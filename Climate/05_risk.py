# === 05_risk.py ===
# Step 5: Compound MDR Risk Calculation
# Depends on: 01 (TC hazard), 02 (surge arrays), 03 (exposure), 04 (vuln)
# Core formula: MDR_compound = 1 - (1-MDR_wind)(1-MDR_surge_eff)
# Outputs:
#   results/risk_panel_all_scenarios_high_confidence.csv
#   results/tc_date_alignment_audit.csv

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
    assign_surge_hybrid_zones,
)

from climada.hazard import Hazard
from climada.entity.exposures import Exposures

if __name__ == "__main__":
    logger = setup_logger("05_risk", config.LOGS_DIR)
    t0 = time.time()

    # ── Load inputs ──────────────────────────────────────────────────
    logger.info("Loading inputs...")

    bldg = pd.read_parquet(config.BUILDING_SKELETON_PARQUET)
    n_buildings = len(bldg)
    logger.info(f"Buildings: {n_buildings:,}")

    values = bldg["value"].values.astype(np.float64)
    impf_tc_ids = bldg["impf_TC"].values.astype(int)
    impf_ss_ids = bldg["impf_SS"].values.astype(int)
    districts = bldg["district"].fillna("unknown").astype(str).values
    building_categories = bldg["building_category"].fillna("B_new").astype(str).values
    surge_classes = bldg["surge_class"].fillna("mid_rise").astype(str).values
    estimated_floors = bldg["estimated_floors"].fillna(1.0).astype(float).values
    price_source = bldg["price_source_level"].values if "price_source_level" in bldg.columns else np.ones(n_buildings)

    # Impact functions
    with open(config.IMPF_SET_TC_PKL, "rb") as f:
        impf_set_tc = pickle.load(f)
    with open(config.IMPF_SET_SS_PKL, "rb") as f:
        impf_set_ss = pickle.load(f)
    tc_funcs = {f.id: f for f in impf_set_tc.get_func(haz_type="TC")}
    ss_funcs = {f.id: f for f in impf_set_ss.get_func(haz_type="SS")}

    # Delta ISR
    delta_df = pd.read_csv(config.DELTA_ISR_CSV)
    delta_dict = dict(zip(delta_df["district"], delta_df["delta_isr"]))
    delta_per_bldg = np.array([delta_dict.get(d, 0.0) for d in districts], dtype=np.float64)

    # Kappa (wind→surge coupling)
    kappa_per_bldg = np.array(
        [config.KAPPA.get(config.CATEGORY_TO_SURGE_CLASS.get(str(c), "mid_rise"), 0.4)
         for c in building_categories], dtype=np.float64)

    # Surge exposed value fraction
    surge_theta = compute_surge_exposed_value_ratio(estimated_floors, surge_classes, config)
    surge_values = values * surge_theta

    # High confidence filter
    is_high_conf = np.isin(price_source, [1, 2])

    # SVI
    svi_df = pd.read_csv(config.SVI_CSV)
    svi_dict = dict(zip(svi_df["district"], svi_df["SVI"]))

    # Alpha temp
    alpha_dict = {}
    if config.ALPHA_TEMP_CSV.exists():
        alpha_csv = pd.read_csv(config.ALPHA_TEMP_CSV)
        yr_col = [c for c in alpha_csv.columns if "year" in c.lower()]
        al_col = [c for c in alpha_csv.columns if "alpha" in c.lower()]
        if yr_col and al_col:
            alpha_dict = dict(zip(alpha_csv[yr_col[0]].astype(int), alpha_csv[al_col[0]].astype(float)))

    # Elevation, coast distance, Huangpu template
    building_elevation = np.load(str(config.BUILDING_ELEVATION_NPY))
    building_coast_distance = np.load(str(config.BUILDING_COAST_DISTANCE_NPY))
    building_hp_template = np.load(str(config.BUILDING_HUANGPU_OVERBANK_TEMPLATE_NPY))
    hybrid_zones = assign_surge_hybrid_zones(
        building_coast_distance, river_template=building_hp_template,
        district_names=districts, config=config)

    # TWL vectors
    twl_hist = np.load(str(config.TWL_VEC_HIST_NPY))
    twl_synth = np.load(str(config.TWL_VEC_SYNTH_NPY))

    # District aggregation matrix
    unique_districts = sorted(set(districts))
    n_districts = len(unique_districts)
    district_to_idx = {d: i for i, d in enumerate(unique_districts)}
    bldg_district_idx = np.array([district_to_idx[d] for d in districts], dtype=int)
    D_dense = sparse.csc_matrix(
        (np.ones(n_buildings, dtype=np.float64),
         (np.arange(n_buildings), bldg_district_idx)),
        shape=(n_buildings, n_districts)).toarray()

    svi_vec = np.array([svi_dict.get(d, 0.0) for d in unique_districts], dtype=np.float64)

    # ── Exposure for CLIMADA centroids ───────────────────────────────
    exp_gdf = gpd.GeoDataFrame(
        {"value": values, "impf_TC": impf_tc_ids, "impf_SS": impf_ss_ids},
        geometry=gpd.points_from_xy(bldg["centroid_lon"], bldg["centroid_lat"]),
        crs=config.CRS_STANDARD)
    exp = Exposures(exp_gdf)

    # ── Scenario definitions ─────────────────────────────────────────
    scenarios = [
        {"name": "historical", "haz_tc_path": config.HAZ_TC_HIST_HDF5,
         "twl_base": twl_hist, "slr": 0.0},
        {"name": "SSP2-4.5", "haz_tc_path": config.HAZ_TC_SSP245_HDF5,
         "twl_base": twl_synth, "slr": config.SSP_SEA_LEVEL_RISE_2050["SSP2-4.5"]},
        {"name": "SSP5-8.5", "haz_tc_path": config.HAZ_TC_SSP585_HDF5,
         "twl_base": twl_synth, "slr": config.SSP_SEA_LEVEL_RISE_2050["SSP5-8.5"]},
    ]

    EVT_BATCH = 200
    unique_impf_tc = sorted(set(impf_tc_ids))
    unique_impf_ss = sorted(set(impf_ss_ids))
    # Pre-compute column masks once (reused across all scenarios and batches)
    tc_col_masks = {impf_id: (impf_tc_ids == impf_id) for impf_id in unique_impf_tc}
    ss_col_masks = {impf_id: (impf_ss_ids == impf_id) for impf_id in unique_impf_ss}
    all_panels = []
    audit_records = []

    # ── Main loop ────────────────────────────────────────────────────
    for scenario in scenarios:
        sc_name = scenario["name"]
        logger.info("=" * 60)
        logger.info(f"Scenario: {sc_name}")

        if not scenario["haz_tc_path"].exists():
            logger.warning(f"Skipping {sc_name}: TC hazard missing")
            continue

        haz_TC = Hazard.from_hdf5(str(scenario["haz_tc_path"]))
        n_events = haz_TC.event_id.shape[0]
        twl_vec = scenario["twl_base"] + scenario["slr"]

        if n_events != len(twl_vec):
            raise ValueError(f"Event count mismatch: TC={n_events}, TWL={len(twl_vec)}")

        exp.assign_centroids(haz_TC)
        centr_col = f"centr_{haz_TC.haz_type}"
        centr_tc = exp.gdf[centr_col].values.astype(int)

        event_dates_list = [date.fromordinal(int(d)) for d in haz_TC.date]
        event_years = np.array([d.year for d in event_dates_list], dtype=int)
        event_months = np.array([d.month for d in event_dates_list], dtype=int)
        event_freq = haz_TC.frequency

        # Align surge event dates (for historical audit)
        if sc_name == "historical" and config.SURGE_HEIGHTS_CSV.exists():
            surge_df = pd.read_csv(config.SURGE_HEIGHTS_CSV)
            if "event_time" in surge_df.columns:
                surge_df["event_time"] = pd.to_datetime(surge_df["event_time"], errors="coerce")
                for i, ename in enumerate(haz_TC.event_name):
                    match = surge_df[surge_df["event_id"].astype(str) == str(ename)]
                    if len(match) > 0 and pd.notna(match.iloc[0]["event_time"]):
                        et = match.iloc[0]["event_time"]
                        event_years[i] = et.year
                        event_months[i] = et.month
                        audit_records.append({
                            "event_name": str(ename),
                            "tc_date": str(event_dates_list[i]),
                            "surge_date": str(et.date()),
                            "hazard_year": et.year,
                            "hazard_month": et.month,
                        })

        logger.info(f"Events: {n_events}, years: {event_years.min()}-{event_years.max()}")

        # Unique centroid mapping for memory efficiency
        uniq_centr, centr_inv = np.unique(centr_tc, return_inverse=True)
        I_tc_uniq = haz_TC.intensity.tocsc()[:, uniq_centr].tocsr()

        # District-level accumulators
        loss_all_dist = np.zeros((n_events, n_districts), dtype=np.float64)
        loss_high_dist = np.zeros((n_events, n_districts), dtype=np.float64)
        wind_all_dist = np.zeros((n_events, n_districts), dtype=np.float64)
        surge_base_all_dist = np.zeros((n_events, n_districts), dtype=np.float64)

        values_high = values.copy()
        values_high[~is_high_conf] = 0.0
        surge_values_high = surge_values.copy()
        surge_values_high[~is_high_conf] = 0.0

        n_batches = (n_events + EVT_BATCH - 1) // EVT_BATCH
        for b_start in tqdm(range(0, n_events, EVT_BATCH),
                            desc=f"  {sc_name}", total=n_batches, unit="batch"):
            b_end = min(b_start + EVT_BATCH, n_events)
            bs = b_end - b_start

            # MDR_wind
            v_uniq = I_tc_uniq[b_start:b_end].toarray()
            v_bldg = v_uniq[:, centr_inv]
            del v_uniq
            mdr_w = np.zeros((bs, n_buildings), dtype=np.float64)
            for impf_id in unique_impf_tc:
                col_mask = tc_col_masks[impf_id]
                if col_mask.any():
                    mdr_w[:, col_mask] = tc_funcs[impf_id].calc_mdr(v_bldg[:, col_mask])
            del v_bldg

            # Bathtub inundation
            h_base = compute_coastal_inundation_depth(
                twl_vec[b_start:b_end], building_elevation, building_coast_distance,
                config, river_template=building_hp_template,
                hybrid_zones=hybrid_zones)

            # h_eff with ISR and wind-envelope amplification
            h_eff = h_base * (1.0 + delta_per_bldg) * (1.0 + kappa_per_bldg * mdr_w)
            np.maximum(h_eff, 0.0, out=h_eff)

            # MDR_surge
            mdr_s = np.zeros((bs, n_buildings), dtype=np.float64)
            for impf_id in unique_impf_ss:
                col_mask = ss_col_masks[impf_id]
                if col_mask.any():
                    mdr_s[:, col_mask] = ss_funcs[impf_id].calc_mdr(h_eff[:, col_mask])

            # MDR_surge_base (without amplification, for decomposition)
            mdr_s_base = np.zeros((bs, n_buildings), dtype=np.float64)
            for impf_id in unique_impf_ss:
                col_mask = ss_col_masks[impf_id]
                if col_mask.any():
                    mdr_s_base[:, col_mask] = ss_funcs[impf_id].calc_mdr(h_base[:, col_mask])

            del h_base, h_eff

            # Compound MDR
            mdr_c = mdr_w + mdr_s - mdr_w * mdr_s
            np.clip(mdr_c, 0.0, 1.0, out=mdr_c)
            surge_comp_adjust = mdr_c - mdr_w

            # Aggregate to district
            wind_all_dist[b_start:b_end] = (mdr_w * values[np.newaxis, :]) @ D_dense
            surge_base_all_dist[b_start:b_end] = (mdr_s_base * surge_values[np.newaxis, :]) @ D_dense
            loss_all_dist[b_start:b_end] = wind_all_dist[b_start:b_end] + \
                (surge_comp_adjust * surge_values[np.newaxis, :]) @ D_dense
            loss_high_dist[b_start:b_end] = \
                (mdr_w * values_high[np.newaxis, :]) @ D_dense + \
                (surge_comp_adjust * surge_values_high[np.newaxis, :]) @ D_dense

            del mdr_w, mdr_s, mdr_s_base, mdr_c, surge_comp_adjust

        # ── Aggregate to district-month panel ────────────────────────
        ym_key = event_years * 100 + event_months
        unique_ym, ym_inv = np.unique(ym_key, return_inverse=True)

        for idx_ym, ym_val in enumerate(unique_ym):
            yr = int(ym_val // 100)
            mo = int(ym_val % 100)
            evt_mask = ym_inv == idx_ym

            alpha_y = alpha_dict.get(yr, 1.0)

            for d_idx, district in enumerate(unique_districts):
                freq_sum = event_freq[evt_mask].sum()
                risk_total = float(loss_all_dist[evt_mask, d_idx].sum())
                risk_high = float(loss_high_dist[evt_mask, d_idx].sum())
                wind_total = float(wind_all_dist[evt_mask, d_idx].sum())
                surge_base = float(surge_base_all_dist[evt_mask, d_idx].sum())
                surge_channel = risk_total - wind_total
                compound_adj = surge_channel - surge_base
                exposure_total = float(values[districts == district].sum())

                svi_corr = 1.0 + config.GAMMA_SVI * svi_dict.get(district, 0.0)
                corrected_risk = risk_total * alpha_y * svi_corr

                all_panels.append({
                    "scenario": sc_name, "year": yr, "month": mo, "district": district,
                    "risk_total": corrected_risk,
                    "risk_wind_channel": wind_total * alpha_y * svi_corr,
                    "risk_surge_channel": surge_channel * alpha_y * svi_corr,
                    "risk_base_surge_only": surge_base * alpha_y * svi_corr,
                    "risk_compound_adjustment": compound_adj * alpha_y * svi_corr,
                    "exposure_total": exposure_total,
                    "risk_ratio": corrected_risk / exposure_total if exposure_total > 0 else 0.0,
                    "wind_share": wind_total / risk_total if risk_total > 0 else 0.0,
                    "surge_share": surge_channel / risk_total if risk_total > 0 else 0.0,
                    "compound_share": compound_adj / risk_total if risk_total > 0 else 0.0,
                    "n_events": int(evt_mask.sum()),
                    "alpha_temp": alpha_y,
                    "SVI": svi_dict.get(district, 0.0),
                    "official_district": district in config.SHANGHAI_DISTRICTS,
                })

        del haz_TC, loss_all_dist, loss_high_dist, wind_all_dist, surge_base_all_dist
        gc.collect()
        logger.info(f"  {sc_name} done")

    # ── Save outputs ─────────────────────────────────────────────────
    risk_panel = pd.DataFrame(all_panels)
    risk_panel = risk_panel.sort_values(["scenario", "year", "month", "district"]).reset_index(drop=True)
    save_intermediate(risk_panel, config.RISK_PANEL_ALL_SCENARIOS_HIGH_CONF_CSV, "risk_panel", logger)
    logger.info(f"Risk panel: {len(risk_panel):,} rows, scenarios: {risk_panel['scenario'].unique().tolist()}")

    # Also save historical-only
    hist_panel = risk_panel[risk_panel["scenario"] == "historical"]
    save_intermediate(hist_panel, config.RISK_PANEL_HIGH_CONF_CSV, "risk_panel_hist", logger)

    # Audit
    if audit_records:
        audit_df = pd.DataFrame(audit_records)
        save_intermediate(audit_df, config.TC_DATE_ALIGNMENT_CSV, "tc_date_alignment", logger)

    logger.info(f"05_risk.py complete in {time.time()-t0:.0f}s")
