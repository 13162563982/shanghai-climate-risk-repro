# === climate_functions.py ===
# Shanghai Real-Estate Climate Risk Model v8 — Shared utility functions.
# All reusable helpers for the computation + visualization pipeline.

import gc
import json
import logging
import pickle
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio


# =====================================================================
# 1. Logging
# =====================================================================

def setup_logger(name, log_dir, level=logging.INFO):
    """Create a timestamped file+console logger."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fh = logging.FileHandler(log_dir / f"log_{name}_{ts}.log", encoding="utf-8")
    fh.setLevel(level)
    ch = logging.StreamHandler()
    ch.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


# =====================================================================
# 2. Intermediate I/O
# =====================================================================

def save_intermediate(data, file_path, step_name, logger=None):
    """Save intermediate data (csv/parquet/json/pkl) with auto format detection."""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    ext = file_path.suffix.lower()
    if ext == ".csv":
        data.to_csv(file_path, index=False, encoding="utf-8-sig")
    elif ext == ".parquet":
        data.to_parquet(file_path, index=False)
    elif ext == ".json":
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    elif ext == ".pkl":
        with open(file_path, "wb") as f:
            pickle.dump(data, f)
    else:
        raise ValueError(f"Unsupported format: {ext}")
    msg = f"[{step_name}] Saved: {file_path} ({file_path.stat().st_size / 1024:.1f} KB)"
    if logger:
        logger.info(msg)


def log_data_quality(df, step_name, logger=None, output_path=None):
    """Log basic data quality stats for a DataFrame."""
    n_rows, n_cols = df.shape
    missing = {col: df[col].isnull().mean() for col in df.columns}
    cols_missing = {k: v for k, v in missing.items() if v > 0}
    msg = f"[{step_name}] {n_rows:,} rows x {n_cols} cols"
    if cols_missing:
        msg += " | missing: " + ", ".join(f"{k}={v:.1%}" for k, v in cols_missing.items())
    if logger:
        logger.info(msg)


# =====================================================================
# 3. Raster utilities
# =====================================================================

def load_raster_clip_shanghai(tif_path, bbox, target_nodata=np.nan):
    """Load a GeoTIFF and clip to a spatial bounding box."""
    from rasterio.windows import from_bounds

    tif_path = Path(tif_path)
    if not tif_path.exists():
        raise FileNotFoundError(f"Raster file not found: {tif_path}")

    lon_min, lat_min, lon_max, lat_max = bbox

    with rasterio.open(tif_path) as src:
        window = from_bounds(lon_min, lat_min, lon_max, lat_max, src.transform)
        data = src.read(1, window=window)
        transform = src.window_transform(window)
        nodata = src.nodata
        if nodata is not None:
            mask = np.isclose(data, nodata, equal_nan=True)
            data = data.astype(np.float64)
            data[mask] = target_nodata

    return {
        "data": data,
        "transform": transform,
        "crs": src.crs,
        "shape": data.shape,
        "bounds": rasterio.transform.array_bounds(data.shape[0], data.shape[1], transform),
        "nodata": nodata,
    }


# =====================================================================
# 4. Building classification
# =====================================================================

def classify_building_category(row):
    """Map a building to category (A_old/A_new/B_old/B_new/C/D) by floors+age+function."""
    floors = row["estimated_floors"]
    age = row["age_year"]
    func = row["function_class"]
    if pd.isna(floors) or pd.isna(func):
        return "unknown"
    if func == "commercial":
        return "D"
    if pd.isna(age):
        if floors <= 6:
            return "A_unknown_age"
        if floors <= 30:
            return "B_unknown_age"
        return "C"
    if floors <= 6:
        return "A_old" if age <= 1990 else ("A_new" if age >= 2002 else "A_old")
    if floors <= 30:
        return "B_old" if age <= 2001 else "B_new"
    return "C"


# =====================================================================
# 5. Spatial join
# =====================================================================

def spatial_join_to_district(gdf_points, district_gdf, district_col="县",
                             nearest_fallback=True, fallback_max_distance_m=5000.0):
    """Spatially join points to Shanghai 16-district polygons."""
    import geopandas as gpd

    if gdf_points.crs != district_gdf.crs:
        district_gdf = district_gdf.to_crs(gdf_points.crs)
    district_ref = district_gdf[[district_col, "geometry"]].copy()

    result = gpd.sjoin(gdf_points, district_ref, how="left", predicate="within")
    if "index_right" in result.columns:
        result = result.drop(columns=["index_right"])
    result = result.rename(columns={district_col: "district"})
    result["district_match_method"] = np.where(result["district"].notna(), "within", "unmatched")

    unmatched_mask = result["district"].isna()
    if nearest_fallback and unmatched_mask.any():
        metric_crs = "EPSG:3857"
        unmatched_metric = result.loc[unmatched_mask].to_crs(metric_crs)
        district_metric = district_ref.to_crs(metric_crs)
        nearest = gpd.sjoin_nearest(unmatched_metric, district_metric, how="left",
                                     distance_col="_dist_m")
        valid = nearest[district_col].notna()
        if fallback_max_distance_m is not None:
            valid &= nearest["_dist_m"] <= fallback_max_distance_m
        if valid.any():
            result.loc[nearest.index[valid], "district"] = nearest.loc[valid, district_col].values
            result.loc[nearest.index[valid], "district_match_method"] = "nearest"
    result["district_matched"] = result["district"].notna()
    return result


# =====================================================================
# 6. Sentinel standardization
# =====================================================================

def standardize_sentinels(df, sentinel_values, columns=None, logger=None):
    """Replace sentinel/placeholder values with NaN."""
    cols = columns if columns is not None else df.columns.tolist()
    df_cleaned = df.copy()
    total = 0
    for col in cols:
        if df_cleaned[col].dtype == object:
            stripped = df_cleaned[col].astype(str).str.strip()
            mask = stripped.isin([str(s).strip() for s in sentinel_values])
        else:
            mask = df_cleaned[col].isin(sentinel_values)
        n = mask.sum()
        df_cleaned.loc[mask, col] = np.nan
        total += n
    if logger and total > 0:
        logger.info(f"Sentinel cleanup: {total:,} values replaced with NaN")
    return df_cleaned


# =====================================================================
# 7. Parametric storm surge computation
# =====================================================================

def compute_surge_for_tracks(tc_tracks, center_lat, center_lon,
                             rmax_default_km, holland_b, rho_water, g,
                             cd_max, fetch_rmax_factor, rho_air,
                             l_shelf_m, h_shelf_m, logger=None, label=""):
    """Compute parametric surge height for each TC event.

    S_e = S_IB + S_wind where:
        S_IB = (P_env - P_c) / (rho_water * g)
        S_wind = (rho_air/rho_water) * C_d * V_coast^2 * L_eff / (g * h_shelf)
    """
    from tqdm import tqdm

    records = []
    for track in tqdm(tc_tracks.data, desc=f"Surge ({label})", unit="trk"):
        sid = str(getattr(track, "sid", "unknown"))
        name = str(getattr(track, "name", "unnamed"))
        lats, lons = track.lat.values, track.lon.values
        dist_deg = np.sqrt((lats - center_lat) ** 2 + (lons - center_lon) ** 2)
        ci = int(np.nanargmin(dist_deg))
        et = pd.Timestamp(track.time.values[ci])

        base = {"event_id": sid, "event_name": name, "event_time": et,
                "event_year": et.year, "event_month": et.month,
                "Pc_hPa": np.nan, "Penv_hPa": np.nan, "Vmax_ms": 0.0,
                "S_IB_m": 0.0, "S_wind_m": 0.0, "S_e_m": 0.0,
                "closest_dist_deg": float(dist_deg[ci])}

        if "central_pressure" not in track.data_vars:
            records.append(base); continue
        pc = float(track.central_pressure.values[ci])

        penv = np.nan
        for f in ["environmental_pressure", "penv"]:
            if f in track.data_vars:
                penv = float(track[f].values[ci]); break
        if np.isnan(penv):
            records.append(base); continue

        if "max_sustained_wind" not in track.data_vars:
            records.append(base); continue
        vmax = float(track.max_sustained_wind.values[ci])
        if np.isnan(pc) or np.isnan(vmax) or vmax <= 0:
            records.append(base); continue

        rmax_km = np.nan
        if "radius_max_wind" in track.data_vars:
            rmax_km = float(track.radius_max_wind.values[ci])
        if np.isnan(rmax_km) or rmax_km <= 0:
            rmax_km = rmax_default_km
        rmax_m = rmax_km * 1000.0

        dist_m = float(dist_deg[ci]) * 111_000.0
        if dist_m <= rmax_m:
            v_coast = vmax
        else:
            rr = (rmax_m / dist_m) ** holland_b
            v_coast = vmax * np.sqrt(rr * np.exp(1.0 - rr))

        s_ib = (penv - pc) * 100.0 / (rho_water * g)
        cd = min((0.75 + 0.067 * v_coast) * 1e-3, cd_max)
        l_eff = min(l_shelf_m, fetch_rmax_factor * rmax_m)
        s_wind = (rho_air / rho_water) * cd * v_coast**2 * l_eff / (g * h_shelf_m)
        s_e = s_ib + s_wind

        rec = dict(base)
        rec.update(Pc_hPa=pc, Penv_hPa=penv, Vmax_ms=vmax, Rmax_km=rmax_km,
                   V_coast_ms=v_coast, S_IB_m=s_ib, S_wind_m=s_wind, S_e_m=s_e)
        records.append(rec)

    df = pd.DataFrame(records)
    df["surge_height_m"] = df["S_e_m"]
    if logger:
        logger.info(f"[{label}] {len(df)} events, S_e: "
                    f"min={df['S_e_m'].min():.3f}, max={df['S_e_m'].max():.3f}, mean={df['S_e_m'].mean():.3f}")
    return df


def extract_sla_from_raster(tif_path, bbox):
    """Extract mean SLA from a single monthly raster."""
    tif_path = Path(tif_path)
    parts = tif_path.stem.replace("sla_", "").split("-")
    if len(parts) != 2:
        return None
    year, month = int(parts[0]), int(parts[1])
    try:
        info = load_raster_clip_shanghai(tif_path, bbox)
        data = info["data"]
        valid = ~np.isnan(data) & (np.abs(data) < 10)
        if valid.sum() > 0:
            return {"year": year, "month": month, "date": f"{year:04d}-{month:02d}",
                    "SLA_mean_m": float(np.mean(data[valid]))}
    except Exception:
        pass
    return None


# =====================================================================
# 8. Coastal inundation (bathtub + Huangpu overlay)
# =====================================================================

def _compute_huangpu_event_scale(twl_values, config, defense_profile=None):
    """Compute Huangpu river branch event-response scale (0-1 per event)."""
    twl = np.asarray(twl_values, dtype=np.float64)
    dp = defense_profile or {}
    trigger = float(dp.get("huangpu_trigger_twl_m", getattr(config, "HYBRID_HUANGPU_TRIGGER_TWL_M", np.inf)))
    reference = float(dp.get("huangpu_reference_twl_m", getattr(config, "HYBRID_HUANGPU_REFERENCE_TWL_M", np.inf)))
    full_resp = float(dp.get("huangpu_full_response_twl_m", getattr(config, "HYBRID_HUANGPU_FULL_RESPONSE_TWL_M", reference)))
    max_scale = float(getattr(config, "HYBRID_HUANGPU_MAX_SCALE", 1.0))
    mode = str(getattr(config, "HYBRID_HUANGPU_RESPONSE_MODE", "linear")).lower()

    # No-defense open boundary scenario
    if trigger <= 0.0 and reference <= 0.0 and full_resp <= 0.0:
        open_ref = float(getattr(config, "HYBRID_HUANGPU_OPEN_BOUNDARY_REFERENCE_TWL_M", 1.0))
        if not np.isfinite(open_ref) or open_ref <= 0:
            open_ref = 1.0
        normed = np.clip(twl / open_ref, 0.0, 1.0)
        if mode == "smoothstep":
            s = normed * normed * (3.0 - 2.0 * normed)
        else:
            s = normed
        return np.where(twl > 0.0, np.clip(s * max_scale, 0.0, max_scale), 0.0)

    if not (np.isfinite(trigger) and np.isfinite(reference) and reference > trigger):
        return np.zeros_like(twl)

    normed = np.clip((twl - trigger) / (reference - trigger), 0.0, 1.0)
    if mode == "smoothstep":
        s = normed * normed * (3.0 - 2.0 * normed)
    else:
        s = normed
    eff_full = full_resp if np.isfinite(full_resp) and full_resp > reference else reference
    if eff_full > reference:
        tail = np.clip((twl - reference) / (eff_full - reference), 0.0, 1.0)
        s = np.where(twl > reference, np.maximum(s, tail), s)
    return np.clip(s * max_scale, 0.0, max_scale)


def compute_coastal_inundation_depth(twl_values, elevation, coast_dist, config,
                                     river_template=None, hybrid_zones=None,
                                     defense_profile=None):
    """Bathtub inundation: defense-crest overtopping + exponential decay + river overlay.

    Returns (n_events, n_buildings) array.
    """
    dp = defense_profile or {}
    twl = np.asarray(twl_values, dtype=np.float64)
    elev = np.asarray(elevation, dtype=np.float64)
    cdist = np.asarray(coast_dist, dtype=np.float64)

    defense_on = dp.get("coastal_defense_enabled", True)
    crest = float(dp.get("coastal_defense_crest_m", getattr(config, "COASTAL_DEFENSE_CREST_M", 0.0))) if defense_on else 0.0
    atten_rate = float(getattr(config, "COASTAL_OVERLAND_ATTENUATION_RATE", 1e-4))
    min_reach = float(getattr(config, "COASTAL_MIN_REACH_M", 500.0))
    atten_exp = float(getattr(config, "COASTAL_ATTENUATION_EXPONENT", 3.0))

    h_over = np.maximum(0.0, twl - crest)  # (n_events,)
    reach = np.maximum(min_reach, h_over / max(atten_rate, 1e-12))[:, np.newaxis]
    h_base = np.minimum(np.maximum(0.0, twl[:, None] - elev[None, :]), h_over[:, None])
    decay = np.exp(-atten_exp * cdist[None, :] / reach)
    h_base *= decay
    h_base[cdist[None, :] > reach] = 0.0

    # Huangpu river overlay
    hp_on = dp.get("huangpu_overbank_enabled",
                    bool(getattr(config, "HYBRID_HUANGPU_OVERBANK_ENABLED", False)))
    if river_template is not None and hp_on:
        rt = np.asarray(river_template, dtype=np.float64)
        scale = _compute_huangpu_event_scale(twl, config, defense_profile=dp)
        river_depth = scale[:, None] * rt[None, :]
        h_base = np.maximum(h_base, river_depth)

    min_depth = float(getattr(config, "COASTAL_MIN_INUNDATION_DEPTH_M", 0.0))
    if min_depth > 0:
        h_base[h_base < min_depth] = 0.0
    return h_base


def build_surge_hazard(surge_df, sla_lookup, elev, centroids, batch_size,
                       logger=None, slr_offset=0.0, surge_wind_scale=1.0, label="",
                       coast_distance_m=None, config=None,
                       river_template=None, hybrid_zones=None,
                       defense_profile=None):
    """Build CLIMADA Hazard(haz_type='SS') from surge DataFrame."""
    from scipy import sparse
    from tqdm import tqdm
    from climada.hazard import Hazard

    n_ev = len(surge_df)
    n_bldg = len(elev)
    ids, dates = [], []
    twl_vec = np.empty(n_ev, dtype=np.float64)
    for idx, (_, ev) in enumerate(surge_df.iterrows()):
        s_ib, s_wind = ev["S_IB_m"], ev["S_wind_m"]
        s_e = s_ib + s_wind * surge_wind_scale
        y, m = int(ev["event_year"]), int(ev["event_month"])
        sla = sla_lookup.get((y, m), 0.0)
        twl_vec[idx] = s_e + sla + slr_offset
        ids.append(ev.get("event_id", f"event_{idx}"))
        dates.append(pd.Timestamp(year=y, month=m, day=15))

    if logger and n_ev > 0:
        logger.info(f"  [{label}] TWL: min={twl_vec.min():.3f}, max={twl_vec.max():.3f}")

    mats = []
    for b0 in tqdm(range(0, n_ev, batch_size), desc=f"Inundation({label})", unit="batch"):
        b1 = min(b0 + batch_size, n_ev)
        twl_b = twl_vec[b0:b1]
        if coast_distance_m is not None and config is not None:
            h = compute_coastal_inundation_depth(
                twl_b, elev, coast_distance_m, config,
                river_template=river_template, hybrid_zones=hybrid_zones,
                defense_profile=defense_profile)
        else:
            h = np.maximum(0.0, twl_b[:, None] - elev[None, :])
        rows, cols, vals = [], [], []
        for i in range(h.shape[0]):
            nz = np.where(h[i] > 0)[0]
            if len(nz):
                rows.extend([i] * len(nz))
                cols.extend(nz.tolist())
                vals.extend(h[i, nz].tolist())
        mats.append(sparse.csr_matrix((vals, (rows, cols)), shape=(b1 - b0, n_bldg)))
        del h; gc.collect()

    intensity = sparse.vstack(mats, format="csr")

    haz = Hazard(haz_type="SS")
    haz.centroids = centroids
    haz.intensity = intensity
    haz.event_id = np.arange(1, n_ev + 1)
    haz.event_name = ids
    haz.date = np.array([d.toordinal() for d in dates])
    haz.frequency = np.ones(n_ev) / n_ev
    haz.units = "m"
    haz.fraction = sparse.csr_matrix((intensity > 0).astype(float))
    if logger:
        logger.info(f"  [{label}] Hazard: {n_ev} events, nnz={intensity.nnz:,}")
    return haz, twl_vec


# =====================================================================
# 9. East Sea coast distance
# =====================================================================

def compute_east_sea_coast_distance(point_lons, point_lats, config, logger=None):
    """Compute distance (m) from points to Shanghai's East Sea coastline.

    Derives coastline from DEM (water mask connected to domain edge) + admin boundary.
    """
    import geopandas as gpd
    from rasterio.features import shapes
    from scipy import ndimage
    from shapely.geometry import shape as shp_shape

    lons = np.asarray(point_lons, dtype=np.float64)
    lats = np.asarray(point_lats, dtype=np.float64)

    # Build admin land polygon.
    # NOTE (option A): district assignment, area/density and the basemap use
    # ADMIN_BOUNDARY_SHP (official GS(2024)0650 layer), but the shoreline is
    # decoupled onto COASTLINE_BOUNDARY_SHP. The generalised official layer only
    # yields 96.2 km of shoreline vs 347.9 km from the fine layer, which
    # suppressed surge inundation by ~13.7% (docs/_潮损偏移复核报告.md).
    _coast_shp = getattr(config, "COASTLINE_BOUNDARY_SHP", config.ADMIN_BOUNDARY_SHP)
    admin_raw = gpd.read_file(_coast_shp)
    sh = admin_raw[admin_raw["市"] == "上海市"].copy()
    sh["ds"] = sh["县"].replace(config.ADMIN_DISTRICT_RENAME)
    land = sh.dissolve().geometry.iloc[0]
    land_gs = gpd.GeoSeries([land], crs=sh.crs)

    # DEM water mask → ocean connected components
    with rasterio.open(str(config.DEM_SHANGHAI_TIF)) as src:
        dem = src.read(1).astype(np.float64)
        dem_t = src.transform
        dem_crs = src.crs
    if land_gs.crs != dem_crs:
        land_gs = land_gs.to_crs(dem_crs)

    water = np.isfinite(dem) & (dem <= 0.0)
    boundary = np.zeros_like(water)
    boundary[0, :] = water[0, :]
    boundary[-1, :] = water[-1, :]
    boundary[:, -1] = water[:, -1]
    labels, _ = ndimage.label(water, np.ones((3, 3), dtype=int))
    ocean_ids = np.unique(labels[boundary])
    ocean_ids = ocean_ids[ocean_ids > 0]
    ocean_mask = np.isin(labels, ocean_ids)

    polys = [shp_shape(g) for g, v in shapes(ocean_mask.astype(np.uint8),
             mask=ocean_mask, transform=dem_t) if int(v) == 1]
    ocean_union = gpd.GeoSeries(polys, crs=dem_crs).unary_union
    tol = max(abs(dem_t.a), abs(dem_t.e)) * 0.51
    shoreline = land_gs.iloc[0].boundary.intersection(ocean_union.buffer(tol))
    if shoreline.is_empty:
        shoreline = land_gs.iloc[0].boundary.intersection(ocean_union)

    metric_crs = "EPSG:32651"
    shore_m = gpd.GeoSeries([shoreline], crs=config.CRS_STANDARD).to_crs(metric_crs).iloc[0]
    pts_m = gpd.GeoSeries(gpd.points_from_xy(lons, lats), crs=config.CRS_STANDARD).to_crs(metric_crs)
    dists = pts_m.distance(shore_m).to_numpy(dtype=np.float64)
    if logger:
        logger.info(f"Coast distance: mean={dists.mean():.0f}m, max={dists.max():.0f}m")
    return dists


# =====================================================================
# 10. Huangpu river proximity template (simplified, no OSM dependency)
# =====================================================================

# Hardcoded Huangpu river centreline waypoints (WGS84)
_HUANGPU_RIVER_WAYPOINTS = [
    (121.52, 31.39),   # Mouth at Yangtze
    (121.51, 31.35),
    (121.50, 31.30),
    (121.49, 31.28),
    (121.50, 31.25),   # Yangpu
    (121.50, 31.23),   # Huangpu/Pudong
    (121.49, 31.21),
    (121.48, 31.19),
    (121.47, 31.17),
    (121.46, 31.15),
    (121.45, 31.13),
    (121.44, 31.11),   # South bend
    (121.42, 31.08),
    (121.40, 31.06),
    (121.38, 31.04),
    (121.36, 31.02),
    (121.35, 31.00),   # Upstream end
]


def build_huangpu_proximity_template(bldg_lons, bldg_lats, config, district_names=None,
                                     scenario_tag=None, logger=None):
    """Build Huangpu river overbank depth template via exponential distance decay.

    Uses hardcoded river centreline (no OSM dependency).
    """
    import geopandas as gpd
    from shapely.geometry import LineString

    lons = np.asarray(bldg_lons, dtype=np.float64)
    lats = np.asarray(bldg_lats, dtype=np.float64)

    tag = str(scenario_tag or "").lower()
    bankfull = float(getattr(config, "HYBRID_HUANGPU_BANKFULL_DEPTH_M", 2.0))
    if "nodef" in tag:
        decay_d = float(getattr(config, "HYBRID_HUANGPU_NODEF_DECAY_DISTANCE_M", 900.0))
        max_reach = float(getattr(config, "HYBRID_HUANGPU_NODEF_MAX_REACH_M", 2500.0))
    else:
        decay_d = float(getattr(config, "HYBRID_HUANGPU_DECAY_DISTANCE_M", 1500.0))
        max_reach = float(getattr(config, "HYBRID_HUANGPU_MAX_REACH_M", 5000.0))
    min_depth = float(getattr(config, "HYBRID_HUANGPU_MIN_RIVER_DEPTH_M", 0.05))

    metric_crs = "EPSG:32651"
    river_line = gpd.GeoSeries([LineString(_HUANGPU_RIVER_WAYPOINTS)],
                                crs="EPSG:4326").to_crs(metric_crs).iloc[0]
    pts = gpd.GeoSeries(gpd.points_from_xy(lons, lats),
                         crs="EPSG:4326").to_crs(metric_crs)
    dist = pts.distance(river_line).to_numpy(dtype=np.float64)

    template = bankfull * np.exp(-dist / decay_d)
    template[dist > max_reach] = 0.0
    template[template < min_depth] = 0.0

    # Restrict to priority districts
    priority = set(getattr(config, "HYBRID_HUANGPU_PRIORITY_DISTRICTS", []))
    if district_names is not None and priority:
        dn = np.asarray(district_names, dtype=object)
        template[~np.isin(dn, list(priority))] = 0.0

    if logger:
        nz = int((template > 0).sum())
        logger.info(f"Huangpu template: nonzero={nz}, max={template.max():.3f}m, "
                    f"bankfull={bankfull}, decay={decay_d}m, tag={tag or 'default'}")
    return template


def assign_surge_hybrid_zones(coast_dist, river_template=None, district_names=None, config=None):
    """Assign hybrid surge spatial zone labels to buildings."""
    n = len(coast_dist)
    labels = np.full(n, "other_inland", dtype=object)
    if config is not None:
        max_d = float(getattr(config, "HYBRID_ZONE_COASTAL_FRINGE_MAX_DISTANCE_M", np.inf))
        coastal = np.asarray(coast_dist) <= max_d
        coastal_ds = set(getattr(config, "HYBRID_ZONE_COASTAL_DISTRICTS", []))
        if district_names is not None and coastal_ds:
            coastal &= np.isin(np.asarray(district_names, dtype=object), list(coastal_ds))
        labels[coastal] = "coastal_fringe"
    if river_template is not None:
        rt = np.asarray(river_template, dtype=np.float64)
        labels[np.isfinite(rt) & (rt > 0)] = "huangpu_backflow_priority"
    return labels


# =====================================================================
# 11. Surge exposed value ratio
# =====================================================================

def compute_surge_exposed_value_ratio(floors, surge_classes, config):
    """Compute the fraction of building value exposed to surge."""
    floors = np.nan_to_num(np.asarray(floors, dtype=np.float64), nan=1.0)
    np.clip(floors, 1.0, None, out=floors)
    surge_classes = np.asarray(surge_classes, dtype=object)
    ratios = np.ones_like(floors, dtype=np.float64)
    floor_eq = getattr(config, "SURGE_EXPOSED_FLOOR_EQUIV", {})
    min_r = getattr(config, "SURGE_EXPOSED_VALUE_MIN_RATIO", {})
    max_r = getattr(config, "SURGE_EXPOSED_VALUE_MAX_RATIO", {})
    full_classes = {"low_rise"}
    for sc in np.unique(surge_classes):
        m = surge_classes == sc
        if sc in full_classes:
            ratios[m] = 1.0; continue
        eq = float(floor_eq.get(sc, 1.0))
        ratios[m] = np.clip(eq / floors[m], float(min_r.get(sc, 0.0)), float(max_r.get(sc, 1.0)))
    return np.clip(ratios, 0.0, 1.0)
