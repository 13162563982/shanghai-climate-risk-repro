# === 06_defense_sensitivity.py ===
# Step 6: Defense Profile Sensitivity — EAL + building hazard metrics
# Depends on: 01-05 outputs
# Outputs:
#   results/defense_sensitivity/defense_profile_eal.csv
#   results/defense_sensitivity/hazard_metrics/hazard_metrics_{scenario}_{profile}.npz

import gc
import importlib.util
import pickle
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
from scipy import sparse
from tqdm import tqdm
import warnings
warnings.filterwarnings("ignore")

_config_path = Path(__file__).resolve().parent / "00_config.py"
_spec = importlib.util.spec_from_file_location("config", _config_path)
config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config)
config.init_environment()

from climate_functions import (
    setup_logger, save_intermediate,
    compute_surge_exposed_value_ratio, compute_coastal_inundation_depth,
    build_huangpu_proximity_template, assign_surge_hybrid_zones,
)

from climada.hazard import Hazard
from climada.entity.exposures import Exposures

def _scenario_tag(name):
    return name.lower().replace("ssp2-4.5", "ssp245").replace("ssp5-8.5", "ssp585").replace(" ", "_")


if __name__ == "__main__":
    logger = setup_logger("06_defense_sensitivity", config.LOGS_DIR)
    t0 = time.time()

    profiles = getattr(config, "DEFENSE_PROFILES", [])
    if not profiles:
        logger.error("No DEFENSE_PROFILES defined in config")
        raise ValueError("No DEFENSE_PROFILES")
    logger.info(f"Defense profiles: {[p['profile_name'] for p in profiles]}")

    # ── Load shared data ─────────────────────────────────────────────
    bldg = pd.read_parquet(config.BUILDING_SKELETON_PARQUET)
    n_buildings = len(bldg)
    values = bldg["value"].values.astype(np.float64)
    impf_tc_ids = bldg["impf_TC"].values.astype(int)
    impf_ss_ids = bldg["impf_SS"].values.astype(int)
    districts = bldg["district"].fillna("unknown").astype(str).values
    building_categories = bldg["building_category"].fillna("B_new").astype(str).values
    surge_classes = bldg["surge_class"].fillna("mid_rise").astype(str).values
    estimated_floors = bldg["estimated_floors"].fillna(1.0).astype(float).values
    building_ids = bldg["building_id"].values if "building_id" in bldg.columns else np.arange(n_buildings)
    bldg_lons = bldg["centroid_lon"].values
    bldg_lats = bldg["centroid_lat"].values

    with open(config.IMPF_SET_TC_PKL, "rb") as f:
        impf_set_tc = pickle.load(f)
    with open(config.IMPF_SET_SS_PKL, "rb") as f:
        impf_set_ss = pickle.load(f)
    tc_funcs = {f.id: f for f in impf_set_tc.get_func(haz_type="TC")}
    ss_funcs = {f.id: f for f in impf_set_ss.get_func(haz_type="SS")}

    delta_df = pd.read_csv(config.DELTA_ISR_CSV)
    delta_dict = dict(zip(delta_df["district"], delta_df["delta_isr"]))
    delta_per_bldg = np.array([delta_dict.get(d, 0.0) for d in districts], dtype=np.float64)
    kappa_per_bldg = np.array(
        [config.KAPPA.get(config.CATEGORY_TO_SURGE_CLASS.get(str(c), "mid_rise"), 0.4)
         for c in building_categories], dtype=np.float64)
    surge_theta = compute_surge_exposed_value_ratio(estimated_floors, surge_classes, config)
    surge_values = values * surge_theta

    svi_df = pd.read_csv(config.SVI_CSV)
    svi_dict = dict(zip(svi_df["district"], svi_df["SVI"]))
    alpha_dict = {}
    if config.ALPHA_TEMP_CSV.exists():
        a_csv = pd.read_csv(config.ALPHA_TEMP_CSV)
        yr_col = [c for c in a_csv.columns if "year" in c.lower()]
        al_col = [c for c in a_csv.columns if "alpha" in c.lower()]
        if yr_col and al_col:
            alpha_dict = dict(zip(a_csv[yr_col[0]].astype(int), a_csv[al_col[0]].astype(float)))
    alpha_mean = float(np.mean(list(alpha_dict.values()))) if alpha_dict else 1.0

    building_elevation = np.load(str(config.BUILDING_ELEVATION_NPY))
    building_coast_distance = np.load(str(config.BUILDING_COAST_DISTANCE_NPY))
    twl_synth = np.load(str(config.TWL_VEC_SYNTH_NPY))
    twl_hist = np.load(str(config.TWL_VEC_HIST_NPY))

    unique_districts = sorted(set(districts))
    n_districts = len(unique_districts)
    district_to_idx = {d: i for i, d in enumerate(unique_districts)}
    bldg_district_idx = np.array([district_to_idx[d] for d in districts], dtype=int)
    D_dense = sparse.csc_matrix(
        (np.ones(n_buildings, dtype=np.float64),
         (np.arange(n_buildings), bldg_district_idx)),
        shape=(n_buildings, n_districts)).toarray()
    svi_vec = np.array([svi_dict.get(d, 0.0) for d in unique_districts], dtype=np.float64)

    exp_gdf = gpd.GeoDataFrame(
        {"value": values, "impf_TC": impf_tc_ids, "impf_SS": impf_ss_ids},
        geometry=gpd.points_from_xy(bldg_lons, bldg_lats), crs=config.CRS_STANDARD)
    exp = Exposures(exp_gdf)

    unique_impf_tc = sorted(set(impf_tc_ids))
    unique_impf_ss = sorted(set(impf_ss_ids))
    EVT_BATCH = 200
    tc_wind_thresh = config.DISTRICT_TC_EVENT_COUNT_WIND_THRESHOLD_MPS
    surge_depth_thresh = config.DISTRICT_SURGE_EVENT_COUNT_DEPTH_THRESHOLD_M

    # ── Pre-load Huangpu templates per profile tag ───────────────────
    hp_templates = {}
    for profile in profiles:
        tag = profile.get("huangpu_template_scenario_tag", "90m_def_gap")
        if tag not in hp_templates:
            hp_templates[tag] = build_huangpu_proximity_template(
                bldg_lons, bldg_lats, config, district_names=districts,
                scenario_tag=tag, logger=logger)

    # ── Scenario definitions (use synth tracks for all) ──────────────
    all_scenarios = [
        {"name": "historical", "haz_tc_path": config.HAZ_TC_SYNTH_HDF5,
         "twl_base": twl_synth, "slr": 0.0},
        {"name": "SSP2-4.5", "haz_tc_path": config.HAZ_TC_SSP245_HDF5,
         "twl_base": twl_synth, "slr": config.SSP_SEA_LEVEL_RISE_2050["SSP2-4.5"]},
        {"name": "SSP5-8.5", "haz_tc_path": config.HAZ_TC_SSP585_HDF5,
         "twl_base": twl_synth, "slr": config.SSP_SEA_LEVEL_RISE_2050["SSP5-8.5"]},
    ]

    all_eal_records = []

    for scenario in tqdm(all_scenarios, desc="Scenarios"):
        sc_name = scenario["name"]
        if not scenario["haz_tc_path"].exists():
            logger.warning(f"Skipping {sc_name}: missing {scenario['haz_tc_path'].name}")
            continue

        logger.info(f"{'='*60}")
        logger.info(f"Scenario: {sc_name}, SLR={scenario['slr']}m")

        haz_TC = Hazard.from_hdf5(str(scenario["haz_tc_path"]))
        n_events = haz_TC.event_id.shape[0]
        event_freq = haz_TC.frequency
        twl_vec = scenario["twl_base"] + scenario["slr"]

        if n_events != len(twl_vec):
            raise ValueError(f"Event count mismatch: TC={n_events}, TWL={len(twl_vec)}")

        exp.assign_centroids(haz_TC)
        centr_tc = exp.gdf[f"centr_{haz_TC.haz_type}"].values.astype(int)

        # Precompute MDR_wind (independent of defense profile)
        I_tc_bldg = haz_TC.intensity.tocsc()[:, centr_tc].tocsr()

        # Building-level TC metrics (computed once per scenario)
        tc_axis_max = I_tc_bldg.max(axis=0)
        tc_max_wind_bldg = np.asarray(tc_axis_max.toarray()).ravel().astype(np.float32) if hasattr(tc_axis_max, "toarray") else np.asarray(tc_axis_max).ravel().astype(np.float32)
        tc_hit_sparse = I_tc_bldg.copy()
        tc_hit_sparse.data = (tc_hit_sparse.data >= tc_wind_thresh).astype(np.uint8)
        tc_hit_sparse.eliminate_zeros()
        tc_event_count_bldg = np.asarray(tc_hit_sparse.sum(axis=0)).ravel().astype(np.uint16)

        # Pre-compute impact-function column masks (reused across batches)
        tc_col_masks = {impf_id: (impf_tc_ids == impf_id) for impf_id in unique_impf_tc}
        ss_col_masks = {impf_id: (impf_ss_ids == impf_id) for impf_id in unique_impf_ss}

        # ── Pre-compute MDR_wind for ALL batches (shared across profiles) ──
        n_batches = (n_events + EVT_BATCH - 1) // EVT_BATCH
        mdr_w_cache = {}  # batch_start → mdr_w array
        wind_dist_cache = {}  # batch_start → wind district aggregation

        logger.info(f"  Pre-computing wind MDR for {n_batches} batches...")
        for b_start in range(0, n_events, EVT_BATCH):
            b_end = min(b_start + EVT_BATCH, n_events)
            mdr_w = I_tc_bldg[b_start:b_end].toarray().astype(np.float64)
            for impf_id in unique_impf_tc:
                col_mask = tc_col_masks[impf_id]
                if col_mask.any():
                    mdr_w[:, col_mask] = tc_funcs[impf_id].calc_mdr(mdr_w[:, col_mask])
            mdr_w_cache[b_start] = mdr_w
            wind_dist_cache[b_start] = (mdr_w * values[np.newaxis, :]) @ D_dense

        for profile in tqdm(profiles, desc=f"  {sc_name} profiles", leave=False):
            prof_name = profile["profile_name"]
            tag = profile.get("huangpu_template_scenario_tag", "90m_def_gap")
            hp_template = hp_templates[tag]
            hp_zones = assign_surge_hybrid_zones(
                building_coast_distance, river_template=hp_template,
                district_names=districts, config=config)

            loss_all_dist = np.zeros((n_events, n_districts), dtype=np.float64)
            wind_all_dist = np.zeros((n_events, n_districts), dtype=np.float64)
            surge_base_all_dist = np.zeros((n_events, n_districts), dtype=np.float64)
            surge_max_depth_bldg = np.zeros(n_buildings, dtype=np.float32)
            surge_event_count_bldg = np.zeros(n_buildings, dtype=np.uint16)

            for b_start in range(0, n_events, EVT_BATCH):
                b_end = min(b_start + EVT_BATCH, n_events)
                bs = b_end - b_start

                # Reuse pre-computed wind MDR
                mdr_w = mdr_w_cache[b_start]

                h_base = compute_coastal_inundation_depth(
                    twl_vec[b_start:b_end], building_elevation, building_coast_distance,
                    config, river_template=hp_template,
                    hybrid_zones=hp_zones, defense_profile=profile)

                surge_hit = h_base >= surge_depth_thresh
                surge_event_count_bldg += surge_hit.sum(axis=0).astype(np.uint16)
                surge_max_depth_bldg = np.maximum(surge_max_depth_bldg, h_base.max(axis=0).astype(np.float32))

                h_eff = h_base * (1.0 + delta_per_bldg) * (1.0 + kappa_per_bldg * mdr_w)
                np.maximum(h_eff, 0.0, out=h_eff)

                mdr_s = np.zeros((bs, n_buildings), dtype=np.float64)
                for impf_id in unique_impf_ss:
                    col_mask = ss_col_masks[impf_id]
                    if col_mask.any():
                        mdr_s[:, col_mask] = ss_funcs[impf_id].calc_mdr(h_eff[:, col_mask])

                mdr_s_base = np.zeros((bs, n_buildings), dtype=np.float64)
                for impf_id in unique_impf_ss:
                    col_mask = ss_col_masks[impf_id]
                    if col_mask.any():
                        mdr_s_base[:, col_mask] = ss_funcs[impf_id].calc_mdr(h_base[:, col_mask])

                del h_base, h_eff

                wind_batch = wind_dist_cache[b_start]
                surge_base_batch = (mdr_s_base * surge_values[np.newaxis, :]) @ D_dense
                surge_comp_adjust = mdr_s - mdr_w * mdr_s
                loss_all_dist[b_start:b_end] = wind_batch + (surge_comp_adjust * surge_values[np.newaxis, :]) @ D_dense
                wind_all_dist[b_start:b_end] = wind_batch
                surge_base_all_dist[b_start:b_end] = surge_base_batch

                del mdr_s, mdr_s_base, surge_comp_adjust

            # Save hazard metrics NPZ
            metrics_path = config.DEFENSE_HAZARD_METRICS_DIR / f"hazard_metrics_{_scenario_tag(sc_name)}_{prof_name}.npz"
            np.savez_compressed(
                str(metrics_path),
                building_id=building_ids,
                scenario=np.array([sc_name]),
                defense_profile=np.array([prof_name]),
                tc_max_wind_mps=tc_max_wind_bldg,
                tc_event_count=tc_event_count_bldg,
                surge_max_depth_m=surge_max_depth_bldg,
                surge_event_count=surge_event_count_bldg,
                tc_wind_threshold_mps=np.array([tc_wind_thresh], dtype=np.float32),
                surge_depth_threshold_m=np.array([surge_depth_thresh], dtype=np.float32),
            )
            logger.info(f"  {prof_name}: metrics saved → {metrics_path.name}")

            # EAL per district
            svi_corr = 1.0 + config.GAMMA_SVI * svi_vec
            for d_idx, district in enumerate(unique_districts):
                eal_compound = float(np.sum(loss_all_dist[:, d_idx] * event_freq)) * svi_corr[d_idx] * alpha_mean
                eal_wind = float(np.sum(wind_all_dist[:, d_idx] * event_freq)) * svi_corr[d_idx] * alpha_mean
                eal_base_surge = float(np.sum(surge_base_all_dist[:, d_idx] * event_freq)) * svi_corr[d_idx] * alpha_mean
                exposure_total = float(values[districts == district].sum())

                all_eal_records.append({
                    "scenario": sc_name, "defense_profile": prof_name, "district": district,
                    "EAL_compound": eal_compound, "EAL_wind": eal_wind,
                    "EAL_surge": eal_compound - eal_wind,
                    "EAL_base_surge_only": eal_base_surge,
                    "EAL_compound_adjustment": eal_compound - eal_wind - eal_base_surge,
                    "EAL_ratio_pct": 100.0 * eal_compound / exposure_total if exposure_total > 0 else 0.0,
                    "exposure_total": exposure_total,
                    "coastal_defense_crest_m": profile.get("coastal_defense_crest_m", 0.0),
                    "slr_offset_m": scenario["slr"],
                })

            del loss_all_dist, wind_all_dist, surge_base_all_dist

        del haz_TC, I_tc_bldg, mdr_w_cache, wind_dist_cache
        gc.collect()

    # ── Save EAL ─────────────────────────────────────────────────────
    eal_df = pd.DataFrame(all_eal_records)
    eal_df.to_csv(str(config.DEFENSE_PROFILE_EAL_CSV), index=False, encoding="utf-8-sig")
    logger.info(f"Defense EAL: {len(eal_df)} rows → {config.DEFENSE_PROFILE_EAL_CSV.name}")

    logger.info(f"06_defense_sensitivity.py complete in {time.time()-t0:.0f}s")
