# === 03_exposure.py ===
# Step 3: Exposure — building skeleton + population raster
# Outputs:
#   intermediate/building_skeleton.parquet
#   intermediate/population_landscan_2024_shanghai.tif

import hashlib
import importlib.util
import math
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from tqdm import tqdm
import warnings
warnings.filterwarnings("ignore")

_config_path = Path(__file__).resolve().parent / "00_config.py"
_spec = importlib.util.spec_from_file_location("config", _config_path)
config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config)
config.init_environment()

from climate_functions import (setup_logger, save_intermediate, standardize_sentinels,
                                spatial_join_to_district, classify_building_category)

if __name__ == "__main__":
    logger = setup_logger("03_exposure", config.LOGS_DIR)
    t0 = time.time()

    # ══════════════════════════════════════════════════════════════════
    # Step 2.1: Load building vectors
    # ══════════════════════════════════════════════════════════════════
    logger.info("=" * 60)
    logger.info("Step 2.1: Load building vector shapefiles")
    logger.info("=" * 60)

    shp_dir = config.BUILDING_VECTOR_DIR
    shp_files = sorted(shp_dir.glob("*.shp"))
    logger.info(f"Found {len(shp_files)} building SHP files in {shp_dir}")

    frames = []
    for shp_path in tqdm(shp_files, desc="Loading SHP", unit="file"):
        gdf = gpd.read_file(shp_path)
        gdf["source_file"] = shp_path.stem
        # Area in metric CRS
        if gdf.crs and not gdf.crs.is_projected:
            gdf_metric = gdf.to_crs("EPSG:32651")
        elif gdf.crs and gdf.crs != "EPSG:32651":
            gdf_metric = gdf.to_crs("EPSG:32651")
        else:
            gdf_metric = gdf
        gdf["footprint_area_m2"] = gdf_metric.geometry.area
        # Centroids in WGS84
        if gdf.crs and str(gdf.crs) != "EPSG:4326":
            gdf_wgs = gdf.to_crs("EPSG:4326")
        else:
            gdf_wgs = gdf
        gdf["centroid_lon"] = gdf_wgs.geometry.centroid.x
        gdf["centroid_lat"] = gdf_wgs.geometry.centroid.y
        # Drop geometry early to save memory in concat
        frames.append(pd.DataFrame(gdf.drop(columns=["geometry"])))

    buildings = pd.concat(frames, ignore_index=True)
    logger.info(f"Total buildings loaded: {len(buildings):,}")

    # Sentinel cleanup (only relevant text columns)
    sentinels = ["M", "暂无", "--", "-", "无", "", " ", "null", "NULL", "None"]
    text_cols = buildings.select_dtypes(include=["object"]).columns.tolist()
    buildings = standardize_sentinels(buildings, sentinels, columns=text_cols, logger=logger)

    # Building ID — fast hash from position + source
    buildings["building_id"] = (
        buildings["centroid_lon"].round(8).astype(str) + "_" +
        buildings["centroid_lat"].round(8).astype(str) + "_" +
        buildings["source_file"].astype(str)
    ).apply(lambda s: hashlib.md5(s.encode()).hexdigest()[:16])

    # ══════════════════════════════════════════════════════════════════
    # Step 2.2: Height → floors → function → classification
    # ══════════════════════════════════════════════════════════════════
    logger.info("Step 2.2: Building classification")

    # Floor estimation
    if "Height" in buildings.columns:
        buildings["Height"] = pd.to_numeric(buildings["Height"], errors="coerce")
    else:
        buildings["Height"] = np.nan
    buildings["estimated_floors"] = np.where(
        buildings["Height"].notna() & (buildings["Height"] > 0),
        np.ceil(buildings["Height"] / config.BUILDING_FLOOR_HEIGHT_M).clip(lower=1),
        np.nan
    )

    # Floor bin (vectorized)
    floors = buildings["estimated_floors"]
    buildings["floor_bin"] = np.where(floors.isna(), "unknown",
                             np.where(floors <= 6, "low_rise",
                             np.where(floors <= 30, "mid_high_rise", "super_high_rise")))

    # Age — primary source: building vector "Year" column
    if "Year" in buildings.columns:
        buildings["age_year"] = pd.to_numeric(buildings["Year"], errors="coerce")
    else:
        buildings["age_year"] = np.nan
    n_before = buildings["age_year"].notna().sum()
    logger.info(f"Building vector Year coverage: {n_before:,}/{len(buildings):,}")

    # Age enrichment — fill missing age_year from Lianjia community JGSJ (竣工时间)
    import re
    from scipy.spatial import cKDTree as cKDTree_age
    lj_poi_dir_age = config.LIANJIA_POI_DIR
    lj_shps_age = sorted(lj_poi_dir_age.glob("*.shp")) if lj_poi_dir_age.exists() else []
    if lj_shps_age:
        logger.info("Loading Lianjia POI for building age enrichment...")
        lj_age_frames = [gpd.read_file(s) for s in lj_shps_age]
        lj_age_gdf = pd.concat(lj_age_frames, ignore_index=True)
        lj_age_gdf = gpd.GeoDataFrame(lj_age_gdf, geometry="geometry", crs="EPSG:4326")
        if "JGSJ" in lj_age_gdf.columns:
            def _parse_jgsj(s):
                if pd.isna(s):
                    return np.nan
                m = re.search(r"(\d{4})", str(s))
                if m:
                    yr = int(m.group(1))
                    if 1900 <= yr <= 2025:
                        return float(yr)
                return np.nan
            lj_age_gdf["year_built"] = lj_age_gdf["JGSJ"].apply(_parse_jgsj)
            lj_age_valid = lj_age_gdf.dropna(subset=["year_built"]).copy()
            logger.info(f"Lianjia communities with valid JGSJ: {len(lj_age_valid):,}/{len(lj_age_gdf):,}")
            if len(lj_age_valid) > 0:
                lj_age_coords = np.column_stack([lj_age_valid.geometry.x, lj_age_valid.geometry.y])
                tree_age = cKDTree_age(lj_age_coords)
                bldg_coords_age = np.column_stack([buildings["centroid_lon"], buildings["centroid_lat"]])
                max_dist_age_deg = 500 / 111000.0  # 500m matching radius
                dists_age, idxs_age = tree_age.query(bldg_coords_age, distance_upper_bound=max_dist_age_deg)
                matched_age = (dists_age < max_dist_age_deg) & buildings["age_year"].isna()
                lj_years = lj_age_valid["year_built"].values
                buildings.loc[matched_age, "age_year"] = lj_years[idxs_age[matched_age]]
                n_after = buildings["age_year"].notna().sum()
                logger.info(f"Age enrichment from Lianjia: {n_after - n_before:,} buildings filled "
                            f"({n_after:,}/{len(buildings):,} total coverage)")
        else:
            logger.warning("Lianjia POI has no JGSJ column, skipping age enrichment")
    else:
        logger.warning("No Lianjia POI SHP found, skipping age enrichment")

    def _age_bin_vec(y_series):
        return np.where(y_series.isna(), "unknown",
               np.where(y_series <= 1990, "pre_1990",
               np.where(y_series <= 2001, "1990_2001", "post_2002")))
    buildings["age_bin"] = _age_bin_vec(buildings["age_year"])

    # Function
    if "Function" in buildings.columns:
        buildings["function_class"] = buildings["Function"].apply(
            lambda x: "residential" if str(x).strip() in ["Residence", "住宅", "居住"] else "commercial"
        )
    else:
        buildings["function_class"] = "residential"

    # Category (vectorized)
    floors = buildings["estimated_floors"]
    age = buildings["age_year"]
    func = buildings["function_class"]
    cat = pd.Series("unknown", index=buildings.index)
    # Commercial → D
    cat = cat.where(func != "commercial", "D")
    # Low-rise residential
    low = (func != "commercial") & floors.notna() & (floors <= 6)
    cat[low & (age <= 1990)] = "A_old"
    cat[low & (age > 1990) & (age < 2002)] = "A_old"
    cat[low & (age >= 2002)] = "A_new"
    cat[low & age.isna()] = "A_old"  # unknown age → A_old
    # Mid/high-rise residential
    mid = (func != "commercial") & floors.notna() & (floors > 6) & (floors <= 30)
    cat[mid & (age <= 2001)] = "B_old"
    cat[mid & (age > 2001)] = "B_new"
    cat[mid & age.isna()] = "B_old"  # unknown age → B_old
    # Super-high-rise
    hi = (func != "commercial") & floors.notna() & (floors > 30)
    cat[hi] = "C"
    # Remaining unknown with valid func
    still_unk = (cat == "unknown") & (func != "commercial") & floors.isna()
    cat[still_unk] = "B_new"  # fallback
    buildings["building_category"] = cat
    buildings["category_source"] = "stable_proxy"

    logger.info(f"Category distribution:\n{buildings['building_category'].value_counts()}")

    # ══════════════════════════════════════════════════════════════════
    # Step 2.3: District assignment
    # ══════════════════════════════════════════════════════════════════
    logger.info("Step 2.3: District spatial join")

    admin_gdf = gpd.read_file(config.ADMIN_BOUNDARY_SHP)
    sh_admin = admin_gdf[admin_gdf["市"] == "上海市"].copy()
    sh_admin["县"] = sh_admin["县"].replace(config.ADMIN_DISTRICT_RENAME)
    sh_districts = sh_admin.dissolve(by="县").reset_index()

    # Create point GeoDataFrame from centroids for fast spatial join
    from shapely.geometry import Point
    points_gdf = gpd.GeoDataFrame(
        buildings[["centroid_lon", "centroid_lat"]],
        geometry=gpd.points_from_xy(buildings["centroid_lon"], buildings["centroid_lat"]),
        crs="EPSG:4326"
    )
    points_gdf = spatial_join_to_district(points_gdf, sh_districts, district_col="县")
    buildings["district"] = points_gdf["district"].values
    buildings["district_matched"] = points_gdf["district_matched"].values
    n_matched = buildings["district_matched"].sum()
    logger.info(f"District match: {n_matched:,}/{len(buildings):,} ({n_matched/len(buildings):.1%})")
    buildings = buildings[buildings["district_matched"]].copy()
    logger.info(f"After district filter: {len(buildings):,}")

    # ══════════════════════════════════════════════════════════════════
    # Step 2.4: Three-tier building valuation
    # ══════════════════════════════════════════════════════════════════
    logger.info("Step 2.4: Building valuation (3-tier pricing)")

    # Load district & city price
    from district_price_data import load_district_price_long

    district_price_df = load_district_price_long(config)
    # Latest available month per district
    latest_dp = district_price_df.sort_values("date").groupby("district").last().reset_index()
    district_price_map = dict(zip(latest_dp["district"], latest_dp["district_price"]))

    city_price_df = pd.read_excel(config.CITY_PRICE_EXCEL)
    # Melt city price to long format
    date_cols = [c for c in city_price_df.columns if "-" in str(c) and len(str(c)) == 7]
    if date_cols:
        city_long = city_price_df.melt(value_vars=date_cols, var_name="date", value_name="city_price")
        city_long["city_price"] = pd.to_numeric(city_long["city_price"], errors="coerce")
        city_price_latest = city_long.dropna(subset=["city_price"]).sort_values("date").iloc[-1]["city_price"]
    else:
        city_price_latest = 50000.0  # fallback
    logger.info(f"City-wide latest price: {city_price_latest:.0f} CNY/m2")

    # Try Lianjia POI matching (L1 pricing tier)
    lj_poi_dir = config.LIANJIA_POI_DIR
    lj_shps = sorted(lj_poi_dir.glob("*.shp")) if lj_poi_dir.exists() else []
    poi_price_map = {}

    if lj_shps:
        logger.info(f"Loading Lianjia POI from {len(lj_shps)} files...")
        lj_frames = [gpd.read_file(s) for s in lj_shps]
        lj_gdf = pd.concat(lj_frames, ignore_index=True)
        lj_gdf = gpd.GeoDataFrame(lj_gdf, geometry="geometry", crs="EPSG:4326")
        # Find price column
        price_col = None
        for c in ["unit_price", "均价", "price", "avg_price"]:
            if c in lj_gdf.columns:
                price_col = c; break
        if price_col:
            lj_gdf["lj_price"] = pd.to_numeric(lj_gdf[price_col], errors="coerce")
            lj_valid = lj_gdf.dropna(subset=["lj_price"])
            if len(lj_valid) > 0:
                from scipy.spatial import cKDTree
                lj_coords = np.column_stack([lj_valid.geometry.x, lj_valid.geometry.y])
                tree = cKDTree(lj_coords)
                bldg_coords = np.column_stack([buildings["centroid_lon"], buildings["centroid_lat"]])
                # ~0.01 deg ≈ 1km at Shanghai latitude
                max_dist_deg = config.MATCH_DISTANCE_MAX_M / 111000.0
                dists, idxs = tree.query(bldg_coords, distance_upper_bound=max_dist_deg)
                matched = dists < max_dist_deg
                if matched.sum() > 0:
                    prices = lj_valid["lj_price"].values
                    for i in np.where(matched)[0]:
                        poi_price_map[i] = prices[idxs[i]]
                logger.info(f"L1 Lianjia match: {matched.sum():,}/{len(buildings):,}")

    # Assign prices: L1 → L2 → L3 (vectorized)
    buildings["price_source_level"] = 3
    buildings["community_price"] = city_price_latest

    # L2: district price (vectorized)
    dp_series = buildings["district"].map(district_price_map)
    l2_mask = dp_series.notna()
    buildings.loc[l2_mask, "community_price"] = dp_series[l2_mask]
    buildings.loc[l2_mask, "price_source_level"] = 2

    # L1: POI price (overrides L2, vectorized)
    if poi_price_map:
        poi_indices = np.array(list(poi_price_map.keys()), dtype=int)
        poi_prices = np.array(list(poi_price_map.values()), dtype=float)
        buildings.iloc[poi_indices, buildings.columns.get_loc("community_price")] = poi_prices
        buildings.iloc[poi_indices, buildings.columns.get_loc("price_source_level")] = 1

    logger.info(f"Price tiers: {buildings['price_source_level'].value_counts().to_dict()}")

    # ── Commercial building exposure adjustment ──
    # Commercial buildings (category D) use construction-cost-based valuation
    # rather than residential market prices, following the replacement-cost
    # approach of Tu et al. (2023, NHESS) citing Arcadis (2020).
    # (1) Cap footprint at 5,000 m² — large polygons often represent
    #     campus/industrial complexes rather than individual buildings.
    # (2) Apply fixed construction cost of 9,800 CNY/m² — the average
    #     commercial construction cost in Shanghai from Arcadis (2020),
    #     as used in Tu et al. (2023) for Shanghai flood risk assessment.
    COMMERCIAL_FOOTPRINT_CAP_M2 = 5000.0
    COMMERCIAL_CONSTRUCTION_COST = 9800.0  # CNY/m², Arcadis (2020)
    is_commercial = (buildings["function_class"] == "commercial")
    n_capped = (is_commercial & (buildings["footprint_area_m2"] > COMMERCIAL_FOOTPRINT_CAP_M2)).sum()
    buildings["effective_footprint_m2"] = buildings["footprint_area_m2"].copy()
    buildings.loc[is_commercial, "effective_footprint_m2"] = (
        buildings.loc[is_commercial, "footprint_area_m2"].clip(upper=COMMERCIAL_FOOTPRINT_CAP_M2))
    buildings["effective_price"] = buildings["community_price"].copy()
    buildings.loc[is_commercial, "effective_price"] = COMMERCIAL_CONSTRUCTION_COST
    logger.info(f"Commercial adjustment: {is_commercial.sum():,} buildings, "
                f"{n_capped:,} footprints capped at {COMMERCIAL_FOOTPRINT_CAP_M2:.0f}m2, "
                f"construction cost={COMMERCIAL_CONSTRUCTION_COST:.0f} CNY/m2 (Arcadis 2020)")

    # Value = effective_footprint * floors * effective_price
    buildings["value"] = (buildings["effective_footprint_m2"] *
                          buildings["estimated_floors"].fillna(1) *
                          buildings["effective_price"])
    buildings.loc[buildings["value"].isna() | (buildings["value"] <= 0), "value"] = 0.0
    logger.info(f"Total exposure: {buildings['value'].sum()/1e12:.2f} trillion CNY")
    logger.info(f"  Residential: {buildings.loc[~is_commercial, 'value'].sum()/1e12:.2f} T CNY")
    logger.info(f"  Commercial:  {buildings.loc[is_commercial, 'value'].sum()/1e12:.2f} T CNY")

    # ══════════════════════════════════════════════════════════════════
    # Step 2.5: Impact function mapping
    # ══════════════════════════════════════════════════════════════════
    logger.info("Step 2.5: Impact function ID mapping")

    buildings["impf_TC"] = buildings["building_category"].map(config.IMPF_TC_IDS).fillna(4).astype(int)
    buildings["surge_class"] = buildings["building_category"].map(config.CATEGORY_TO_SURGE_CLASS).fillna("mid_rise")
    buildings["impf_SS"] = buildings["surge_class"].map(config.IMPF_SS_IDS).fillna(12).astype(int)

    # ══════════════════════════════════════════════════════════════════
    # Step 2.6: Save building skeleton
    # ══════════════════════════════════════════════════════════════════
    skeleton_cols = [
        "building_id", "centroid_lon", "centroid_lat", "footprint_area_m2",
        "effective_footprint_m2", "Height", "estimated_floors", "floor_bin",
        "age_year", "age_bin",
        "function_class", "building_category", "category_source",
        "district", "district_matched", "source_file",
        "value", "impf_TC", "impf_SS", "surge_class",
        "community_price", "effective_price", "price_source_level",
    ]
    existing_cols = [c for c in skeleton_cols if c in buildings.columns]
    skeleton = buildings[existing_cols].copy()
    save_intermediate(skeleton, config.BUILDING_SKELETON_PARQUET, "building_skeleton", logger)
    logger.info(f"Building skeleton: {len(skeleton):,} buildings, {len(existing_cols)} columns")

    # ══════════════════════════════════════════════════════════════════
    # Step 2.7: Population raster (LandScan clip)
    # ══════════════════════════════════════════════════════════════════
    logger.info("Step 2.7: Clip LandScan population raster")

    import rasterio
    from rasterio.warp import reproject, Resampling
    from rasterio.transform import from_bounds

    landscan_dir = config.LANDSCAN_DIR
    # Find the reference year raster
    ls_patterns = [
        f"*{config.LANDSCAN_REFERENCE_YEAR}*.tif",
        f"*landscan*{config.LANDSCAN_REFERENCE_YEAR}*.tif",
        "*.tif",
    ]
    ls_file = None
    for pat in ls_patterns:
        found = sorted(landscan_dir.glob(pat))
        if found:
            ls_file = found[-1]; break

    if ls_file is None:
        logger.warning(f"No LandScan raster found in {landscan_dir}")
    else:
        logger.info(f"LandScan source: {ls_file.name}")
        lon_min, lat_min, lon_max, lat_max = config.SHANGHAI_BBOX
        out_path = config.POPULATION_LANDSCAN_CLIPPED_TIF
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with rasterio.open(str(ls_file)) as src:
            from rasterio.windows import from_bounds as rb_bounds
            window = rb_bounds(lon_min, lat_min, lon_max, lat_max, src.transform)
            data = src.read(1, window=window)
            transform = src.window_transform(window)

        # Write clipped GeoTIFF
        with rasterio.open(
            str(out_path), "w", driver="GTiff",
            height=data.shape[0], width=data.shape[1], count=1,
            dtype=data.dtype, crs="EPSG:4326", transform=transform,
        ) as dst:
            dst.write(data, 1)
        logger.info(f"Population raster saved: {out_path.name} ({data.shape})")

    logger.info(f"03_exposure.py complete in {time.time()-t0:.0f}s")
