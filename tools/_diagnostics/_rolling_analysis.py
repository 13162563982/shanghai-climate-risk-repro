"""
Rolling-Window Parameter Analysis for CRI Projection
=====================================================
Uses 5-year rolling windows starting from 2000 to characterize
temporal evolution of ALL underlying components: H, E, V, S.

Output: data-driven parameter trajectories + backtest vs historical CRI.
"""
import pandas as pd
import numpy as np
from scipy import stats as sp_stats
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# ── Load data ────────────────────────────────────────────────────────
haz = pd.read_csv("output/results/shanghai_city_monthly_climate_hazard.csv")
haz["date"] = pd.to_datetime(haz["date"])

print("=" * 70)
print("ROLLING-WINDOW PARAMETER ANALYSIS (5-year windows, 2000→2023)")
print("=" * 70)
print(f"Data: {len(haz)} months, {haz['year'].min()}-{haz['year'].max()}")
print(f"Columns: {haz.columns.tolist()}")
print()

WIN = 5  # years per window

# ═══════════════════════════════════════════════════════════════════════
# 1. HAZARD INDEX H(t) — Rolling OU parameters
# ═══════════════════════════════════════════════════════════════════════
print("=" * 70)
print("1. HAZARD H(t): Rolling OU parameter evolution")
print("=" * 70)

h_results = []
for end_yr in range(2000 + WIN - 1, 2024):
    start_yr = end_yr - WIN + 1
    mask = (haz["year"] >= start_yr) & (haz["year"] <= end_yr)
    h_vals = haz.loc[mask, "hazard_index"].values
    if len(h_vals) < 24:
        continue
    
    # OU fit: dH = theta(mu - H)dt + sigma*dW
    dh = np.diff(h_vals)
    slope, intercept, r_val, p_val, se = sp_stats.linregress(h_vals[:-1], dh)
    theta = -slope
    mu = intercept / theta if theta > 0 else h_vals.mean()
    sigma = np.std(dh - intercept - slope * h_vals[:-1])
    half_life = np.log(2) / theta if theta > 0 else np.inf
    
    # Annual mean and trend within window
    h_annual = haz.loc[mask].groupby("year")["hazard_index"].mean()
    h_trend = np.polyfit(h_annual.index.values, h_annual.values, 1)[0]
    
    # Seasonal amplitude (max monthly mean - min monthly mean)
    h_seasonal = haz.loc[mask].groupby("month")["hazard_index"].mean()
    seasonal_amp = h_seasonal.max() - h_seasonal.min()
    
    # Sub-components
    for comp in ["sla_norm", "wind_norm", "precip_norm", "heat_norm"]:
        if comp in haz.columns:
            c_annual = haz.loc[mask].groupby("year")[comp].mean()
            c_trend = np.polyfit(c_annual.index.values, c_annual.values, 1)[0] if len(c_annual) > 2 else 0
            h_results.append({
                "window": f"{start_yr}-{end_yr}",
                "end_yr": end_yr,
                "param": f"{comp}_trend",
                "value": c_trend, 
            })
    
    h_results.append({"window": f"{start_yr}-{end_yr}", "end_yr": end_yr,
                      "param": "theta", "value": theta})
    h_results.append({"window": f"{start_yr}-{end_yr}", "end_yr": end_yr,
                      "param": "mu", "value": mu})
    h_results.append({"window": f"{start_yr}-{end_yr}", "end_yr": end_yr,
                      "param": "sigma", "value": sigma})
    h_results.append({"window": f"{start_yr}-{end_yr}", "end_yr": end_yr,
                      "param": "half_life_mo", "value": half_life})
    h_results.append({"window": f"{start_yr}-{end_yr}", "end_yr": end_yr,
                      "param": "h_mean", "value": h_vals.mean()})
    h_results.append({"window": f"{start_yr}-{end_yr}", "end_yr": end_yr,
                      "param": "h_trend_yr", "value": h_trend})
    h_results.append({"window": f"{start_yr}-{end_yr}", "end_yr": end_yr,
                      "param": "seasonal_amp", "value": seasonal_amp})

h_df = pd.DataFrame(h_results)

print("\n  OU parameters over time:")
print(f"  {'Window':<12} {'θ':>6} {'μ':>6} {'σ':>6} {'t½(mo)':>7} {'H_mean':>7} {'trend/yr':>9} {'seas_amp':>9}")
for win in h_df["window"].unique():
    w = h_df[h_df["window"] == win]
    theta = w[w["param"]=="theta"]["value"].iloc[0]
    mu = w[w["param"]=="mu"]["value"].iloc[0]
    sigma = w[w["param"]=="sigma"]["value"].iloc[0]
    hl = w[w["param"]=="half_life_mo"]["value"].iloc[0]
    hm = w[w["param"]=="h_mean"]["value"].iloc[0]
    ht = w[w["param"]=="h_trend_yr"]["value"].iloc[0]
    sa = w[w["param"]=="seasonal_amp"]["value"].iloc[0]
    print(f"  {win:<12} {theta:6.3f} {mu:6.4f} {sigma:6.4f} {hl:7.1f} {hm:7.4f} {ht:+9.5f} {sa:9.4f}")

# Sub-component trends
print("\n  Sub-component trends (per year) by window:")
print(f"  {'Window':<12} {'SLA':>9} {'Wind':>9} {'Precip':>9} {'Heat':>9}")
for win in h_df["window"].unique():
    w = h_df[h_df["window"] == win]
    vals = {}
    for comp in ["sla_norm", "wind_norm", "precip_norm", "heat_norm"]:
        row = w[w["param"] == f"{comp}_trend"]
        vals[comp] = row["value"].iloc[0] if len(row) > 0 else 0
    print(f"  {win:<12} {vals['sla_norm']:+9.5f} {vals['wind_norm']:+9.5f} "
          f"{vals['precip_norm']:+9.5f} {vals['heat_norm']:+9.5f}")

# ═══════════════════════════════════════════════════════════════════════
# 2. EXPOSURE E(t) — Rolling growth rate
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("2. EXPOSURE E(t): Rolling growth dynamics")
print("=" * 70)

e_results = []
for end_yr in range(2000 + WIN - 1, 2024):
    start_yr = end_yr - WIN + 1
    mask = (haz["year"] >= start_yr) & (haz["year"] <= end_yr)
    e_annual = haz.loc[mask].groupby("year")["e_norm"].first()
    if len(e_annual) < 3:
        continue
    
    # Log growth rates
    e_vals = e_annual.values
    log_growth = np.diff(np.log(np.maximum(e_vals, 1e-6)))
    r_mean = log_growth.mean() if len(log_growth) > 0 else 0
    r_std = log_growth.std() if len(log_growth) > 1 else 0
    
    # Gap to ceiling
    gap = 1.0 - e_vals[-1]
    
    e_results.append({
        "window": f"{start_yr}-{end_yr}", "end_yr": end_yr,
        "e_last": e_vals[-1], "r_growth": r_mean,
        "r_std": r_std, "gap_to_K": gap
    })

e_df = pd.DataFrame(e_results)
print(f"\n  {'Window':<12} {'E(end)':>7} {'r(growth/yr)':>13} {'σ(growth)':>10} {'gap to K':>9}")
for _, row in e_df.iterrows():
    print(f"  {row['window']:<12} {row['e_last']:7.4f} {row['r_growth']:+13.4f} "
          f"{row['r_std']:10.4f} {row['gap_to_K']:9.4f}")

# ═══════════════════════════════════════════════════════════════════════
# 3. VULNERABILITY V(t) — Rolling growth rate
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("3. VULNERABILITY V(t): Rolling growth dynamics")
print("=" * 70)

v_results = []
for end_yr in range(2000 + WIN - 1, 2024):
    start_yr = end_yr - WIN + 1
    mask = (haz["year"] >= start_yr) & (haz["year"] <= end_yr)
    v_annual = haz.loc[mask].groupby("year")["v_norm"].first()
    if len(v_annual) < 3:
        continue
    
    v_vals = v_annual.values
    log_growth = np.diff(np.log(np.maximum(v_vals, 1e-6)))
    r_mean = log_growth.mean() if len(log_growth) > 0 else 0
    r_std = log_growth.std() if len(log_growth) > 1 else 0
    gap = 1.0 - v_vals[-1]
    
    v_results.append({
        "window": f"{start_yr}-{end_yr}", "end_yr": end_yr,
        "v_last": v_vals[-1], "r_growth": r_mean,
        "r_std": r_std, "gap_to_K": gap
    })

v_df = pd.DataFrame(v_results)
print(f"\n  {'Window':<12} {'V(end)':>7} {'r(growth/yr)':>13} {'σ(growth)':>10} {'gap to K':>9}")
for _, row in v_df.iterrows():
    print(f"  {row['window']:<12} {row['v_last']:7.4f} {row['r_growth']:+13.4f} "
          f"{row['r_std']:10.4f} {row['gap_to_K']:9.4f}")

# ═══════════════════════════════════════════════════════════════════════
# 4. DAMAGE SIGNAL S(t) — Rolling Poisson parameters
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("4. DAMAGE S(t): Rolling Compound Poisson parameters")
print("=" * 70)

s_results = []
for end_yr in range(2000 + WIN - 1, 2024):
    start_yr = end_yr - WIN + 1
    mask = (haz["year"] >= start_yr) & (haz["year"] <= end_yr)
    risk_vals = haz.loc[mask, "risk_total"].values
    n_months = len(risk_vals)
    nonzero = risk_vals[risk_vals > 0]
    n_events = len(nonzero)
    lam_mo = n_events / max(n_months, 1)
    
    if n_events > 1:
        log_sev = np.log(nonzero)
        mu_log = log_sev.mean()
        sigma_log = log_sev.std()
        mean_loss = nonzero.mean()
    else:
        mu_log = np.nan
        sigma_log = np.nan
        mean_loss = np.nan
    
    s_results.append({
        "window": f"{start_yr}-{end_yr}", "end_yr": end_yr,
        "n_events": n_events, "lambda_mo": lam_mo,
        "mu_log": mu_log, "sigma_log": sigma_log,
        "mean_loss": mean_loss
    })

s_df = pd.DataFrame(s_results)
print(f"\n  {'Window':<12} {'n_evt':>6} {'λ/mo':>7} {'μ_log':>7} {'σ_log':>7} {'mean_loss':>12}")
for _, row in s_df.iterrows():
    print(f"  {row['window']:<12} {row['n_events']:6.0f} {row['lambda_mo']:7.4f} "
          f"{row['mu_log']:7.2f} {row['sigma_log']:7.2f} {row['mean_loss']:12.2e}")

# ═══════════════════════════════════════════════════════════════════════
# 5. CRI COMPOSITE — Rolling trend & volatility
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("5. CRI COMPOSITE: Rolling trend decomposition")
print("=" * 70)

cri_results = []
for end_yr in range(2000 + WIN - 1, 2024):
    start_yr = end_yr - WIN + 1
    mask = (haz["year"] >= start_yr) & (haz["year"] <= end_yr)
    cri_annual = haz.loc[mask].groupby("year")["cri_index"].mean().dropna()
    if len(cri_annual) < 3:
        continue
    
    slope = np.polyfit(cri_annual.index.values, cri_annual.values, 1)[0]
    pct_growth = slope / cri_annual.iloc[0] * 100 if cri_annual.iloc[0] > 0 else 0
    
    # Monthly volatility (std of log returns)
    cri_12m = haz.loc[mask, "cri_12m"].dropna().values
    if len(cri_12m) > 12:
        log_ret = np.diff(np.log(np.maximum(cri_12m, 1e-6)))
        monthly_vol = log_ret.std()
        annual_vol = monthly_vol * np.sqrt(12)
    else:
        monthly_vol = np.nan
        annual_vol = np.nan
    
    cri_results.append({
        "window": f"{start_yr}-{end_yr}", "end_yr": end_yr,
        "cri_start": cri_annual.iloc[0], "cri_end": cri_annual.iloc[-1],
        "slope_yr": slope, "pct_growth_yr": pct_growth,
        "monthly_vol": monthly_vol, "annual_vol": annual_vol
    })

cri_df = pd.DataFrame(cri_results)
print(f"\n  {'Window':<12} {'CRI_start':>10} {'CRI_end':>8} {'slope/yr':>9} {'%/yr':>7} {'ann_vol':>8}")
for _, row in cri_df.iterrows():
    print(f"  {row['window']:<12} {row['cri_start']:10.1f} {row['cri_end']:8.1f} "
          f"{row['slope_yr']:+9.2f} {row['pct_growth_yr']:+7.1f} {row['annual_vol']:8.3f}")

# ═══════════════════════════════════════════════════════════════════════
# 6. KEY FINDINGS SUMMARY
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("6. KEY FINDINGS & PATTERNS")
print("=" * 70)

# H trend evolution
h_trends = h_df[h_df["param"] == "h_trend_yr"].copy()
h_recent = h_trends[h_trends["end_yr"] >= 2018]["value"]
h_early = h_trends[h_trends["end_yr"] <= 2010]["value"]
print(f"\n  H drift trend:")
print(f"    Early windows (ending ≤2010): {h_early.mean():+.5f}/yr")
print(f"    Recent windows (ending ≥2018): {h_recent.mean():+.5f}/yr")
print(f"    → Drift is {'accelerating' if h_recent.mean() > h_early.mean() else 'decelerating'}")

# H mu evolution
h_mus = h_df[h_df["param"] == "mu"].copy()
print(f"\n  H OU mean-reversion target (mu):")
print(f"    Range: {h_mus['value'].min():.4f} — {h_mus['value'].max():.4f}")
print(f"    Last 3 windows: {h_mus.tail(3)['value'].values.round(4).tolist()}")

# H seasonal amplitude
h_seas = h_df[h_df["param"] == "seasonal_amp"].copy()
print(f"\n  Seasonal amplitude:")
print(f"    Range: {h_seas['value'].min():.4f} — {h_seas['value'].max():.4f}")
print(f"    Trend: {'increasing' if h_seas.tail(3)['value'].mean() > h_seas.head(3)['value'].mean() else 'stable/decreasing'}")

# E saturation
if len(e_df) > 0:
    print(f"\n  E(exposure) saturation:")
    print(f"    Gap to ceiling: {e_df.iloc[-1]['gap_to_K']:.4f} (essentially saturated)")
    print(f"    Growth rate collapse: {e_df.iloc[0]['r_growth']:+.4f} → {e_df.iloc[-1]['r_growth']:+.4f}")

# V saturation
if len(v_df) > 0:
    print(f"\n  V(vulnerability) saturation:")
    print(f"    Gap to ceiling: {v_df.iloc[-1]['gap_to_K']:.4f}")
    print(f"    Growth rate collapse: {v_df.iloc[0]['r_growth']:+.4f} → {v_df.iloc[-1]['r_growth']:+.4f}")

# CRI growth rate deceleration
if len(cri_df) > 0:
    print(f"\n  CRI growth rate evolution:")
    print(f"    Early: {cri_df.iloc[0]['pct_growth_yr']:+.1f}%/yr")
    print(f"    Recent: {cri_df.iloc[-1]['pct_growth_yr']:+.1f}%/yr")
    print(f"    → {'Decelerating' if cri_df.iloc[-1]['pct_growth_yr'] < cri_df.iloc[0]['pct_growth_yr'] else 'Accelerating'}")
    
    # Annualized vol
    print(f"\n  CRI annualized volatility:")
    print(f"    Range: {cri_df['annual_vol'].min():.3f} — {cri_df['annual_vol'].max():.3f}")
    print(f"    Recent: {cri_df.tail(3)['annual_vol'].mean():.3f}")

# ═══════════════════════════════════════════════════════════════════════
# 7. BACKTEST: Use rolling params to "predict" next year
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("7. BACKTEST: Rolling-param one-year-ahead forecast")
print("=" * 70)

# For each window ending in year Y, predict CRI in year Y+1
backtest_results = []
for _, row in cri_df.iterrows():
    end_yr = row["end_yr"]
    predicted_next = row["cri_end"] + row["slope_yr"]
    actual_mask = haz["year"] == (end_yr + 1)
    if actual_mask.any():
        actual = haz.loc[actual_mask, "cri_index"].mean()
        if not np.isnan(actual):
            err = predicted_next - actual
            pct_err = err / actual * 100
            backtest_results.append({
                "pred_year": end_yr + 1,
                "predicted": predicted_next,
                "actual": actual,
                "error": err,
                "pct_error": pct_err
            })

bt_df = pd.DataFrame(backtest_results)
if len(bt_df) > 0:
    print(f"\n  {'Year':>6} {'Predicted':>10} {'Actual':>8} {'Error':>8} {'%Err':>7}")
    for _, row in bt_df.iterrows():
        print(f"  {row['pred_year']:6.0f} {row['predicted']:10.1f} {row['actual']:8.1f} "
              f"{row['error']:+8.1f} {row['pct_error']:+7.1f}%")
    
    mae = bt_df["error"].abs().mean()
    mape = bt_df["pct_error"].abs().mean()
    print(f"\n  MAE = {mae:.1f}, MAPE = {mape:.1f}%")
    print(f"  Bias = {bt_df['error'].mean():+.1f} (systematic {'over' if bt_df['error'].mean() > 0 else 'under'}-prediction)")

# ═══════════════════════════════════════════════════════════════════════
# 8. PROJECTION-RELEVANT PARAMETER SUMMARY
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("8. DATA-DRIVEN PARAMETERS FOR PROJECTION")
print("=" * 70)

# Best estimates from most recent windows
recent_h = h_df[h_df["end_yr"] >= 2020]
theta_best = recent_h[recent_h["param"]=="theta"]["value"].mean()
mu_best = recent_h[recent_h["param"]=="mu"]["value"].mean()
sigma_best = recent_h[recent_h["param"]=="sigma"]["value"].mean()
drift_best = recent_h[recent_h["param"]=="h_trend_yr"]["value"].mean()
seas_best = recent_h[recent_h["param"]=="seasonal_amp"]["value"].mean()

print(f"\n  H(t) OU (from recent 3 windows):")
print(f"    θ = {theta_best:.4f} (mean-reversion speed)")
print(f"    μ = {mu_best:.4f} (long-run mean)")
print(f"    σ = {sigma_best:.4f} (monthly volatility)")
print(f"    drift = {drift_best:+.5f}/yr")
print(f"    seasonal amplitude = {seas_best:.4f}")

if len(e_df) > 0:
    recent_e = e_df[e_df["end_yr"] >= 2020]
    print(f"\n  E(t) Logistic (from recent windows):")
    print(f"    r = {recent_e['r_growth'].mean():+.4f}/yr")
    print(f"    σ = {recent_e['r_std'].mean():.4f}/yr")
    print(f"    E(last) = {recent_e.iloc[-1]['e_last']:.4f}, gap = {recent_e.iloc[-1]['gap_to_K']:.4f}")
    
if len(v_df) > 0:
    recent_v = v_df[v_df["end_yr"] >= 2020]
    print(f"\n  V(t) Logistic (from recent windows):")
    print(f"    r = {recent_v['r_growth'].mean():+.4f}/yr")
    print(f"    σ = {recent_v['r_std'].mean():.4f}/yr")
    print(f"    V(last) = {recent_v.iloc[-1]['v_last']:.4f}, gap = {recent_v.iloc[-1]['gap_to_K']:.4f}")

recent_s = s_df[s_df["end_yr"] >= 2018]
if len(recent_s) > 0 and recent_s["mu_log"].notna().any():
    print(f"\n  S(t) Compound Poisson (from recent windows):")
    print(f"    λ = {recent_s['lambda_mo'].mean():.4f}/mo")
    print(f"    μ_log = {recent_s['mu_log'].mean():.2f}")
    print(f"    σ_log = {recent_s['sigma_log'].mean():.2f}")

if len(cri_df) > 0:
    recent_cri = cri_df[cri_df["end_yr"] >= 2020]
    print(f"\n  CRI composite (from recent windows):")
    print(f"    trend = {recent_cri['slope_yr'].mean():+.1f}/yr")
    print(f"    annualized vol = {recent_cri['annual_vol'].mean():.3f}")
    print(f"    monthly vol = {recent_cri['monthly_vol'].mean():.4f}")

# Low-frequency variability for Z slow modulator
print(f"\n  Z(t) slow modulator (data-derived):")
h_vals_all = haz["hazard_index"].values
h_36m = pd.Series(h_vals_all).rolling(36, min_periods=12).mean().dropna().values
sigma_slow_data = np.diff(h_36m).std()
# Also try spectral analysis for ENSO-scale period
from numpy.fft import fft
h_detrend = h_vals_all - np.polyval(np.polyfit(np.arange(len(h_vals_all)), h_vals_all, 1), np.arange(len(h_vals_all)))
ps = np.abs(fft(h_detrend))**2
freqs = np.fft.fftfreq(len(h_detrend), d=1)  # monthly
# Look for peaks in 2-7 year band 
band_mask = (1/freqs > 24) & (1/freqs < 84) & (freqs > 0)
if band_mask.any():
    peak_idx = np.argmax(ps[band_mask])
    peak_period = 1 / freqs[band_mask][peak_idx]
    peak_power = ps[band_mask][peak_idx]
    total_power = ps[freqs > 0].sum()
    print(f"    Peak low-freq period: {peak_period:.0f} months ({peak_period/12:.1f} years)")
    print(f"    Low-freq power fraction: {ps[band_mask].sum()/total_power*100:.1f}%")
    theta_slow_data = np.log(2) / (peak_period / 2)  # half-life = half period
    print(f"    Implied θ_slow: {theta_slow_data:.4f}")

print(f"    σ_slow (from 36-mo MA diffs): {sigma_slow_data:.5f}")

print("\n" + "=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)
