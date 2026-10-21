# === 01_hazard_tc.py ===
# Step 1: TC Wind Hazard — IBTrACS → filtered tracks → synthetic → Holland2010 → SSP scaling
# Outputs:
#   intermediate/tc_tracks_shanghai.pkl, tc_tracks_all.pkl
#   intermediate/haz_TC_hist.hdf5, haz_TC_synth.hdf5, haz_TC_ssp245.hdf5, haz_TC_ssp585.hdf5
#   intermediate/alpha_temp_series.csv

import gc
import importlib.util
import pickle
import shutil
import tempfile
import time
from pathlib import Path

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

from climate_functions import setup_logger, save_intermediate, load_raster_clip_shanghai
from climada.hazard.tc_tracks import TCTracks
from climada.hazard.trop_cyclone import TropCyclone
from climada.hazard import Centroids

if __name__ == "__main__":
    logger = setup_logger("01_hazard_tc", config.LOGS_DIR)
    t0 = time.time()

    # ── Step 1.1: Load IBTrACS & filter for Shanghai ────────────────────
    logger.info("=" * 60)
    logger.info("Step 1.1: Load IBTrACS and filter TC tracks for Shanghai")
    logger.info("=" * 60)

    # netCDF4 on Windows cannot handle non-ASCII paths
    ibtracs_str = str(config.IBTRACS_FILE)
    _tmp_dir = None
    if not ibtracs_str.isascii():
        logger.info("Non-ASCII path detected — copying IBTrACS to temp dir")
        _tmp_dir = Path(tempfile.mkdtemp(prefix="ibtracs_"))
        _tmp_path = _tmp_dir / "IBTrACS.WP.v04r01.nc"
        shutil.copy2(config.IBTRACS_FILE, _tmp_path)
        ibtracs_load = str(_tmp_path)
    else:
        ibtracs_load = ibtracs_str

    logger.info("Loading TCTracks from IBTrACS (provider='usa', basin='WP')...")
    tc_all = TCTracks.from_ibtracs_netcdf(
        provider="usa", basin="WP", estimate_missing=True,
        correct_pres=True, file_name=ibtracs_load,
    )
    logger.info(f"Loaded {tc_all.size} WP tracks")

    # Filter: track passes within TC_FILTER_RADIUS_DEG of Shanghai center
    slat, slon = config.SHANGHAI_CENTER_LAT, config.SHANGHAI_CENTER_LON
    radius = config.TC_FILTER_RADIUS_DEG
    sel = []
    for idx, trk in enumerate(tqdm(tc_all.data, desc="Filter tracks")):
        d = np.sqrt((trk.lat.values - slat)**2 + (trk.lon.values - slon)**2)
        if np.nanmin(d) < radius:
            sel.append(idx)

    tc_shanghai = TCTracks()
    tc_shanghai.data = [tc_all.data[i] for i in sel]
    n_sh = tc_shanghai.size
    logger.info(f"Filtered: {n_sh}/{tc_all.size} tracks affect Shanghai")

    save_intermediate(tc_shanghai, config.TC_TRACKS_PKL, "tc_tracks_shanghai", logger)

    if _tmp_dir:
        shutil.rmtree(_tmp_dir, ignore_errors=True)

    # ── Step 1.2: Historical wind field ──────────────────────────────────
    logger.info("=" * 60)
    logger.info("Step 1.2: Historical TC wind field (Holland 2010)")
    logger.info("=" * 60)

    lon_min, lat_min, lon_max, lat_max = config.SHANGHAI_BBOX
    res = config.MODEL_RESOLUTION_DEG
    lons = np.arange(lon_min, lon_max + res / 2, res)
    lats = np.arange(lat_min, lat_max + res / 2, res)
    lon_g, lat_g = np.meshgrid(lons, lats)
    centroids = Centroids(lat=lat_g.ravel(), lon=lon_g.ravel())
    logger.info(f"Centroids grid: {len(lats)}x{len(lons)} = {centroids.size:,}")

    from pathos.pools import ProcessPool
    pool = ProcessPool(ncpus=config.N_WORKERS)

    logger.info(f"Computing historical wind field ({n_sh} tracks, {config.N_WORKERS} workers)...")
    haz_hist = TropCyclone.from_tracks(
        tracks=tc_shanghai, centroids=centroids,
        model=config.TC_WIND_MODEL, pool=pool, max_memory_gb=config.MAX_MEMORY_GB,
    )
    logger.info(f"Hist wind: {haz_hist.size} events, max={haz_hist.intensity.max():.1f} m/s")
    haz_hist.write_hdf5(str(config.HAZ_TC_HIST_HDF5))
    del haz_hist; gc.collect()

    # ── Step 1.3: Synthetic track augmentation ───────────────────────────
    logger.info("=" * 60)
    logger.info("Step 1.3: Synthetic TC tracks")
    logger.info("=" * 60)

    tc_synth = TCTracks()
    tc_synth.data = [t.copy(deep=True) for t in tc_shanghai.data]
    tc_synth.equal_timestep()
    np.random.seed(config.RANDOM_SEED)
    tc_synth.calc_perturbed_trajectories(nb_synth_tracks=config.NB_SYNTH_TRACKS)
    logger.info(f"Synthetic: {tc_synth.size} tracks (orig {n_sh} + synth)")

    logger.info("Computing synthetic wind field...")
    haz_synth = TropCyclone.from_tracks(
        tracks=tc_synth, centroids=centroids,
        model=config.TC_WIND_MODEL, pool=pool, max_memory_gb=config.MAX_MEMORY_GB,
    )
    logger.info(f"Synth wind: {haz_synth.size} events")
    haz_synth.write_hdf5(str(config.HAZ_TC_SYNTH_HDF5))

    save_intermediate(tc_synth, config.TC_TRACKS_ALL_PKL, "tc_tracks_all", logger)

    # ── Step 1.4: SSP scaling (Knutson 2020) ─────────────────────────────
    logger.info("=" * 60)
    logger.info("Step 1.4: SSP intensity scaling")
    logger.info("=" * 60)

    from climada.hazard import tc_clim_change

    for ssp_label, hdf5_path in [("SSP2-4.5", config.HAZ_TC_SSP245_HDF5),
                                  ("SSP5-8.5", config.HAZ_TC_SSP585_HDF5)]:
        rcp_col = "4.5" if "4.5" in ssp_label else "8.5"
        try:
            sc_df = tc_clim_change.get_knutson_scaling_factor(
                variable="intensity", percentile="50", basin="WP",
                baseline=(1985, 2005), yearly_steps=1,
            )
            yr = 2050 if 2050 in sc_df.index else sc_df.index[np.argmin(np.abs(sc_df.index - 2050))]
            pct = sc_df.loc[yr, rcp_col] if rcp_col in sc_df.columns else 0.0
            factor = 1.0 + pct / 100.0
        except Exception as e:
            logger.warning(f"{ssp_label} Knutson fallback to config: {e}")
            factor = config.SSP_TC_INTENSITY_FACTOR_2050.get(ssp_label, 1.0)

        logger.info(f"{ssp_label}: intensity factor = {factor:.4f}")
        haz_ssp = TropCyclone()
        haz_ssp.centroids = haz_synth.centroids
        haz_ssp.event_id = haz_synth.event_id.copy()
        haz_ssp.event_name = list(haz_synth.event_name)
        haz_ssp.date = haz_synth.date.copy()
        haz_ssp.frequency = haz_synth.frequency.copy()
        haz_ssp.intensity = haz_synth.intensity.copy() * factor
        haz_ssp.fraction = haz_synth.fraction.copy()
        haz_ssp.units = haz_synth.units
        haz_ssp.haz_type = haz_synth.haz_type
        haz_ssp.write_hdf5(str(hdf5_path))
        logger.info(f"{ssp_label} saved: {hdf5_path.name}")

    del haz_synth, tc_synth; gc.collect()

    # ── Step 1.5: Temperature trend factor alpha_temp ────────────────────
    logger.info("=" * 60)
    logger.info("Step 1.5: Temperature trend alpha_temp")
    logger.info("=" * 60)

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from scipy import stats

    # Use Tmin + Tmax monthly rasters to derive mean temperature
    tmin_dir = config.TMIN_RASTER_DIR
    tmax_dir = config.TMAX_RASTER_DIR

    def _extract_temp(tif_path, prefix, col):
        fname = tif_path.stem
        if not fname.startswith(prefix):
            return None
        parts = fname.replace(prefix, "", 1).split("-")
        if len(parts) != 2:
            return None
        try:
            info = load_raster_clip_shanghai(tif_path, config.SHANGHAI_BBOX)
            valid = ~np.isnan(info["data"])
            if valid.sum() == 0:
                return None
            return {"year": int(parts[0]), "month": int(parts[1]),
                    col: float(np.nanmean(info["data"]))}
        except Exception:
            return None

    tmin_recs, tmax_recs = [], []
    tmin_files = sorted(tmin_dir.glob("tmin_*.tif")) if tmin_dir.exists() else []
    tmax_files = sorted(tmax_dir.glob("tmax_*.tif")) if tmax_dir.exists() else []

    if tmin_files and tmax_files:
        with ThreadPoolExecutor(max_workers=config.IO_WORKERS) as ex:
            for fut in tqdm(as_completed({ex.submit(_extract_temp, p, "tmin_", "tmin"): p
                                          for p in tmin_files}),
                           total=len(tmin_files), desc="Tmin"):
                r = fut.result()
                if r: tmin_recs.append(r)
        with ThreadPoolExecutor(max_workers=config.IO_WORKERS) as ex:
            for fut in tqdm(as_completed({ex.submit(_extract_temp, p, "tmax_", "tmax"): p
                                          for p in tmax_files}),
                           total=len(tmax_files), desc="Tmax"):
                r = fut.result()
                if r: tmax_recs.append(r)

    if tmin_recs and tmax_recs:
        merged = pd.merge(pd.DataFrame(tmin_recs), pd.DataFrame(tmax_recs),
                          on=["year", "month"], how="inner")
        merged["temp_monthly_mean"] = 0.5 * (merged["tmin"] + merged["tmax"])
        annual = merged.groupby("year").agg(temp_annual_mean=("temp_monthly_mean", "mean")).reset_index()

        bl = annual.loc[(annual["year"] >= 1990) & (annual["year"] <= 2020), "temp_annual_mean"]
        baseline = bl.mean() if len(bl) else annual["temp_annual_mean"].mean()
        annual["delta_T"] = annual["temp_annual_mean"] - baseline
        slope, _, r, p, _ = stats.linregress(annual["year"], annual["delta_T"])
        annual["delta_T_trend"] = slope * (annual["year"] - annual["year"].median())
        annual["alpha_temp"] = np.exp(config.TEMP_RISK_ELASTICITY * annual["delta_T_trend"])
        logger.info(f"Temp trend: slope={slope:.6f} C/yr (p={p:.4f}), "
                    f"alpha range [{annual['alpha_temp'].min():.4f}, {annual['alpha_temp'].max():.4f}]")
    else:
        logger.warning("No Tmin/Tmax data found; alpha_temp = 1.0 for all years")
        annual = pd.DataFrame({"year": range(1980, 2025),
                                "temp_annual_mean": np.nan,
                                "delta_T": 0.0, "delta_T_trend": 0.0, "alpha_temp": 1.0})

    save_intermediate(annual[["year", "temp_annual_mean", "delta_T", "delta_T_trend", "alpha_temp"]],
                      config.ALPHA_TEMP_CSV, "alpha_temp", logger)

    # Cleanup
    try:
        pool.close(); pool.join(); pool.clear()
    except Exception:
        pass

    logger.info(f"01_hazard_tc.py complete in {time.time()-t0:.0f}s")
