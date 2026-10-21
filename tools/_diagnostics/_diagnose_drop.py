"""Diagnose the drop at projection start and audit all parameters."""
import pandas as pd
import numpy as np

haz = pd.read_csv("output/results/shanghai_city_monthly_climate_hazard.csv")
proj = pd.read_csv("output/results/shanghai_city_cri_projection.csv")
haz["date"] = pd.to_datetime(haz["date"])

print("=" * 65)
print("DROP DIAGNOSIS: Why does CRI dip at projection start?")
print("=" * 65)

# Historical tail values
print("\n--- Historical tail (last 24 months) ---")
tail = haz.tail(24)
print(f"  cri_raw (last 12): {tail['cri_raw'].tail(12).values.round(4).tolist()}")
print(f"  cri_raw mean (last 12): {tail['cri_raw'].tail(12).mean():.4f}")
print(f"  cri_raw mean (all): {haz['cri_raw'].mean():.4f}")
print(f"  cri_12m (last val): {haz['cri_12m'].iloc[-1]:.4f}")
print(f"  cri_index (last val): {haz['cri_index'].iloc[-1]:.1f}")

# H values at tail
print(f"\n  H(last 12): {tail['hazard_index'].tail(12).values.round(4).tolist()}")
print(f"  H(last 12 mean): {tail['hazard_index'].tail(12).mean():.4f}")
print(f"  H(overall mean): {haz['hazard_index'].mean():.4f}")
print(f"  H(last) = {haz['hazard_index'].iloc[-1]:.4f}")

# The key: H's OU long-run mean
h_vals = haz["hazard_index"].values
dh = np.diff(h_vals)
from scipy import stats as sp_stats
slope_h, intercept_h, _, _, _ = sp_stats.linregress(h_vals[:-1], dh)
theta_h = -slope_h
mu_h = intercept_h / theta_h if theta_h > 0 else h_vals.mean()
print(f"\n  OU fitted: theta={theta_h:.4f}, mu_long={mu_h:.4f}")
print(f"  H(last)={h_vals[-1]:.4f} vs mu_long={mu_h:.4f}")
print(f"  H(last) is {'ABOVE' if h_vals[-1] > mu_h else 'BELOW'} mu by {abs(h_vals[-1]-mu_h):.4f}")

# E and V at tail
print(f"\n  E(last): {haz['e_norm'].iloc[-1]:.4f}")
print(f"  V(last): {haz['v_norm'].iloc[-1]:.4f}")
print(f"  damage_signal(last): {haz['damage_signal'].iloc[-1]:.4f}")

# CRI_raw components
last_row = haz.iloc[-1]
cri_components = (last_row["hazard_index"] * last_row["e_norm"] * 
                  last_row["v_norm"] * (1 + 0.5 * last_row["damage_signal"]))
print(f"\n  cri_raw(last) = H*E*V*(1+kS) = {last_row['hazard_index']:.4f} * "
      f"{last_row['e_norm']:.4f} * {last_row['v_norm']:.4f} * "
      f"(1 + 0.5*{last_row['damage_signal']:.4f}) = {cri_components:.4f}")

# Projection: what does H mean-revert to?
print(f"\n--- Projection H dynamics ---")
print(f"  H starts at {h_vals[-1]:.4f}")
print(f"  OU pulls toward mu={mu_h:.4f}")
print(f"  Monthly seasonal anomalies:")
h_seasonal = haz.groupby("month")["hazard_index"].mean()
h_seasonal_anom = h_seasonal - h_seasonal.mean()
for m in range(1, 13):
    print(f"    Month {m:2d}: mean={h_seasonal[m]:.4f}, "
          f"anom={h_seasonal_anom[m]:+.4f}")

# What is the last month of historical data?
print(f"\n  Last historical month: {haz.iloc[-1]['year']:.0f}-{haz.iloc[-1]['month']:.0f}")
print(f"  Projection starts: {haz.iloc[-1]['year']:.0f}-{haz.iloc[-1]['month']:.0f} + 1")

# The 12-month rolling window issue
print(f"\n--- 12-month Rolling Window Transition ---")
print("  Historical last 12 cri_raw values go INTO projection rolling window")
print(f"  hist_tail_raw = last 11 cri_raw: {haz['cri_raw'].values[-11:].round(4).tolist()}")
avg_tail = haz["cri_raw"].values[-11:].mean()
print(f"  Tail mean: {avg_tail:.4f}")
print(f"  Overall cri_raw mean: {haz['cri_raw'].mean():.4f}")
print(f"  If projection cri_raw reverts to overall mean, the 12-mo MA DROPS")
print(f"  because tail is {avg_tail/haz['cri_raw'].mean():.1f}x the overall mean")

# Check: is the tail period anomalously high?
h_last_year = haz.tail(12)["hazard_index"].mean()
e_last_year = haz.tail(12)["e_norm"].mean()
v_last_year = haz.tail(12)["v_norm"].mean()
print(f"\n  Last-year avg: H={h_last_year:.4f}, E={e_last_year:.4f}, V={v_last_year:.4f}")
print(f"  Overall avg:   H={haz['hazard_index'].mean():.4f}, E={haz['e_norm'].mean():.4f}, V={haz['v_norm'].mean():.4f}")
print(f"  → The tail H × E × V is MUCH higher than overall mean because E and V")
print(f"    grew from 0.5/0.63 → 1.0 over 30 years. The OU mean (mu={mu_h:.4f})")
print(f"    was fitted to ALL 31 years, including early low-E/V periods.")
print(f"    BUT the OU mean-reversion target should reflect the CURRENT level,")
print(f"    not the 31-year average!")

print(f"\n{'='*65}")
print(f"PARAMETER AUDIT: Data-driven vs. subjective")
print(f"{'='*65}")

print("""
  [DATA-DRIVEN] H: OU parameters (theta, mu, sigma)
    → Fitted from 372-month hazard_index via OLS on dH ~ H
    ✓ Purely data-driven
    
  [DATA-DRIVEN] H: seasonal anomalies
    → Monthly means from historical data
    ✓ Purely data-driven
    
  [DATA-DRIVEN] H: drift per year
    → From linear regression of annual H means
    ✓ Purely data-driven
    
  [DATA-DRIVEN] E: logistic-GBM (r, sigma)
    → Fitted from LandScan annual log-growth rates
    ✓ Purely data-driven
    
  [DATA-DRIVEN] V: logistic-GBM (r, sigma)
    → Fitted from ISR annual log-growth rates
    ✓ Purely data-driven
    
  [DATA-DRIVEN] S: Compound Poisson (lambda, mu_log, sigma_log)
    → Lambda from event frequency, severity from log(damage)
    ✓ Purely data-driven
    
  [DATA-DRIVEN] Z: slow modulator (theta_slow=0.02)
    → half-life ~35 months, roughly ENSO period (3-7yr)
    ~ Physically motivated but theta_slow value is a choice
    
  [SUBJECTIVE] sigma_slow = 0.015
    → Calibrated visually, not from data
    ✗ Should be fitted from low-frequency H variability
    
  [SUBJECTIVE] SSP H-drift multipliers: 1.0, 1.5, 2.5
    → Chosen manually, not from IPCC/CMIP6 data
    ✗ Should be derived from CMIP6 temperature projections
    
  [SUBJECTIVE] SSP damage adjustments: (1.0,0), (1.10,0.223), (1.20,0.405)
    → Lambda and severity shifts chosen manually
    ✗ Should be derived from Emanuel/Knutson TC-climate scaling
""")

# Compute what sigma_slow SHOULD be from data
# Low-frequency H variability: take 36-month rolling std of H
h_36m = pd.Series(h_vals).rolling(36, min_periods=12).mean()
h_lf = h_36m.dropna().values
h_lf_diffs = np.diff(h_lf)
sigma_lf = h_lf_diffs.std()
print(f"  Data-derived sigma_slow: std(d(36-mo-MA(H))) = {sigma_lf:.5f}")
print(f"  Current sigma_slow = 0.015")

# Compute SSP multipliers from IPCC warming rates
# IPCC AR6 Table SPM.1: 
#   SSP2-4.5 global warming 2021-2040: +1.5°C (best est), 2041-2060: +2.0°C
#   SSP5-8.5 global warming 2021-2040: +1.6°C (best est), 2041-2060: +2.4°C
# Knutson et al 2020: TC intensity +5% per 2°C, frequency: -10% to +25%
# Emanuel 2011/2021: PDI scales as T^3 (power dissipation)
# For composite H (wind+precip+SLA+heat): mixed climate sensitivity
# Conservative: H drift scales linearly with temperature anomaly
print(f"\n  IPCC AR6 warming (vs 1850-1900):")
print(f"    Current (2024): ~1.1°C")
print(f"    SSP2-4.5 by 2050: ~2.0°C → additional +0.9°C from now")
print(f"    SSP5-8.5 by 2050: ~2.4°C → additional +1.3°C from now")
print(f"  If H-drift scales with dT/dt:")
print(f"    Historical dT rate: ~0.2°C/decade (last 30yr)")
print(f"    SSP2-4.5 dT rate:  ~0.3°C/decade → 1.5x historical")
print(f"    SSP5-8.5 dT rate:  ~0.4°C/decade → 2.0x historical")
print(f"  Current multipliers: 1.0, 1.5, 2.5")
print(f"  Data-grounded:       1.0, 1.5, 2.0")
