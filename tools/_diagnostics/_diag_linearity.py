"""Diagnose linearity in early CFCI projection."""
import pandas as pd
import numpy as np

proj = pd.read_csv("output/results/shanghai_cfci_projection.csv")
proj["date"] = pd.to_datetime(proj["date"])

for sc in proj["scenario"].unique():
    s = proj[proj["scenario"] == sc].head(18).copy()
    diffs = s["cfci_p50"].diff().values[1:]
    band = (s["cfci_p90"] - s["cfci_p10"]).values
    print(f"\n=== {sc} ===")
    print(s[["date", "cfci_p50", "cfci_p10", "cfci_p90"]].to_string(index=False))
    print(f"  p50 diffs: {np.round(diffs, 2)}")
    print(f"  band width: {np.round(band, 1)}")
    # Check linearity: R² of p50 vs time index
    t_idx = np.arange(len(s))
    p50 = s["cfci_p50"].values
    corr = np.corrcoef(t_idx, p50)[0, 1]
    print(f"  R² (linearity): {corr**2:.4f}")

# Also check: load NPZ and examine path-level variance at early time steps
print("\n\n=== Path-level diagnostics (Baseline) ===")
cri = np.load("../Climate/output/results/cri_mc_paths_baseline.npz")
fri = np.load("../Finance/output/results/fri_mc_paths_baseline.npz")
cri_sims = cri["all_sims"]
fri_sims = fri["all_sims"]
cri_dates = pd.to_datetime(cri["dates"])
fri_dates = pd.to_datetime(fri["dates"])

print(f"CRI paths shape: {cri_sims.shape}, dates: {cri_dates[0]} to {cri_dates[-1]}")
print(f"FRI paths shape: {fri_sims.shape}, dates: {fri_dates[0]} to {fri_dates[-1]}")

# CRI cross-sectional CV at early time steps
for t in [0, 5, 11, 23, 35]:
    if t < cri_sims.shape[1]:
        vals = cri_sims[:, t]
        print(f"  CRI t={t} ({cri_dates[t].strftime('%Y-%m')}): "
              f"mean={vals.mean():.1f}, std={vals.std():.1f}, "
              f"CV={vals.std()/vals.mean():.3f}")

print()
for t in [0, 5, 11, 23, 35]:
    if t < fri_sims.shape[1]:
        vals = fri_sims[:, t]
        print(f"  FRI t={t} ({fri_dates[t].strftime('%Y-%m')}): "
              f"mean={vals.mean():.1f}, std={vals.std():.1f}, "
              f"CV={vals.std()/vals.mean():.3f}")

# Check individual CRI path volatility (month-to-month changes)
print("\n=== Temporal volatility of individual CRI paths ===")
for i in [0, 1, 2]:
    path = cri_sims[i, :24]
    diffs = np.diff(path)
    print(f"  Path {i}: monthly diffs std={diffs.std():.2f}, "
          f"range=[{diffs.min():.2f}, {diffs.max():.2f}]")

print("\n=== Temporal volatility of individual FRI paths ===") 
for i in [0, 1, 2]:
    path = fri_sims[i, :24]
    diffs = np.diff(path)
    print(f"  Path {i}: monthly diffs std={diffs.std():.2f}, "
          f"range=[{diffs.min():.2f}, {diffs.max():.2f}]")

# Check: what does CFCI look like for a few individual paths?
print("\n=== Individual CFCI paths (Baseline, first 12 months) ===")
common = np.intersect1d(cri_dates, fri_dates)
cri_mask = np.isin(cri_dates, common)
fri_mask = np.isin(fri_dates, common)
cri_aligned = cri_sims[:, cri_mask]
fri_aligned = fri_sims[:, fri_mask]

for i in [0, 50, 100, 200, 499]:
    cfci = np.sqrt(cri_aligned[i] * fri_aligned[i])
    print(f"  Path {i}: first 12 CFCI = {np.round(cfci[:12], 1)}")
    diffs = np.diff(cfci[:12])
    print(f"            diffs = {np.round(diffs, 1)}")
