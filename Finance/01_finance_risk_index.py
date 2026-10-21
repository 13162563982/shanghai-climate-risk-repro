# === 01_finance_risk_index.py ===
# Shanghai Finance Risk Index (FRI)
#
# Three sub-indicators, all parameter-free:
#   1. Price Gap      — |P / P_HP - 1|   (HP-filter trend deviation)
#   2. Realized Vol   — std(Δ¹ ln P)     (12-mo rolling log-return vol)
#   3. Climate CVaR   — rolling 5-yr CVaR₅% from stochastic TC event set
#
# FRI = equal-weight average of min-max-normalised sub-indicators
# FRI Index = base-100, anchored at first valid month
#
# Output: results/shanghai_finance_risk_index.csv

import importlib.util
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

# ── Load config ──────────────────────────────────────────────────────
_config_path = Path(__file__).resolve().parent / "00_config.py"
_spec = importlib.util.spec_from_file_location("config", _config_path)
config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config)

# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _mean_norm(arr):
    """Mean-division normalise (center ≈ 1.0).  NaN-safe.
    More stable than min-max: insensitive to sample extremes,
    so FRI level is robust to sub-indicator weight reallocation.
    """
    mu = np.nanmean(arr)
    if abs(mu) < 1e-12:
        return np.zeros_like(arr)
    return arr / mu


def _hp_filter(y, lam):
    """Hodrick-Prescott filter (sparse matrix, fast).
    Returns trend component τ.
    """
    from scipy import sparse
    from scipy.sparse.linalg import spsolve
    n = len(y)
    e = sparse.eye(n, format="csc")
    # Second-difference operator D
    D = sparse.diags([1, -2, 1], [0, 1, 2], shape=(n - 2, n), format="csc")
    trend = spsolve(e + lam * D.T @ D, y)
    return trend


if __name__ == "__main__":
    t0 = time.time()
    print("=" * 60)
    print("Finance Risk Index (FRI) — Data-Driven Computation")
    print("=" * 60)

    # ═════════════════════════════════════════════════════════════════
    # 1. Load city-level housing price
    # ═════════════════════════════════════════════════════════════════
    print("\n[1] Loading city housing price data...")
    price_wide = pd.read_excel(config.CITY_PRICE_EXCEL)

    # Extract month columns (YYYY-MM format)
    month_cols = [str(c) for c in price_wide.columns
                  if re.fullmatch(r"\d{4}-\d{2}", str(c))]
    meta_cols = [c for c in ["省名", "省代码", "市名", "市代码"]
                 if c in price_wide.columns]

    price_long = price_wide.melt(
        id_vars=meta_cols, value_vars=month_cols,
        var_name="year_month", value_name="price",
    )
    price_long["price"] = pd.to_numeric(price_long["price"], errors="coerce")
    price_long = price_long.dropna(subset=["price"]).copy()
    price_long["date"] = pd.to_datetime(price_long["year_month"],
                                        format="%Y-%m", errors="coerce")
    price_long = (price_long.dropna(subset=["date"])
                  .sort_values("date")
                  .drop_duplicates(subset=["date"])
                  .reset_index(drop=True))

    price = price_long[["date", "price"]].copy()
    price["year"] = price["date"].dt.year
    price["month"] = price["date"].dt.month

    print(f"  Price data: {len(price)} months, "
          f"{price['date'].min().strftime('%Y-%m')} → "
          f"{price['date'].max().strftime('%Y-%m')}")

    # ═════════════════════════════════════════════════════════════════
    # 2. Load Climate CVaR (from stochastic event set)
    # ═════════════════════════════════════════════════════════════════
    print("\n[2] Loading Climate CVaR data...")
    cvar = pd.read_csv(config.CLIMATE_CVAR_CSV)
    cvar["date"] = pd.to_datetime(cvar["date"])
    cvar = cvar.sort_values("date").reset_index(drop=True)
    cvar_col = cvar[["date", "cvar_12m"]].copy()

    cvar_valid = cvar_col["cvar_12m"].dropna()
    print(f"  CVaR data: {len(cvar)} months, "
          f"CVaR 12m range: {cvar_valid.min():.6f} — {cvar_valid.max():.6f}")

    # ═════════════════════════════════════════════════════════════════
    # 3. Compute sub-indicator 1: Price Gap (HP deviation)
    # ═════════════════════════════════════════════════════════════════
    print("\n[3] Computing Price Gap (HP filter deviation)...")

    p_vals = price["price"].values.astype(float)
    trend = _hp_filter(p_vals, config.HP_LAMBDA)
    price["price_trend"] = trend
    price["price_gap"] = np.abs(p_vals / trend - 1.0)

    print(f"  HP λ = {config.HP_LAMBDA:,} (Ravn-Uhlig monthly convention)")
    print(f"  Price gap range: {price['price_gap'].min():.4f} — "
          f"{price['price_gap'].max():.4f}")

    # ═════════════════════════════════════════════════════════════════
    # 4. Compute sub-indicator 2: Realized Volatility
    # ═════════════════════════════════════════════════════════════════
    print("\n[4] Computing Realized Volatility (12-mo rolling)...")

    price["log_return"] = np.log(price["price"]).diff()
    price["realized_vol"] = (
        price["log_return"]
        .rolling(config.VOLATILITY_WINDOW, min_periods=6)
        .std()
    )

    print(f"  Window = {config.VOLATILITY_WINDOW} months")
    vol_valid = price["realized_vol"].dropna()
    print(f"  Volatility range: {vol_valid.min():.6f} — {vol_valid.max():.6f}")

    # ═════════════════════════════════════════════════════════════════
    # 5. Compute sub-indicator 3: Climate CVaR
    # ═════════════════════════════════════════════════════════════════
    print("\n[5] Merging Climate CVaR channel...")

    # Climate CVaR = rolling 5-year CVaR₅% from stochastic TC event set.
    # This is a tail-risk measure (worst 5% mean loss ratio) — distinct
    # from CRI which is a mean hazard intensity.  No double counting.
    price = price.merge(cvar_col, on="date", how="left")
    price["cvar_12m"] = price["cvar_12m"].interpolate(method="linear")
    price["cvar_12m"] = price["cvar_12m"].bfill()

    price["climate_risk"] = price["cvar_12m"]

    cr_valid = price["climate_risk"].dropna()
    print(f"  Climate CVaR range: "
          f"{cr_valid.min():.6f} — {cr_valid.max():.6f}")
    print(f"  Valid months: {len(cr_valid)} / {len(price)}")

    # ═════════════════════════════════════════════════════════════════
    # 6. Normalise and composite
    # ═════════════════════════════════════════════════════════════════
    print("\n[6] Normalising sub-indicators and computing FRI...")

    # Only compute FRI where all three sub-indicators are valid
    valid_mask = (price["price_gap"].notna()
                  & price["realized_vol"].notna()
                  & price["climate_risk"].notna())

    price["gap_norm"] = np.nan
    price["vol_norm"] = np.nan
    price["climate_norm"] = np.nan
    price["fri_raw"] = np.nan

    if valid_mask.sum() > 0:
        price.loc[valid_mask, "gap_norm"] = _mean_norm(
            price.loc[valid_mask, "price_gap"].values)
        price.loc[valid_mask, "vol_norm"] = _mean_norm(
            price.loc[valid_mask, "realized_vol"].values)
        price.loc[valid_mask, "climate_norm"] = _mean_norm(
            price.loc[valid_mask, "climate_risk"].values)

        w1, w2, w3 = config.FRI_WEIGHTS
        price.loc[valid_mask, "fri_raw"] = (
            w1 * price.loc[valid_mask, "gap_norm"].values
            + w2 * price.loc[valid_mask, "vol_norm"].values
            + w3 * price.loc[valid_mask, "climate_norm"].values
        )

    # 12-month rolling mean (consistent with CRI smoothing)
    price["fri_12m"] = (
        price["fri_raw"]
        .rolling(config.VOLATILITY_WINDOW, min_periods=6)
        .mean()
    )

    # Base-100 index (anchor at first valid 12m value)
    first_valid_12m = price["fri_12m"].dropna().iloc[0]
    price["fri_index"] = (
        config.FRI_BASE_INDEX * price["fri_12m"] / first_valid_12m
    )

    print(f"  FRI raw range:   {price['fri_raw'].min():.4f} — "
          f"{price['fri_raw'].max():.4f}")
    print(f"  FRI 12m range:   {price['fri_12m'].dropna().min():.4f} — "
          f"{price['fri_12m'].dropna().max():.4f}")
    print(f"  FRI index range: {price['fri_index'].dropna().min():.1f} — "
          f"{price['fri_index'].dropna().max():.1f}")

    # ═════════════════════════════════════════════════════════════════
    # 7. Save output
    # ═════════════════════════════════════════════════════════════════
    print("\n[7] Saving output...")

    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    out = price[[
        "date", "year", "month",
        "price", "price_trend",
        "price_gap", "realized_vol", "climate_risk",
        "gap_norm", "vol_norm", "climate_norm",
        "fri_raw", "fri_12m", "fri_index",
    ]].copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(str(config.FRI_OUTPUT_CSV), index=False, encoding="utf-8-sig")

    print(f"  → {config.FRI_OUTPUT_CSV.name}: {len(out)} rows")

    # ═════════════════════════════════════════════════════════════════
    # 8. Summary statistics
    # ═════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    fri_valid = price.dropna(subset=["fri_index"])
    if len(fri_valid) > 0:
        first = fri_valid.iloc[0]
        last = fri_valid.iloc[-1]
        peak = fri_valid.loc[fri_valid["fri_index"].idxmax()]
        trough = fri_valid.loc[fri_valid["fri_index"].idxmin()]

        print(f"  Period:  {first['date']} → {last['date']} "
              f"({len(fri_valid)} months)")
        print(f"  Start:   FRI = {first['fri_index']:.1f}")
        print(f"  End:     FRI = {last['fri_index']:.1f}")
        print(f"  Peak:    FRI = {peak['fri_index']:.1f} "
              f"({peak['date']})")
        print(f"  Trough:  FRI = {trough['fri_index']:.1f} "
              f"({trough['date']})")

        # Correlation with CRI (if overlapping period exists)
        haz = pd.read_csv(config.CLIMATE_HAZARD_CSV)
        haz["date"] = pd.to_datetime(haz["date"])
        cri_12m = haz[["date", "cri_index"]].copy()
        cri_12m.columns = ["date", "cri_index"]
        merged = fri_valid.merge(cri_12m, on="date", how="inner")
        if len(merged) > 12:
            corr = merged["fri_index"].corr(merged["cri_index"])
            print(f"\n  FRI-CRI correlation (overlapping {len(merged)} mo): "
                  f"r = {corr:.3f}")

    print(f"\n  Elapsed: {time.time() - t0:.1f}s")
    print("=" * 60)
