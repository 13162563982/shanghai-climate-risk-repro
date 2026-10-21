"""
Diagnose the dip at projection start.
Check: H_last vs mu_h, cri_raw tail level, rolling warmup effect,
       seasonal anomaly at projection month, EWMA decay.
"""
import pandas as pd
import numpy as np

haz = pd.read_csv("output/results/shanghai_city_monthly_climate_hazard.csv")
haz["date"] = pd.to_datetime(haz["date"])

print("=== PROJECTION START DIP DIAGNOSIS ===\n")

# 1. Historical CRI tail
print("1. Historical CRI tail (last 24 months):")
tail = haz.tail(24)[["date","year","month","hazard_index","e_norm","v_norm",
                       "damage_signal","cri_raw","cri_12m","cri_index"]]
for _, r in tail.iterrows():
    print(f"   {r['date'].strftime('%Y-%m')}  H={r['hazard_index']:.4f}  "
          f"E={r['e_norm']:.4f}  V={r['v_norm']:.4f}  "
          f"S_ewma={r['damage_signal']:.4f}  "
          f"cri_raw={r['cri_raw']:.4f}  cri_12m={r['cri_12m']:.4f}  "
          f"cri_idx={r['cri_index']:.1f}")

# 2. The 11-month tail used for warmup
hist_tail_raw = haz["cri_raw"].values[-11:]
print(f"\n2. hist_tail_raw for 12-mo warmup (last 11 months):")
print(f"   values: {hist_tail_raw.round(4).tolist()}")
print(f"   mean:   {hist_tail_raw.mean():.4f}")

# 3. H_last vs mu_recent
h_vals = haz["hazard_index"].values
H_last = h_vals[-1]
recent_5yr = haz[haz["year"] >= 2019]["hazard_index"]
mu_recent = recent_5yr.mean()
print(f"\n3. H initial condition:")
print(f"   H_last (Dec 2023) = {H_last:.4f}")
print(f"   mu_recent (5yr)   = {mu_recent:.4f}")
print(f"   Gap: {H_last - mu_recent:+.4f}")

# 4. Seasonal anomaly at projection start month (Jan = month 0)
h_seasonal = haz[haz["year"] >= 2019].groupby("month")["hazard_index"].mean()
h_seasonal_anom = (h_seasonal - h_seasonal.mean()).values
print(f"\n4. Seasonal anomaly (projection starts at Jan):")
for mo in range(1, 13):
    print(f"   Month {mo:2d}: {h_seasonal_anom[mo-1]:+.4f} {'<-- Jan start' if mo == 1 else ''}")

# 5. What happens to CRI when seasonal dip occurs?
# The first few months of projection: Jan, Feb, Mar...
# H will be pulled toward mu + seasonal_anom[0,1,2...] + drift
print(f"\n5. First 6 months of projection (expected H):")
from scipy import stats as sp_stats
h_recent_fit = haz[haz["year"] >= 2014]["hazard_index"].values
dh = np.diff(h_recent_fit)
slope, intercept, _, _, _ = sp_stats.linregress(h_recent_fit[:-1], dh)
theta_ = -slope
sigma_ = np.std(dh - intercept - slope * h_recent_fit[:-1])

h_annual_recent = haz[haz["year"] >= 2014].groupby("year")["hazard_index"].mean()
drift_yr, _ = np.polyfit(h_annual_recent.index.values, h_annual_recent.values, 1)
drift_mo = drift_yr / 12

H_t = H_last
for t in range(6):
    mo_idx = t % 12  # Jan=0, Feb=1...
    mu_t = mu_recent + drift_mo * (t+1) + h_seasonal_anom[mo_idx]
    # Expected OU step (no noise)
    H_t_next = H_t + theta_ * (mu_t - H_t)
    print(f"   t={t+1} (month {mo_idx+1:2d}): mu_t={mu_t:.4f}, "
          f"H_expected={H_t_next:.4f} (seasonal anom={h_seasonal_anom[mo_idx]:+.4f})")
    H_t = H_t_next

# 6. The real culprit: cri_raw in last months vs 12mo rolling
print(f"\n6. CRI_raw vs CRI_12m gap in historical tail:")
cri_raw_last12 = haz["cri_raw"].values[-12:]
cri_12m_last = haz["cri_12m"].values[-1]
cri_raw_mean = cri_raw_last12.mean()
print(f"   cri_raw mean(last 12mo) = {cri_raw_mean:.4f}")
print(f"   cri_12m (last value)    = {cri_12m_last:.4f}")
print(f"   Last cri_raw            = {haz['cri_raw'].values[-1]:.4f}")

# Check: in the last 12 months, which months had HIGH cri_raw 
# that will drop out of the rolling window?
cri_raw_last24 = haz["cri_raw"].values[-24:]
print(f"\n   cri_raw last 24 months (month 1=oldest):")
for i, v in enumerate(cri_raw_last24):
    marker = " <<<< will drop out early" if i < 12 else ""
    print(f"   [{i+1:2d}] {v:.4f}{marker}")

# 7. The base_value
base_idx = haz["cri_12m"].dropna().values[0]
print(f"\n7. base_value (first valid cri_12m) = {base_idx:.6f}")
print(f"   CRI_index formula: 100 * cri_12m / base_value")
print(f"   Current CRI_index last = {100 * cri_12m_last / base_idx:.1f}")

# 8. EWMA decay - damage_signal will decay toward 0 if no events
ewma_last = haz["damage_signal"].values[-1]
alpha = 0.85
print(f"\n8. EWMA damage signal decay (α={alpha}):")
state = ewma_last
for t in range(12):
    state = alpha * state  # no new events
    print(f"   t={t+1}: S(t)={state:.4f} → boost = {0.5*state:+.4f}")
