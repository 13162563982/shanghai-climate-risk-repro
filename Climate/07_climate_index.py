# === 07_climate_index.py ===
# Step 7: Shanghai Climate Risk Index (CRI)
# Framework: CRI = Hazard × Exposure × Vulnerability × (1 + κ·DamageSignal)
#
# H(t)  — monthly composite hazard (SLA, wind, precip, heat) ∈ [0,1]
# E(t)  — annual LandScan population, normalised to [0.5, 1.0]
# V(t)  — annual ISR city mean, normalised to [0.5, 1.0]
# S(t)  — EWMA-smoothed, log-transformed CLIMADA event loss signal
#
# Outputs:
#   results/shanghai_city_monthly_climate_hazard.csv
#   (columns: date, year, month, hazard_index, sla_norm, wind_norm,
#             precip_norm, heat_norm, e_norm, v_norm,
#             damage_signal, cri_raw, cri_12m, cri_index)

import hashlib
import importlib.util
import time
from pathlib import Path

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

_config_path = Path(__file__).resolve().parent / "00_config.py"
_spec = importlib.util.spec_from_file_location("config", _config_path)
config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config)
config.init_environment()

from climate_functions import setup_logger, load_raster_clip_shanghai

if __name__ == "__main__":
    logger = setup_logger("07_climate_index", config.LOGS_DIR)
    t0 = time.time()

    bbox = config.SHANGHAI_BBOX
    year_start = config.CFI_TREND_YEAR_START
    year_end = config.CFI_TREND_YEAR_END
    heat_base = config.CFI_HEAT_BASE_TEMP

    # ── Helper: extract monthly mean from raster directory ───────────
    def _extract_monthly_series(raster_dir, label):
        """Scan dir for TIF files, extract year/month from filename, compute spatial mean."""
        recs = []
        if not raster_dir.exists():
            logger.warning(f"{label} directory not found: {raster_dir}")
            return pd.DataFrame(columns=["year", "month", "value"])

        tifs = sorted(raster_dir.glob("*.tif"))
        logger.info(f"{label}: {len(tifs)} rasters")
        for tif in tifs:
            stem = tif.stem
            parts = [p for p in stem.replace("_", "-").split("-") if p.isdigit()]
            if len(parts) >= 2:
                yr, mo = int(parts[-2]), int(parts[-1])
                if yr < 1900 or yr > 2100 or mo < 1 or mo > 12:
                    digits = "".join(c for c in stem if c.isdigit())
                    if len(digits) >= 6:
                        yr, mo = int(digits[:4]), int(digits[4:6])
            elif len(parts) == 1 and len(parts[0]) >= 6:
                yr, mo = int(parts[0][:4]), int(parts[0][4:6])
            else:
                continue

            if yr < year_start or yr > year_end:
                continue
            if mo < 1 or mo > 12:
                continue

            try:
                r = load_raster_clip_shanghai(tif, bbox)
                data = r["data"]
                valid = data[np.isfinite(data)]
                if len(valid) > 0:
                    recs.append({"year": yr, "month": mo, "value": float(np.nanmean(valid))})
            except Exception as e:
                logger.warning(f"  {label} {tif.name}: {e}")

        df = pd.DataFrame(recs)
        if len(df) > 0:
            df = df.groupby(["year", "month"], as_index=False)["value"].mean()
        return df

    # ═════════════════════════════════════════════════════════════════
    # PART 1: Hazard Index H(t) — monthly composite [0,1]
    # ═════════════════════════════════════════════════════════════════
    logger.info("=" * 60)
    logger.info("PART 1: Extracting monthly climate hazard variables")
    logger.info("=" * 60)

    sla_series = pd.DataFrame()
    if config.SLA_MONTHLY_CSV.exists():
        sla_df = pd.read_csv(config.SLA_MONTHLY_CSV)
        sla_series = sla_df[["year", "month"]].copy()
        sla_series["value"] = sla_df["SLA_mean_m"]
        logger.info(f"SLA: loaded from pre-computed, {len(sla_series)} months")
    else:
        sla_series = _extract_monthly_series(config.SLA_DIR, "SLA")

    wind_series = _extract_monthly_series(config.WIND_RASTER_DIR, "Wind")
    precip_series = _extract_monthly_series(config.PRECIP_RASTER_DIR, "Precip")
    tmax_series = _extract_monthly_series(config.TMAX_RASTER_DIR, "Tmax")

    # Create full date spine
    full_dates = pd.DataFrame({
        "date": pd.date_range(f"{year_start}-01-01", f"{year_end}-12-01", freq="MS")
    })
    full_dates["year"] = full_dates["date"].dt.year
    full_dates["month"] = full_dates["date"].dt.month

    def _merge_series(spine, series_df, col_name):
        if series_df is None or len(series_df) == 0:
            spine[col_name] = np.nan
            return spine
        merged = spine.merge(
            series_df.rename(columns={"value": col_name}),
            on=["year", "month"], how="left")
        merged[col_name] = merged[col_name].interpolate("linear")
        return merged

    panel = full_dates.copy()
    panel = _merge_series(panel, sla_series, "sla_raw")
    panel = _merge_series(panel, wind_series, "wind_raw")
    panel = _merge_series(panel, precip_series, "precip_raw")
    panel = _merge_series(panel, tmax_series, "tmax_raw")

    def _minmax_norm(arr):
        a = arr.copy()
        lo, hi = np.nanpercentile(a, [1, 99])
        if hi <= lo:
            return np.zeros_like(a)
        return np.clip((a - lo) / (hi - lo), 0, 1)

    panel["sla_norm"] = _minmax_norm(panel["sla_raw"].values)
    panel["wind_norm"] = _minmax_norm(panel["wind_raw"].values)
    panel["precip_norm"] = _minmax_norm(panel["precip_raw"].values)

    if "tmax_raw" in panel.columns and panel["tmax_raw"].notna().any():
        heat_excess = np.maximum(panel["tmax_raw"].values - heat_base, 0.0)
        panel["heat_norm"] = _minmax_norm(heat_excess)
    else:
        panel["heat_norm"] = 0.0

    w = config.CFI_WEIGHT_SLA + config.CFI_WEIGHT_WIND + config.CFI_WEIGHT_PRECIP + config.CFI_WEIGHT_HEAT
    panel["hazard_index"] = (
        config.CFI_WEIGHT_SLA * panel["sla_norm"] +
        config.CFI_WEIGHT_WIND * panel["wind_norm"] +
        config.CFI_WEIGHT_PRECIP * panel["precip_norm"] +
        config.CFI_WEIGHT_HEAT * panel["heat_norm"]
    ) / w
    panel["hazard_index"] = panel["hazard_index"].fillna(0.0)

    logger.info(f"  H(t): mean={panel['hazard_index'].mean():.4f}, "
                f"range=[{panel['hazard_index'].min():.4f}, {panel['hazard_index'].max():.4f}]")

    # ═════════════════════════════════════════════════════════════════
    # PART 2: Exposure Index E(t) — LandScan annual pop → [floor, 1.0]
    # ═════════════════════════════════════════════════════════════════
    logger.info("=" * 60)
    logger.info("PART 2: Building time-varying Exposure index (LandScan)")
    logger.info("=" * 60)

    e_floor = config.CRI_EXPOSURE_FLOOR
    pop_records = []
    for yr in range(2000, 2025):
        tif = config.LANDSCAN_DIR / f"立方数据学社_landscan_{yr}.tif"
        if tif.exists():
            try:
                r = load_raster_clip_shanghai(tif, bbox)
                data = r["data"]
                total_pop = float(np.nansum(data[data > 0]))
                pop_records.append({"year": yr, "population": total_pop})
            except Exception as e:
                logger.warning(f"  LandScan {yr}: {e}")

    pop_df = pd.DataFrame(pop_records)
    logger.info(f"  LandScan population: {len(pop_df)} years ({pop_df['year'].min()}-{pop_df['year'].max()})")

    pop_min = pop_df["population"].min()
    pop_max = pop_df["population"].max()
    pop_df["e_norm"] = e_floor + (1.0 - e_floor) * (pop_df["population"] - pop_min) / max(pop_max - pop_min, 1)

    # Extend to full year range with extrapolation
    all_years = pd.DataFrame({"year": range(year_start, year_end + 1)})
    pop_annual = all_years.merge(pop_df[["year", "e_norm"]], on="year", how="left")
    # Before 2000: fill with floor value
    pop_annual["e_norm"] = pop_annual["e_norm"].interpolate("linear")
    pop_annual["e_norm"] = pop_annual["e_norm"].bfill().ffill()
    pop_annual.loc[pop_annual["year"] < pop_df["year"].min(), "e_norm"] = e_floor

    # Merge to monthly panel (step function within year)
    panel = panel.merge(pop_annual[["year", "e_norm"]], on="year", how="left")
    panel["e_norm"] = panel["e_norm"].ffill().bfill()
    logger.info(f"  E(t): range=[{panel['e_norm'].min():.4f}, {panel['e_norm'].max():.4f}]")

    # ═════════════════════════════════════════════════════════════════
    # PART 3: Vulnerability Index V(t) — ISR city mean → [floor, 1.0]
    # ═════════════════════════════════════════════════════════════════
    logger.info("=" * 60)
    logger.info("PART 3: Building time-varying Vulnerability index (ISR)")
    logger.info("=" * 60)

    v_floor = config.CRI_VULNERABILITY_FLOOR
    isr = pd.read_csv(str(config.ISR_PANEL_CSV))
    isr_city = isr.groupby("year", as_index=False)["mean_isr"].mean()

    isr_min = isr_city["mean_isr"].min()
    isr_max = isr_city["mean_isr"].max()
    isr_city["v_norm"] = v_floor + (1.0 - v_floor) * (isr_city["mean_isr"] - isr_min) / max(isr_max - isr_min, 1e-9)

    # Extend to full year range
    isr_annual = all_years.merge(isr_city[["year", "v_norm"]], on="year", how="left")
    isr_annual["v_norm"] = isr_annual["v_norm"].interpolate("linear")
    isr_annual["v_norm"] = isr_annual["v_norm"].bfill().ffill()

    panel = panel.merge(isr_annual[["year", "v_norm"]], on="year", how="left")
    panel["v_norm"] = panel["v_norm"].ffill().bfill()
    logger.info(f"  V(t): range=[{panel['v_norm'].min():.4f}, {panel['v_norm'].max():.4f}]")

    # ═════════════════════════════════════════════════════════════════
    # PART 4: CLIMADA Damage Signal S(t) — EWMA-smoothed event loss
    # ═════════════════════════════════════════════════════════════════
    logger.info("=" * 60)
    logger.info("PART 4: Building CLIMADA damage signal (EWMA-smoothed)")
    logger.info("=" * 60)

    alpha = config.CRI_EWMA_ALPHA
    kappa = config.CRI_DAMAGE_KAPPA

    # Load risk panel → city-level monthly loss
    risk_csv = config.RISK_PANEL_ALL_SCENARIOS_HIGH_CONF_CSV
    damage_series = pd.DataFrame({"year": panel["year"], "month": panel["month"]})
    damage_series["risk_total"] = 0.0

    if risk_csv.exists():
        risk = pd.read_csv(str(risk_csv))
        hist = risk[risk["scenario"] == "historical"].copy()
        city_risk = hist.groupby(["year", "month"], as_index=False)["risk_total"].sum()
        damage_series = damage_series.merge(
            city_risk, on=["year", "month"], how="left", suffixes=("_old", "")
        )
        if "risk_total_old" in damage_series.columns:
            damage_series["risk_total"] = damage_series["risk_total"].fillna(damage_series["risk_total_old"])
            damage_series.drop(columns=["risk_total_old"], inplace=True)
        damage_series["risk_total"] = damage_series["risk_total"].fillna(0.0)
        logger.info(f"  CLIMADA risk panel loaded: {(damage_series['risk_total'] > 0).sum()} event months")
    else:
        logger.warning("  Risk panel not found — damage signal will be zero")

    # EAL-normalise: D_raw = monthly_loss / (EAL / 12)
    total_loss = damage_series["risk_total"].sum()
    n_years = year_end - year_start + 1
    eal_monthly = total_loss / (n_years * 12) if n_years > 0 else 1.0
    eal_monthly = max(eal_monthly, 1.0)  # safety

    # Log transform to compress extremes
    d_raw = damage_series["risk_total"].values / eal_monthly
    d_log = np.log1p(d_raw)

    # EWMA smoothing
    s = np.zeros_like(d_log)
    for i in range(len(d_log)):
        if i == 0:
            s[i] = (1 - alpha) * d_log[i]
        else:
            s[i] = alpha * s[i - 1] + (1 - alpha) * d_log[i]

    # Normalize S to [0, 1]
    s_max = s.max() if s.max() > 0 else 1.0
    s_norm = s / s_max

    panel["damage_signal"] = s_norm
    panel["risk_total"] = damage_series["risk_total"].values

    n_events = (damage_series["risk_total"] > 0).sum()
    logger.info(f"  Damage EWMA: alpha={alpha}, peak S_norm={s_norm.max():.4f}")
    logger.info(f"  EAL={total_loss/n_years:.2e}/yr, kappa={kappa}")

    # ═════════════════════════════════════════════════════════════════
    # PART 5: Composite CRI = H × E × V × (1 + κ·S)
    # ═════════════════════════════════════════════════════════════════
    logger.info("=" * 60)
    logger.info("PART 5: Computing Climate Risk Index")
    logger.info("=" * 60)

    panel["cri_raw"] = (
        panel["hazard_index"]
        * panel["e_norm"]
        * panel["v_norm"]
        * (1.0 + kappa * panel["damage_signal"])
    )

    # 12-month rolling mean
    panel["cri_12m"] = panel["cri_raw"].rolling(12, min_periods=6).mean()

    # Base-100 index: first valid 12m average = 100
    first_valid_idx = panel["cri_12m"].first_valid_index()
    base_value = panel.loc[first_valid_idx, "cri_12m"] if first_valid_idx is not None else 1.0
    base_value = max(base_value, 1e-12)
    panel["cri_index"] = config.CRI_BASE_INDEX * panel["cri_12m"] / base_value

    logger.info(f"  CRI raw: mean={panel['cri_raw'].mean():.4f}, "
                f"range=[{panel['cri_raw'].min():.4f}, {panel['cri_raw'].max():.4f}]")
    logger.info(f"  CRI index (base {config.CRI_BASE_INDEX:.0f}): "
                f"start={panel['cri_index'].dropna().iloc[0]:.1f}, "
                f"end={panel['cri_index'].dropna().iloc[-1]:.1f}")

    # ═════════════════════════════════════════════════════════════════
    # SAVE historical CRI
    # ═════════════════════════════════════════════════════════════════
    out_cols = ["date", "year", "month", "hazard_index",
                "sla_norm", "wind_norm", "precip_norm", "heat_norm",
                "e_norm", "v_norm", "damage_signal", "risk_total",
                "cri_raw", "cri_12m", "cri_index"]
    out = panel[out_cols].copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(str(config.CFI_HAZARD_CITY_CSV), index=False, encoding="utf-8-sig")
    logger.info(f"Historical CRI: {len(out)} months → {config.CFI_HAZARD_CITY_CSV.name}")

    # ═════════════════════════════════════════════════════════════════
    # PART 6: SDE Monte Carlo Forward Projection (2024 → 2050)
    #
    # H(t): Ornstein-Uhlenbeck + seasonal + trend drift
    #        dH = θ(μ(t) − H)dt + σ_H dW
    # E(t): Logistic-GBM  dE = rE(1−E/K)dt + σ_E E(1−E/K) dW
    # V(t): Logistic-GBM  dV = r_V V(1−V/K)dt + σ_V V(1−V/K) dW
    # S(t): Compound Poisson  N~Pois(λ), L~LogNormal(μ_log,σ_log)
    # ═════════════════════════════════════════════════════════════════
    logger.info("=" * 60)
    logger.info("PART 6: SDE Monte Carlo Projection → %d",
                config.CRI_PROJECTION_END_YEAR)
    logger.info("=" * 60)

    from scipy import stats as sp_stats

    N_SIM = config.CRI_N_SIM
    proj_end = config.CRI_PROJECTION_END_YEAR
    n_proj_months = (proj_end - year_end) * 12
    dt_mo = 1.0          # monthly time step
    dt_yr = 1.0 / 12.0   # fraction of year

    # ── 6a. H(t) OU parameters ───────────────────────────────────────
    h_vals = panel["hazard_index"].values

    # Fit OU params from RECENT period (last 10 years) for local dynamics.
    # Rolling-window analysis shows recent θ≈0.47, σ≈0.12 vs full-series
    # θ≈0.43, σ≈0.11; using recent period avoids regime-shift bias.
    recent_fit_years = 10
    recent_fit_mask = panel["year"] >= (year_end - recent_fit_years + 1)
    h_recent = panel.loc[recent_fit_mask, "hazard_index"].values
    dh = np.diff(h_recent)
    slope_h, intercept_h, _, _, _ = sp_stats.linregress(h_recent[:-1], dh)
    theta_h = float(-slope_h)
    sigma_h = float(np.std(dh - intercept_h - slope_h * h_recent[:-1]))

    # OU mean-reversion target: use RECENT level (last 5 years)
    # to avoid drop at projection start.  The 31-year average is biased
    # low by early decades when E and V were smaller.
    recent_years = 5
    recent_mask = panel["year"] >= (year_end - recent_years + 1)
    mu_h_long = float(panel.loc[recent_mask, "hazard_index"].mean())

    # 12-month seasonal cycle (fit from recent period too for consistency)
    h_seasonal = panel.loc[recent_mask].groupby("month")["hazard_index"].mean()
    h_seasonal_anom = (h_seasonal - h_seasonal.mean()).values  # length-12 array

    # Trend drift from recent period — rolling analysis confirms
    # recent drift ≈ +0.008/yr (vs near-zero full-series average)
    h_annual_recent = panel.loc[recent_fit_mask].groupby("year")["hazard_index"].mean()
    h_drift_per_yr, _ = np.polyfit(h_annual_recent.index.values,
                                    h_annual_recent.values, 1)
    h_drift_per_mo = h_drift_per_yr / 12.0

    logger.info(f"  H-OU: θ={theta_h:.4f}, μ_recent={mu_h_long:.4f}, "
                f"σ={sigma_h:.4f}, drift={h_drift_per_yr:+.5f}/yr")

    # ── 6b. E(t) Logistic-GBM parameters ─────────────────────────────
    e_annual = pop_annual[pop_annual["year"] >= 2000].copy()
    e_vals = e_annual["e_norm"].values
    e_log_growth = np.diff(np.log(np.maximum(e_vals, 1e-6)))
    r_e = float(e_log_growth.mean())     # ~0.023/yr
    sigma_e = float(e_log_growth.std())  # ~0.072/yr
    K_e = 1.0
    E_last = float(panel["e_norm"].iloc[-1])
    logger.info(f"  E-Logistic: r={r_e:.4f}/yr, σ={sigma_e:.4f}, E0={E_last:.4f}")

    # ── 6c. V(t) Logistic-GBM parameters ─────────────────────────────
    v_annual = isr_annual[isr_annual["year"] >= 1990].copy()
    v_vals = v_annual["v_norm"].values
    v_log_growth = np.diff(np.log(np.maximum(v_vals, 1e-6)))
    r_v = float(v_log_growth.mean())     # ~0.016/yr
    sigma_v = float(v_log_growth.std())  # ~0.006/yr
    K_v = 1.0
    V_last = float(panel["v_norm"].iloc[-1])
    logger.info(f"  V-Logistic: r={r_v:.4f}/yr, σ={sigma_v:.4f}, V0={V_last:.4f}")

    # ── 6d. S(t) Compound Poisson parameters ─────────────────────────
    risk_vals = panel["risk_total"].values
    nonzero_risk = risk_vals[risk_vals > 0]
    n_events = len(nonzero_risk)
    n_months_total = len(risk_vals)
    lam_monthly = n_events / n_months_total  # ~0.067 events/month
    if n_events > 2:
        log_severity = np.log(nonzero_risk)
        mu_log_sev = float(log_severity.mean())
        sigma_log_sev = float(log_severity.std())
    else:
        mu_log_sev, sigma_log_sev = 18.0, 3.0

    # EWMA constants from PART 4
    ewma_state_last = float(panel["damage_signal"].iloc[-1])

    logger.info(f"  S-Poisson: λ={lam_monthly:.4f}/mo, "
                f"μ_log={mu_log_sev:.2f}, σ_log={sigma_log_sev:.2f}")

    # ── 6e. Monte Carlo simulation ───────────────────────────────────
    # Slow climate-regime modulator Z(t): ENSO-like multi-year oscillations
    # (Chan 2000).  2-factor: fast OU for H + slow OU modulator Z(t).
    # Z shared across scenarios (same internal variability, different forcing).
    # theta_slow: spectral analysis of detrended H(t) finds dominant
    # low-frequency peak at 4.4yr (53 months) — ENSO-like modulation.
    # θ_slow = ln(2) / (period/2) ≈ 0.026
    theta_slow = 0.026
    # sigma_slow: data-derived from 36-month low-frequency H variability
    h_36m = pd.Series(h_vals).rolling(36, min_periods=12).mean().dropna()
    sigma_slow = float(np.diff(h_36m.values).std())
    logger.info(f"  Z-slow: θ_slow={theta_slow:.3f}, σ_slow={sigma_slow:.5f}")

    proj_records = []
    hist_tail_raw = panel["cri_raw"].values[-11:]  # for 12-mo MA warmup

    # Deseasonalise H_last: remove the December seasonal component so
    # the OU operates on the slowly-varying mean, not a seasonal trough.
    last_month_idx = (int(panel["month"].iloc[-1]) - 1) % 12
    H_deseason_last = float(h_vals[-1]) - h_seasonal_anom[last_month_idx]

    # Pre-generate shared Z-noise and fast H-noise for all simulations
    # so scenarios share the same internal climate variability
    rng_shared = np.random.RandomState(42)
    Z_noise_all = rng_shared.randn(N_SIM, n_proj_months)
    H_noise_all = rng_shared.randn(N_SIM, n_proj_months)

    scenario_results = {}
    for scenario, h_drift_mult in config.CRI_SSP_H_DRIFT_MULT.items():
        lam_mult, sev_shift = config.CRI_SSP_DAMAGE_ADJ[scenario]
        # Scenario-specific RNG only for E, V, S (independent across scenarios)
        rng = np.random.RandomState(
            42 + int(hashlib.sha256(scenario.encode()).hexdigest(), 16) % 10_000)

        all_sims_idx = np.empty((N_SIM, n_proj_months))

        for sim_i in range(N_SIM):
            # --- H: 2-factor OU (deseasonalised) + seasonal added back ---
            # The observed seasonal cycle IS the OU output; feeding it
            # back as OU input double-damps the amplitude.  Fix: run OU
            # on the deseasonalised mean, then add seasonal at full
            # data-observed amplitude.
            H_path = np.empty(n_proj_months)
            H_ds = H_deseason_last      # deseasonalised state
            Z_t = 0.0                    # slow climate-regime modulator
            for t in range(n_proj_months):
                Z_t = (Z_t + theta_slow * (0.0 - Z_t)
                       + sigma_slow * Z_noise_all[sim_i, t])
                # OU target: long-run mean + trend drift + slow modulator
                mu_ds = (mu_h_long
                         + h_drift_per_mo * h_drift_mult * (t + 1)
                         + Z_t)
                H_ds = (H_ds + theta_h * (mu_ds - H_ds) * dt_mo
                        + sigma_h * H_noise_all[sim_i, t])
                # Re-apply seasonal at full observed amplitude
                mo_idx = t % 12
                H_t = H_ds + h_seasonal_anom[mo_idx]
                H_path[t] = np.clip(H_t, 0.0, 1.0)

            # --- E: Logistic-GBM (annual steps) ---
            E_path_annual = np.empty((proj_end - year_end,))
            E_t = E_last
            for j in range(len(E_path_annual)):
                gap = max(1.0 - E_t / K_e, 0.0)
                E_t = E_t + r_e * E_t * gap * dt_yr * 12 \
                    + sigma_e * E_t * gap * rng.randn()
                E_t = np.clip(E_t, e_floor, K_e)
                E_path_annual[j] = E_t
            # Expand to monthly (step function)
            E_path = np.repeat(E_path_annual, 12)[:n_proj_months]

            # --- V: Logistic-GBM (annual steps) ---
            V_path_annual = np.empty((proj_end - year_end,))
            V_t = V_last
            for j in range(len(V_path_annual)):
                gap = max(1.0 - V_t / K_v, 0.0)
                V_t = V_t + r_v * V_t * gap * dt_yr * 12 \
                    + sigma_v * V_t * gap * rng.randn()
                V_t = np.clip(V_t, v_floor, K_v)
                V_path_annual[j] = V_t
            V_path = np.repeat(V_path_annual, 12)[:n_proj_months]

            # --- S: Compound Poisson → EWMA ---
            monthly_loss = np.zeros(n_proj_months)
            for t in range(n_proj_months):
                n_tc = rng.poisson(lam_monthly * lam_mult)
                if n_tc > 0:
                    severities = np.exp(
                        rng.normal(mu_log_sev + sev_shift,
                                   sigma_log_sev, size=n_tc))
                    monthly_loss[t] = severities.sum()

            d_raw = monthly_loss / max(eal_monthly, 1.0)
            d_log = np.log1p(d_raw)
            d_norm = d_log / max(s_max, 1e-9)
            ewma_arr = np.empty(n_proj_months)
            state = ewma_state_last
            for t in range(n_proj_months):
                state = alpha * state + (1 - alpha) * d_norm[t]
                ewma_arr[t] = state

            # --- CRI composite ---
            cri_raw_sim = (H_path * E_path * V_path
                           * (1.0 + kappa * ewma_arr))

            # 12-mo rolling (prepend historical tail to warm up)
            combined = np.concatenate([hist_tail_raw, cri_raw_sim])
            rolling = pd.Series(combined).rolling(
                12, min_periods=6).mean().values
            cri_12m_sim = rolling[len(hist_tail_raw):]
            all_sims_idx[sim_i] = (
                config.CRI_BASE_INDEX * cri_12m_sim / base_value)

        # Percentile envelopes
        p50 = np.median(all_sims_idx, axis=0)
        p10 = np.percentile(all_sims_idx, 10, axis=0)
        p90 = np.percentile(all_sims_idx, 90, axis=0)

        # Store for shared-rep selection
        scenario_results[scenario] = {
            "all_sims": all_sims_idx,
            "p50": p50, "p10": p10, "p90": p90,
        }

        logger.info(
            f"  {scenario}: CRI@2050 median={p50[-1]:.0f} "
            f"[{p10[-1]:.0f}, {p90[-1]:.0f}]")

    # ── Export full MC path arrays for Composite module (Iman-Conover) ──
    _scenario_key_map = {
        "Historical Baseline": "baseline",
        "SSP2-4.5": "ssp245",
        "SSP5-8.5": "ssp585",
    }
    # Build projection date strings once
    _proj_date_strs = []
    for _yr in range(year_end + 1, proj_end + 1):
        for _mo in range(1, 13):
            if len(_proj_date_strs) >= n_proj_months:
                break
            _proj_date_strs.append(f"{_yr}-{_mo:02d}-01")

    for scenario, skey in _scenario_key_map.items():
        if scenario in scenario_results:
            _npz_path = config.RESULTS_DIR / f"cri_mc_paths_{skey}.npz"
            np.savez_compressed(
                str(_npz_path),
                all_sims=scenario_results[scenario]["all_sims"],
                dates=np.array(_proj_date_strs),
            )
            logger.info(f"  Saved {_npz_path.name}: "
                        f"shape={scenario_results[scenario]['all_sims'].shape}")

    # ── Shared representative ("characteristic") path for all scenarios ──
    # Criterion: among paths whose endpoint is near the median (p40–p60),
    # pick the one whose month-to-month volatility (std of Δindex) best
    # matches the historical CRI volatility.  This avoids the p50 line
    # (over-smooth) and the closest-to-median rep (may be too volatile).
    hist_cri_vals = panel["cri_index"].dropna().values
    hist_vol = np.std(np.diff(hist_cri_vals))

    base_sims = scenario_results["Historical Baseline"]["all_sims"]
    base_finals = base_sims[:, -1]
    lo40 = np.nanpercentile(base_finals, 40)
    hi60 = np.nanpercentile(base_finals, 60)
    candidates = np.where((base_finals >= lo40) & (base_finals <= hi60))[0]
    if len(candidates) == 0:
        candidates = np.arange(base_sims.shape[0])
    path_vols = np.array([np.std(np.diff(base_sims[i])) for i in candidates])
    best_idx = int(np.argmin(np.abs(path_vols - hist_vol)))
    rep_i = int(candidates[best_idx])
    logger.info(f"  Characteristic path: sim={rep_i}, "
                f"hist_vol={hist_vol:.2f}, path_vol={path_vols[best_idx]:.2f}")

    for scenario in config.CRI_SSP_H_DRIFT_MULT:
        res = scenario_results[scenario]
        rep = res["all_sims"][rep_i]
        p50, p10, p90 = res["p50"], res["p10"], res["p90"]

        logger.info(f"  {scenario}: rep={rep[-1]:.0f} (shared sim={rep_i})")

        idx = 0
        for yr in range(year_end + 1, proj_end + 1):
            for mo in range(1, 13):
                if idx >= n_proj_months:
                    break
                proj_records.append({
                    "date": f"{yr}-{mo:02d}-01",
                    "year": yr, "month": mo,
                    "scenario": scenario,
                    "cri_index_rep": float(rep[idx]),
                    "cri_index_p50": float(p50[idx]),
                    "cri_index_p10": float(p10[idx]),
                    "cri_index_p90": float(p90[idx]),
                })
                idx += 1

    proj_df = pd.DataFrame(proj_records)
    proj_df.to_csv(
        str(config.CRI_PROJECTION_CSV), index=False, encoding="utf-8-sig")
    logger.info(f"  Projection: {len(proj_df)} rows, N_SIM={N_SIM} → "
                f"{config.CRI_PROJECTION_CSV.name}")
    logger.info(f"07_climate_index.py complete in {time.time()-t0:.0f}s")
