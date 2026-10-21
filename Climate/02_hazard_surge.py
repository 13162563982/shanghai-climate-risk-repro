# === 02_hazard_surge.py ===
# Step 2: Storm Surge Hazard — DEM + parametric surge + bathtub inundation
# Depends on: 01 (tc_tracks), 03 (building_skeleton for centroids)
# Outputs:
#   intermediate/dem_shanghai.tif, sla_monthly.csv, surge_heights_hist.csv
#   intermediate/building_elevation.npy, building_coast_distance_m.npy
#   intermediate/haz_SS_{hist,synth,ssp245,ssp585}.hdf5
#   intermediate/twl_vec_{hist,synth}.npy

import gc
import importlib.util
import pickle
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import rasterio
from rasterio.merge import merge
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_bounds
from tqdm import tqdm
import warnings
warnings.filterwarnings("ignore")

_config_path = Path(__file__).resolve().parent / "00_config.py"
_spec = importlib.util.spec_from_file_location("config", _config_path)
config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config)
config.init_environment()

from climate_functions import (
    setup_logger, save_intermediate, load_raster_clip_shanghai,
    compute_surge_for_tracks, extract_sla_from_raster, build_surge_hazard,
    compute_east_sea_coast_distance, build_huangpu_proximity_template,
    assign_surge_hybrid_zones,
)

if __name__ == "__main__":
    logger = setup_logger("02_hazard_surge", config.LOGS_DIR)
    t0 = time.time()

    L_SHELF_M = config.L_SHELF_M
    H_SHELF_M = config.H_SHELF_M

    # ── Step 1.6: FABDEM DEM preprocessing ───────────────────────────
    logger.info("=" * 60)
    logger.info("Step 1.6: FABDEM DEM preprocessing")
    logger.info("=" * 60)

    for tile in config.FABDEM_TILES_SHANGHAI:
        if not tile.exists():
            raise FileNotFoundError(f"FABDEM tile missing: {tile}")

    src_files = [rasterio.open(str(t)) for t in config.FABDEM_TILES_SHANGHAI]
    merged_data, merged_transform = merge(src_files, nodata=-9999)
    merged_crs = src_files[0].crs
    for s in src_files:
        s.close()

    merged_data = merged_data.astype(np.float32)
    merged_data[merged_data <= config.FABDEM_NODATA_VALUE + 1] = np.nan

    lon_min, lat_min, lon_max, lat_max = config.SHANGHAI_BBOX
    res = config.MODEL_RESOLUTION_DEG
    dst_w = int((lon_max - lon_min) / res)
    dst_h = int((lat_max - lat_min) / res)
    dst_transform = from_bounds(lon_min, lat_min, lon_max, lat_max, dst_w, dst_h)

    dst_data = np.full((1, dst_h, dst_w), np.nan, dtype=np.float32)
    reproject(source=merged_data, destination=dst_data,
              src_transform=merged_transform, src_crs=merged_crs,
              dst_transform=dst_transform, dst_crs=config.CRS_STANDARD,
              resampling=Resampling.bilinear, src_nodata=np.nan, dst_nodata=np.nan)
    dem = dst_data[0]
    dem[dem < -100] = np.nan
    dem = np.nan_to_num(dem, nan=0.0)
    logger.info(f"DEM: {dem.shape}, min={dem.min():.1f}, max={dem.max():.1f}, mean={dem.mean():.1f}")

    dem_path = config.DEM_SHANGHAI_TIF
    dem_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(str(dem_path), "w", driver="GTiff",
                       height=dst_h, width=dst_w, count=1, dtype=np.float32,
                       crs=config.CRS_STANDARD, transform=dst_transform, nodata=-9999.0) as f:
        f.write(dem, 1)
    logger.info(f"DEM saved: {dem_path.name}")

    # ── Step 1.7: Parametric surge heights ───────────────────────────
    logger.info("=" * 60)
    logger.info("Step 1.7: Parametric surge height estimation")
    logger.info("=" * 60)

    logger.info(f"Shelf params: L={L_SHELF_M:.0f}m, h={H_SHELF_M:.1f}m")

    with open(config.TC_TRACKS_PKL, "rb") as f:
        tc_shanghai = pickle.load(f)
    logger.info(f"Loaded {tc_shanghai.size} historical tracks")

    surge_df_hist = compute_surge_for_tracks(
        tc_shanghai, config.SHANGHAI_CENTER_LAT, config.SHANGHAI_CENTER_LON,
        config.RMAX_DEFAULT_KM, config.HOLLAND_B_DEFAULT,
        config.RHO_WATER, config.G, config.CD_MAX, config.FETCH_RMAX_FACTOR,
        config.RHO_AIR, L_SHELF_M, H_SHELF_M, logger=logger, label="historical")
    save_intermediate(surge_df_hist, config.SURGE_HEIGHTS_CSV, "surge_heights_hist", logger)

    with open(config.TC_TRACKS_ALL_PKL, "rb") as f:
        tc_all = pickle.load(f)
    logger.info(f"Loaded {tc_all.size} tracks (hist+synth)")

    surge_df_all = compute_surge_for_tracks(
        tc_all, config.SHANGHAI_CENTER_LAT, config.SHANGHAI_CENTER_LON,
        config.RMAX_DEFAULT_KM, config.HOLLAND_B_DEFAULT,
        config.RHO_WATER, config.G, config.CD_MAX, config.FETCH_RMAX_FACTOR,
        config.RHO_AIR, L_SHELF_M, H_SHELF_M, logger=logger, label="hist+synth")
    del tc_all

    # ── Step 1.8: SLA monthly time series ────────────────────────────
    logger.info("=" * 60)
    logger.info("Step 1.8: SLA monthly time series")
    logger.info("=" * 60)

    sla_files = sorted(config.SLA_DIR.glob("sla_*.tif"))
    logger.info(f"SLA rasters: {len(sla_files)}")
    sla_bbox = (121.2, 30.6, 122.5, 31.9)
    sla_recs = []
    with ThreadPoolExecutor(max_workers=config.IO_WORKERS) as ex:
        futs = {ex.submit(extract_sla_from_raster, p, sla_bbox): p for p in sla_files}
        for fut in tqdm(as_completed(futs), total=len(futs), desc="SLA"):
            r = fut.result()
            if r: sla_recs.append(r)

    sla_df = pd.DataFrame(sla_recs).sort_values(["year", "month"]).reset_index(drop=True)
    # Interpolate missing months
    if len(sla_df) > 0:
        full_dates = pd.date_range(f"{sla_df['year'].min()}-01", f"{sla_df['year'].max()}-12", freq="MS")
        sla_df["date_dt"] = pd.to_datetime(sla_df["date"])
        sla_full = pd.DataFrame({"date_dt": full_dates}).merge(
            sla_df[["date_dt", "SLA_mean_m"]], on="date_dt", how="left")
        sla_full["SLA_mean_m"] = sla_full["SLA_mean_m"].interpolate("linear")
        sla_full["year"] = sla_full["date_dt"].dt.year
        sla_full["month"] = sla_full["date_dt"].dt.month
        sla_full["date"] = sla_full["date_dt"].dt.strftime("%Y-%m")
        sla_out = sla_full[["year", "month", "date", "SLA_mean_m"]]
    else:
        sla_out = sla_df
    save_intermediate(sla_out, config.SLA_MONTHLY_CSV, "sla_monthly", logger)

    sla_lookup = {}
    for _, row in sla_out.iterrows():
        sla_lookup[(int(row["year"]), int(row["month"]))] = float(row["SLA_mean_m"])

    # ── Step 1.9: Bathtub inundation → Surge Hazard ──────────────────
    logger.info("=" * 60)
    logger.info("Step 1.9: Bathtub inundation model")
    logger.info("=" * 60)

    from climada.hazard import Centroids

    bldg = pd.read_parquet(config.BUILDING_SKELETON_PARQUET)
    logger.info(f"Building skeleton: {len(bldg):,}")
    bldg_lons = bldg["centroid_lon"].values
    bldg_lats = bldg["centroid_lat"].values

    # Sample building elevation from DEM
    with rasterio.open(str(config.DEM_SHANGHAI_TIF)) as src:
        elev = np.array([v[0] for v in src.sample(zip(bldg_lons, bldg_lats))])
    elev = np.where(np.isnan(elev) | (elev <= -100), 0.0, elev)
    np.save(str(config.BUILDING_ELEVATION_NPY), elev)
    logger.info(f"Building elevation: mean={elev.mean():.1f}m, low(≤3m)={np.mean(elev<=3):.1%}")

    # Coast distance
    coast_dist = compute_east_sea_coast_distance(bldg_lons, bldg_lats, config, logger=logger)
    np.save(str(config.BUILDING_COAST_DISTANCE_NPY), coast_dist.astype(np.float32))

    # Huangpu river proximity template
    district_names = bldg["district"].astype(str).values
    hp_template = build_huangpu_proximity_template(
        bldg_lons, bldg_lats, config, district_names=district_names,
        scenario_tag="90m_def_gap", logger=logger)
    np.save(str(config.BUILDING_HUANGPU_OVERBANK_TEMPLATE_NPY), hp_template.astype(np.float32))

    hybrid_zones = assign_surge_hybrid_zones(coast_dist, river_template=hp_template,
                                              district_names=district_names, config=config)
    surge_centroids = Centroids(lat=bldg_lats, lon=bldg_lons)
    batch_size = max(1, int(64 * 1024 * 1024 / (len(bldg) * 8)))  # ~64MB per batch

    # Historical
    logger.info("Building historical surge hazard...")
    haz_hist, twl_hist = build_surge_hazard(
        surge_df_hist, sla_lookup, elev, surge_centroids, batch_size,
        logger=logger, label="historical",
        coast_distance_m=coast_dist, config=config,
        river_template=hp_template, hybrid_zones=hybrid_zones)
    haz_hist.write_hdf5(str(config.HAZ_SS_HIST_HDF5))
    np.save(str(config.TWL_VEC_HIST_NPY), twl_hist)

    # Synthetic (hist+synth)
    logger.info("Building synthetic surge hazard...")
    haz_synth, twl_synth = build_surge_hazard(
        surge_df_all, sla_lookup, elev, surge_centroids, batch_size,
        logger=logger, label="synthetic",
        coast_distance_m=coast_dist, config=config,
        river_template=hp_template, hybrid_zones=hybrid_zones)
    haz_synth.write_hdf5(str(config.HAZ_SS_SYNTH_HDF5))
    np.save(str(config.TWL_VEC_SYNTH_NPY), twl_synth)

    # ── Step 1.10: SSP sea-level rise scenarios ──────────────────────
    logger.info("=" * 60)
    logger.info("Step 1.10: SSP sea-level rise scenarios")
    logger.info("=" * 60)

    for ssp, slr, path in [
        ("SSP2-4.5", config.SSP_SEA_LEVEL_RISE_2050["SSP2-4.5"], config.HAZ_SS_SSP245_HDF5),
        ("SSP5-8.5", config.SSP_SEA_LEVEL_RISE_2050["SSP5-8.5"], config.HAZ_SS_SSP585_HDF5),
    ]:
        tc_factor = config.SSP_TC_INTENSITY_FACTOR_2050.get(ssp, 1.0)
        wind_factor = tc_factor ** 2
        logger.info(f"{ssp}: SLR +{slr}m, surge_wind_scale={wind_factor:.4f}")
        haz_ssp, _ = build_surge_hazard(
            surge_df_all, sla_lookup, elev, surge_centroids, batch_size,
            logger=logger, slr_offset=slr, surge_wind_scale=wind_factor, label=ssp,
            coast_distance_m=coast_dist, config=config,
            river_template=hp_template, hybrid_zones=hybrid_zones)
        haz_ssp.write_hdf5(str(path))
        logger.info(f"  {ssp} saved: {path.name}")

    logger.info(f"02_hazard_surge.py complete in {time.time()-t0:.0f}s")
