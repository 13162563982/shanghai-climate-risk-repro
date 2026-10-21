"""Analyze historical housing price dynamics for jump-diffusion parameter fitting."""
import pandas as pd
import numpy as np
from scipy import stats

fri = pd.read_csv('output/results/shanghai_finance_risk_index.csv')
price = fri['price'].values

# Log returns
lr = np.diff(np.log(price))
print("=== Historical Housing Price Statistics ===")
print(f"N months: {len(price)}, period: {fri['date'].iloc[0]} to {fri['date'].iloc[-1]}")
print(f"Price range: {price.min():.0f} to {price.max():.0f}")
print()

print("=== Log Returns ===")
print(f"Monthly mean: {lr.mean():.6f} ({lr.mean()*12:.4f} annualized)")
print(f"Monthly std:  {lr.std():.6f} ({lr.std()*np.sqrt(12):.4f} annualized)")
print(f"Skewness: {pd.Series(lr).skew():.3f}")
print(f"Kurtosis: {pd.Series(lr).kurtosis():.3f}")
print()

# Jump detection (2-sigma threshold)
threshold = 2.0 * lr.std()
jump_mask = np.abs(lr - lr.mean()) > threshold
jumps = lr[jump_mask]
print("=== Jump Detection (2-sigma threshold) ===")
print(f"Jump months: {len(jumps)} / {len(lr)}")
print(f"Jump intensity lambda: {len(jumps)/len(lr):.4f}/month")
if len(jumps) > 0:
    print(f"Jump sizes: mean={jumps.mean():.6f}, std={jumps.std():.6f}")
    # Show individual jumps with dates
    jump_idx = np.where(jump_mask)[0]
    for idx in jump_idx:
        print(f"  {fri['date'].iloc[idx+1]}: log-return = {lr[idx]:+.4f}")
print()

# Non-jump returns (for diffusion vol)
non_jump_lr = lr[~jump_mask]
print("=== Diffusion Volatility (non-jump returns) ===")
print(f"Non-jump monthly std: {non_jump_lr.std():.6f} ({non_jump_lr.std()*np.sqrt(12):.4f} annualized)")
print()

# Mean-reversion from price gap
trend = fri['price_trend'].values
gap = price / trend - 1
dg = np.diff(gap)
slope, intercept, _, _, _ = stats.linregress(gap[:-1], dg)
theta_gap = -slope
print("=== Mean-Reversion (Price Gap → HP trend) ===")
print(f"theta_gap (reversion speed): {theta_gap:.4f}/month")
print(f"half-life: {np.log(2)/max(theta_gap, 0.001):.1f} months")
print(f"Last price gap: {gap[-1]:.4f}")
print(f"Last 12m mean gap: {gap[-12:].mean():.4f}")
print()

# Trend growth rate
log_trend = np.log(trend)
trend_growth_annual = np.diff(log_trend).mean() * 12
print("=== Trend Growth ===")
print(f"Annualized HP trend growth: {trend_growth_annual:.4f}")
print(f"Recent 3yr trend growth: {np.diff(log_trend)[-36:].mean()*12:.4f}")
print(f"Last trend value: {trend[-1]:.0f}")
print(f"Last price: {price[-1]:.0f}")
