# === 01a_climate_cvar.py ===
# Climate Value-at-Risk (CVaR) from Stochastic Event Set
#
# Generates synthetic TC events via CLIMADA's perturbation method,
# computes per-event wind losses, and derives rolling annual CVaR_5%.
#
# Usage:
#   python 01a_climate_cvar.py --test      # Quick validation (N=5, ~535 events)
#   python 01a_climate_cvar.py             # Full run (N=100, ~10,800 events)
#
# Output: results/shanghai_climate_cvar_monthly.csv

import argparse
import gc
import importlib.util
import os
import pickle
import sys
import time
from datetime import date
from pathlib import Path

import logging
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")
# Suppress CLIMADA's extremely verbose windfield warnings (H10 cyclostrophic)
logging.getLogger("climada.hazard.trop_cyclone").setLevel(logging.CRITICAL)
logging.getLogger("climada.hazard.trop_cyclone.trop_cyclone_windfields").setLevel(logging.CRITICAL)
logging.getLogger("climada").setLevel(logging.ERROR)

# ── Load config ──────────────────────────────────────────────────────
_config_path = Path(__file__).resolve().parent / "00_config.py"
_spec = importlib.util.spec_from_file_location("config", _config_path)
config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config)

_clim_config_path = config.CLIMATE_DIR / "00_config.py"
_clim_spec = importlib.util.spec_from_file_location("clim_config", _clim_config_path)
clim_config = importlib.util.module_from_spec(_clim_spec)
_clim_spec.loader.exec_module(clim_config)
clim_config.init_environment()

# ═══════════════════════════════════════════════════════════════════════
# Parameters
# ═══════════════════════════════════════════════════════════════════════

RANDOM_SEED_CVAR = 2024
CVAR_ALPHA = 0.05
ROLLING_WINDOW_YEARS = 5
MAX_MEMORY_GB = 14.0           # aggressive: user has 10 GB free
CVAR_OUTPUT_CSV = config.RESULTS_DIR / "shanghai_climate_cvar_monthly.csv"
INTERMEDIATE_DIR = config.OUTPUT_DIR / "intermediate"
HAZ_CACHE_PREFIX = "haz_TC_cvar"


def load_price_index():
    """Load city-level monthly housing price and compute annual price ratio."""
    import re
    xls = pd.read_excel(config.CITY_PRICE_EXCEL)
    month_cols = [str(c) for c in xls.columns if re.fullmatch(r"\d{4}-\d{2}", str(c))]
    meta = [c for c in ["省名", "省代码", "市名", "市代码"] if c in xls.columns]
    long = xls.melt(id_vars=meta, value_vars=month_cols,
                    var_name="ym", value_name="price")
    long["price"] = pd.to_numeric(long["price"], errors="coerce")
    long = long.dropna(subset=["price"]).copy()
    long["date"] = pd.to_datetime(long["ym"], format="%Y-%m", errors="coerce")
    long = long.dropna(subset=["date"]).sort_values("date").drop_duplicates("date")
    annual = long.groupby(long["date"].dt.year)["price"].mean()
    base_price = annual.iloc[-1]
    price_ratio = (annual / base_price).to_dict()
    return price_ratio


def _fmt_time(seconds):
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true",
                        help="Quick test: N=5 per track (~535 events)")
    args = parser.parse_args()

    NB_SYNTH = 5 if args.test else 100
    mode_label = "TEST (N=5)" if args.test else "FULL (N=100)"

    t0 = time.time()
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print(f"Climate CVaR  [{mode_label}]")
    print("=" * 65)
    print(f"  Memory limit : {MAX_MEMORY_GB} GB")
    print(f"  Synth/track  : {NB_SYNTH}")
    print(f"  CVaR alpha   : {CVAR_ALPHA}")
    sys.stdout.flush()

    # ═════════════════════════════════════════════════════════════════
    # Phase 1: Generate stochastic TC event set
    # ═════════════════════════════════════════════════════════════════

    haz_hdf5 = INTERMEDIATE_DIR / f"{HAZ_CACHE_PREFIX}_N{NB_SYNTH}.hdf5"

    if haz_hdf5.exists():
        print(f"\n[1/4] Loading cached hazard: {haz_hdf5.name}")
        from climada.hazard import Hazard
        haz = Hazard.from_hdf5(str(haz_hdf5))
        print(f"  -> {haz.size} events")
        sys.stdout.flush()
    else:
        print(f"\n[1/4] Generating stochastic TC event set...")
        sys.stdout.flush()

        from tqdm import tqdm
        from climada.hazard import TropCyclone, Centroids
        from climada.hazard.tc_tracks import TCTracks

        # 1a. Load historical tracks
        t1 = time.time()
        with open(str(clim_config.TC_TRACKS_PKL), "rb") as f:
            tc_hist = pickle.load(f)
        n_hist = tc_hist.size
        print(f"  Historical tracks: {n_hist}")

        # 1b. Perturbations
        print(f"  Generating {NB_SYNTH} perturbations per track...")
        sys.stdout.flush()
        tc_stoch = TCTracks()
        tc_stoch.data = [t.copy(deep=True) for t in tc_hist.data]
        tc_stoch.equal_timestep()
        np.random.seed(RANDOM_SEED_CVAR)
        tc_stoch.calc_perturbed_trajectories(nb_synth_tracks=NB_SYNTH)
        n_total = tc_stoch.size
        print(f"  Total tracks: {n_total} ({_fmt_time(time.time()-t1)})")

        # 1c. Centroid grid
        lon_min, lat_min, lon_max, lat_max = clim_config.SHANGHAI_BBOX
        res = clim_config.MODEL_RESOLUTION_DEG
        lons = np.arange(lon_min, lon_max + res / 2, res)
        lats = np.arange(lat_min, lat_max + res / 2, res)
        lon_g, lat_g = np.meshgrid(lons, lats)
        centroids = Centroids(lat=lat_g.ravel(), lon=lon_g.ravel())
        print(f"  Centroids: {centroids.size}")

        # 1d. Wind fields — all at once (same approach as Climate pipeline)
        print(f"  Computing wind fields (max_mem={MAX_MEMORY_GB}GB)...")
        sys.stdout.flush()
        t_wf = time.time()

        haz = TropCyclone.from_tracks(
            tracks=tc_stoch, centroids=centroids,
            model=clim_config.TC_WIND_MODEL,
            max_memory_gb=MAX_MEMORY_GB,
        )

        print(f"  Events: {haz.size}, max wind: {haz.intensity.max():.1f} m/s, "
              f"nnz: {haz.intensity.nnz:,} ({_fmt_time(time.time()-t_wf)})")
        haz.write_hdf5(str(haz_hdf5))
        print(f"  Cached: {haz_hdf5.name} ({_fmt_time(time.time()-t1)})")
        sys.stdout.flush()

        del tc_stoch, tc_hist
        gc.collect()

    # ═════════════════════════════════════════════════════════════════
    # Phase 2: Per-event wind losses
    # ═════════════════════════════════════════════════════════════════
    print(f"\n[2/4] Computing per-event losses...")
    sys.stdout.flush()
    from tqdm import tqdm
    from climada.entity.exposures import Exposures
    import geopandas as gpd

    bldg = pd.read_parquet(str(clim_config.BUILDING_SKELETON_PARQUET))
    n_bldg = len(bldg)
    total_exposure = bldg["value"].sum()
    print(f"  Buildings: {n_bldg:,}, exposure: {total_exposure/1e9:.1f}B CNY")

    exp_gdf = gpd.GeoDataFrame(
        {"value": bldg["value"].values.astype(np.float64),
         "impf_TC": bldg["impf_TC"].values.astype(int)},
        geometry=gpd.points_from_xy(bldg["centroid_lon"], bldg["centroid_lat"]),
        crs=clim_config.CRS_STANDARD,
    )
    exp = Exposures(exp_gdf)
    exp.assign_centroids(haz)

    with open(str(clim_config.IMPF_SET_TC_PKL), "rb") as f:
        impf_set = pickle.load(f)

    n_events = haz.size
    centr_col = f"centr_{haz.haz_type}"
    centr_tc = exp.gdf[centr_col].values.astype(int)
    values = bldg["value"].values.astype(np.float64)
    impf_tc_ids = bldg["impf_TC"].values.astype(int)
    tc_funcs = {f.id: f for f in impf_set.get_func(haz_type="TC")}
    unique_impf = sorted(set(impf_tc_ids))

    uniq_centr, centr_inv = np.unique(centr_tc, return_inverse=True)
    I_tc_uniq = haz.intensity.tocsc()[:, uniq_centr].tocsr()

    # Batch size: (batch × n_bldg × 8 bytes) should stay under ~2 GB
    # n_bldg ~ 585k → 200 events × 585k × 8 ≈ 0.9 GB
    EVT_BATCH = min(300, max(50, n_events // 4))
    at_event = np.zeros(n_events, dtype=np.float64)

    t2 = time.time()
    pbar = tqdm(total=n_events, desc="  Impact", unit="evt",
                ncols=80, file=sys.stdout)

    for b_start in range(0, n_events, EVT_BATCH):
        b_end = min(b_start + EVT_BATCH, n_events)
        bs = b_end - b_start

        v_uniq = I_tc_uniq[b_start:b_end].toarray()
        v_bldg = v_uniq[:, centr_inv]
        del v_uniq

        mdr = np.zeros((bs, n_bldg), dtype=np.float64)
        for impf_id in unique_impf:
            fn = tc_funcs[impf_id]
            mask = impf_tc_ids == impf_id
            if mask.any():
                mdr[:, mask] = fn.calc_mdr(v_bldg[:, mask])
        del v_bldg

        at_event[b_start:b_end] = (mdr * values[np.newaxis, :]).sum(axis=1)
        del mdr
        pbar.update(bs)

    pbar.close()
    print(f"  Impact done: {_fmt_time(time.time()-t2)}")
    print(f"  Loss range: {at_event.min():.0f} — {at_event.max():,.0f} CNY")
    print(f"  Non-zero: {(at_event > 0).sum()} / {n_events}")
    sys.stdout.flush()

    del I_tc_uniq
    gc.collect()

    # ═════════════════════════════════════════════════════════════════
    # Phase 3: Rolling CVaR
    # ═════════════════════════════════════════════════════════════════
    print(f"\n[3/4] Computing rolling annual CVaR...")

    event_dates = [date.fromordinal(int(d)) for d in haz.date]
    event_years = np.array([d.year for d in event_dates], dtype=int)
    del haz
    gc.collect()

    loss_ratio = at_event / total_exposure
    price_ratio_dict = load_price_index()

    all_years = sorted(set(event_years))
    year_min, year_max = min(all_years), max(all_years)
    half_w = ROLLING_WINDOW_YEARS // 2

    annual_cvar = {}
    annual_eal = {}
    annual_n_events = {}

    for yr in range(year_min, year_max + 1):
        yr_lo = max(yr - half_w, year_min)
        yr_hi = min(yr + half_w, year_max)
        mask = (event_years >= yr_lo) & (event_years <= yr_hi)
        wl = loss_ratio[mask]
        if len(wl) == 0:
            annual_cvar[yr] = 0.0
            annual_eal[yr] = 0.0
            annual_n_events[yr] = 0
            continue
        sl = np.sort(wl)[::-1]
        n_tail = max(1, int(np.ceil(len(sl) * CVAR_ALPHA)))
        cvar_raw = sl[:n_tail].mean()
        pr = price_ratio_dict.get(yr, 1.0)
        annual_cvar[yr] = float(cvar_raw * pr)
        annual_eal[yr] = float(wl.mean() * pr)
        annual_n_events[yr] = int(mask.sum())

    print(f"  CVaR years: {len(annual_cvar)}")
    print(f"  CVaR range: {min(annual_cvar.values()):.6f} — "
          f"{max(annual_cvar.values()):.6f}")

    # ═════════════════════════════════════════════════════════════════
    # Phase 4: Monthly interpolation + save
    # ═════════════════════════════════════════════════════════════════
    print(f"\n[4/4] Saving monthly CVaR series...")

    months = pd.date_range("1993-01-01", "2023-12-01", freq="MS")
    records = []
    for dt in months:
        yr = dt.year
        records.append({
            "date": dt, "year": yr, "month": dt.month,
            "cvar_annual": annual_cvar.get(yr, 0.0),
            "eal_annual": annual_eal.get(yr, 0.0),
            "n_events_window": annual_n_events.get(yr, 0),
        })
    df = pd.DataFrame(records)
    df["cvar_12m"] = (
        df["cvar_annual"]
        .rolling(12, min_periods=6, center=True)
        .mean()
    )
    df["cvar_12m"] = df["cvar_12m"].bfill().ffill()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df.to_csv(str(CVAR_OUTPUT_CSV), index=False, encoding="utf-8-sig")
    print(f"  -> {CVAR_OUTPUT_CSV.name} ({len(df)} rows)")

    # ═════════════════════════════════════════════════════════════════
    elapsed = time.time() - t0
    print("\n" + "=" * 65)
    print("SUMMARY")
    print("=" * 65)
    print(f"  Mode:     {mode_label}")
    print(f"  Events:   {n_events}")
    print(f"  Non-zero: {(at_event > 0).sum()}")
    print(f"  Exposure: {total_exposure/1e9:.1f}B CNY")
    print(f"  CVaR rng: {df['cvar_annual'].min():.6f} — "
          f"{df['cvar_annual'].max():.6f}")

    for yr in [1995, 2005, 2015, 2023]:
        rows = df[df["year"] == yr]
        if len(rows):
            r = rows.iloc[0]
            print(f"  {yr}: CVaR={r['cvar_annual']:.6f}, "
                  f"12m={r['cvar_12m']:.6f}")

    print(f"\n  Total: {_fmt_time(elapsed)}")
    if args.test:
        print(f"\n  ** TEST MODE — rerun without --test for full N=100 **")
    print("=" * 65)
