"""Diagnostic script for CRI projection issues."""
import pandas as pd
import numpy as np

proj = pd.read_csv("output/results/shanghai_city_cri_projection.csv")
haz = pd.read_csv("output/results/shanghai_city_monthly_climate_hazard.csv")
haz["date"] = pd.to_datetime(haz["date"])
haz["year"] = haz["date"].dt.year

scenarios = ["Historical Baseline", "SSP2-4.5", "SSP5-8.5"]

print("=" * 60)
print("ISSUE 1: Scenario Separation")
print("=" * 60)
for yr in [2030, 2040, 2050]:
    vals = {}
    for scn in scenarios:
        s = proj[(proj["scenario"] == scn) & (proj["year"] == yr)]
        vals[scn] = s["cri_index_p50"].mean()
    base = vals["Historical Baseline"]
    gap45 = (vals["SSP2-4.5"] / base - 1) * 100
    gap85 = (vals["SSP5-8.5"] / base - 1) * 100
    print(f"  {yr}: Baseline={base:.0f}, SSP245={vals['SSP2-4.5']:.0f} (+{gap45:.1f}%), "
          f"SSP585={vals['SSP5-8.5']:.0f} (+{gap85:.1f}%)")

print()
print("=" * 60)
print("ISSUE 2: Band vs Rep-Path Alignment")
print("=" * 60)
for scn in scenarios:
    s = proj[proj["scenario"] == scn]
    inside = ((s["cri_index_rep"] >= s["cri_index_p10"]) &
              (s["cri_index_rep"] <= s["cri_index_p90"])).mean()
    corr = np.corrcoef(s["cri_index_rep"], s["cri_index_p50"])[0, 1]
    bias = s["cri_index_rep"].mean() - s["cri_index_p50"].mean()
    print(f"  {scn}:")
    print(f"    rep inside band: {inside*100:.0f}%")
    print(f"    corr(rep, p50): {corr:.3f}")
    print(f"    mean bias (rep - p50): {bias:+.1f}")
    # Check band vs rep at different points
    for t_frac, label in [(0.1, "early"), (0.5, "mid"), (0.9, "late")]:
        idx = int(len(s) * t_frac)
        row = s.iloc[idx]
        print(f"    {label}: rep={row['cri_index_rep']:.0f}, "
              f"p50={row['cri_index_p50']:.0f}, "
              f"band=[{row['cri_index_p10']:.0f}, {row['cri_index_p90']:.0f}]")

print()
print("=" * 60)
print("ISSUE 3: Trend Analysis")
print("=" * 60)
# Historical trend
ha = haz.groupby("year")["cri_index"].mean().dropna()
h_slope = np.polyfit(ha.index.values, ha.values, 1)[0]
print(f"  Historical data: +{h_slope:.2f}/yr ({h_slope/ha.iloc[0]*100:.1f}%/yr of start)")

for scn in scenarios:
    s = proj[proj["scenario"] == scn]
    ann = s.groupby("year")["cri_index_p50"].mean()
    slope = np.polyfit(ann.index.values, ann.values, 1)[0]
    pct = slope / ann.iloc[0] * 100
    print(f"  {scn}: {slope:+.2f}/yr ({pct:+.1f}%/yr), "
          f"start_3yr={ann.iloc[:3].mean():.0f}, end_3yr={ann.iloc[-3:].mean():.0f}")

print()
print("=" * 60)
print("ROOT CAUSE ANALYSIS")
print("=" * 60)

# H drift
h_ann = haz.groupby("year")["hazard_index"].mean()
h_drift_yr, _ = np.polyfit(h_ann.index.values, h_ann.values, 1)
print(f"  H drift from data: {h_drift_yr:+.5f}/yr")
print(f"  H mean: {haz['hazard_index'].mean():.4f}")
print(f"  H drift/mean: {h_drift_yr/haz['hazard_index'].mean()*100:+.2f}%/yr")
print(f"  Over 27yr projection:")
print(f"    Baseline: H adds {h_drift_yr*27:.4f}")
print(f"    SSP2-4.5: H adds {h_drift_yr*1.5*27:.4f}")
print(f"    SSP5-8.5: H adds {h_drift_yr*2.5*27:.4f}")
print(f"  BUT: OU mean-reversion (theta=0.43) pulls H back to mu")
print(f"  → drift only shifts mu_t linearly, actual H tracks mu_t with lag")

# E, V saturation
print(f"\n  E(last) = {haz['e_norm'].iloc[-1]:.4f}, gap to K=1: {1-haz['e_norm'].iloc[-1]:.4f}")
print(f"  V(last) = {haz['v_norm'].iloc[-1]:.4f}, gap to K=1: {1-haz['v_norm'].iloc[-1]:.4f}")
print(f"  → Both saturated at ceiling, ~0 growth room → NO trend contribution")

# What WOULD produce the historical trend?
hist_start = ha.iloc[0]
hist_end = ha.iloc[-1]
hist_yrs = ha.index[-1] - ha.index[0]
print(f"\n  Historical CRI: {hist_start:.0f} → {hist_end:.0f} over {hist_yrs}yr")
print(f"  That's {(hist_end/hist_start)**(1/hist_yrs)-1:.1%}/yr compound growth")
print(f"  Driven by: E (0.50→1.00) + V (0.63→1.00) + H rising")
print(f"  In projection: E≈1, V≈1 saturated → only H drift + S spikes drive trend")
print(f"  H drift alone: {h_drift_yr/haz['hazard_index'].mean()*100:.2f}%/yr → minimal")

# IPCC-based climate trend literature
print()
print("=" * 60)
print("LITERATURE: Expected climate trend magnitudes")
print("=" * 60)
print("  Knutson et al. 2020 (BAMS): TC intensity +5% per 2°C warming")
print("  Emanuel 2021: Power Dissipation Index +25-30% per 2°C")
print("  IPCC AR6 WG1: SSP2-4.5 → +1.5°C by 2050, SSP5-8.5 → +2.0°C")
print("  → For hazard H (composite):")
print("    SSP2-4.5: ~+10-15% over 27yr (+0.4-0.6%/yr)")
print("    SSP5-8.5: ~+20-30% over 27yr (+0.7-1.1%/yr)")
print("  Current model H drift:")
print(f"    Baseline: {h_drift_yr*27/haz['hazard_index'].mean()*100:.1f}% total")
print(f"    SSP2-4.5: {h_drift_yr*1.5*27/haz['hazard_index'].mean()*100:.1f}% total")
print(f"    SSP5-8.5: {h_drift_yr*2.5*27/haz['hazard_index'].mean()*100:.1f}% total")
