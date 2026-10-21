import pandas as pd
haz = pd.read_csv("output/results/shanghai_city_monthly_climate_hazard.csv")
proj = pd.read_csv("output/results/shanghai_city_cri_projection.csv")

print("=== Historical tail (last 6 months) ===")
for _, r in haz.tail(6).iterrows():
    print(f"  {r['date']}  cri_index={r['cri_index']:.1f}")

print("\n=== Projection start: Historical Baseline (p50) ===")
bl = proj[proj["scenario"]=="Historical Baseline"].head(24)
for _, r in bl.iterrows():
    print(f"  {r['date']}  p50={r['cri_index_p50']:.1f}  p10={r['cri_index_p10']:.1f}  p90={r['cri_index_p90']:.1f}")

hist_last = haz["cri_index"].iloc[-1]
proj_first = bl["cri_index_p50"].iloc[0]
proj_min = bl["cri_index_p50"].min()
proj_min_date = bl.loc[bl["cri_index_p50"].idxmin(), "date"]
print(f"\nHistorical terminal: {hist_last:.1f}")
print(f"Projection first:   {proj_first:.1f}  (gap={proj_first-hist_last:+.1f})")
print(f"Projection min:     {proj_min:.1f} at {proj_min_date} (dip={proj_min-hist_last:+.1f})")
