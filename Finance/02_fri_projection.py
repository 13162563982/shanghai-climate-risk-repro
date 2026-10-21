# === 02_fri_projection.py ===
# Shanghai Finance Risk Index (FRI) — Forward Projection 2025-07 → 2050-12
#
# Merton Jump-Diffusion Framework (Merton 1976 + Case-Shiller 1989):
#
#   Housing price follows mean-reverting jump-diffusion GBM:
#     d(ln P) = θ(μ_trend − ln P) dt + σ dW + J dN
#
#   Where:
#     θ   — mean-reversion speed toward HP trend (Case-Shiller, 1989)
#     σ   — diffusion volatility (non-jump component)
#     N   — Poisson(λ) jump arrivals (Merton, 1976)
#     J   — log-normal jump sizes (market crashes / surges)
#
#   Sub-indicators are DERIVED from simulated price paths (not independent):
#     Price Gap   = |P / P_trend − 1|     (deviation from HP trend)
#     Realized Vol = rolling std(Δ ln P)   (12-mo log-return vol)
#     Climate CVaR = scaled from CRI scenario (tail-risk channel)
#
#   Key advantage: price crash → price gap ↑ AND volatility ↑ simultaneously,
#   capturing the natural correlation structure that independent OU misses.
#
#   Climate scenarios affect jump intensity (λ) and CVaR scaling:
#     Higher climate risk → more frequent extreme events → more price jumps
#
# Literature:
#   Merton (1974): Structural credit risk, asset value as GBM
#   Merton (1976): Jump-diffusion extension for rare events
#   Case & Shiller (1989): Housing prices exhibit mean-reversion
#   Baldauf et al. (2020): Climate risk affects housing price discount
#
# Monte Carlo: 500 paths, output p10/p50/p90 envelopes.

import hashlib
import importlib.util
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
# Jump-Diffusion Parameter Fitting
# ═══════════════════════════════════════════════════════════════════════

def _hp_filter(y, lam):
    """Hodrick-Prescott filter (sparse matrix, fast).
    Returns trend component τ.
    """
    from scipy import sparse
    from scipy.sparse.linalg import spsolve
    n = len(y)
    e = sparse.eye(n, format="csc")
    D = sparse.diags([1, -2, 1], [0, 1, 2], shape=(n - 2, n), format="csc")
    trend = spsolve(e + lam * D.T @ D, y)
    return trend


def fit_jump_diffusion(prices, hp_trend, jump_threshold=2.0):
    """Fit Merton jump-diffusion parameters from historical price data.

    Returns dict with:
      sigma_diff  — monthly diffusion volatility (non-jump)
      theta_mr    — mean-reversion speed toward HP trend
      lambda_jump — monthly jump intensity (Poisson rate)
      mu_jump     — mean jump size (in log space)
      sigma_jump  — jump size volatility
      last_log_price — log(P) at end of history
      last_log_trend — log(trend) at end of history
      trend_growth   — recent annualized HP trend growth rate
    """
    from scipy import stats as sp_stats

    log_returns = np.diff(np.log(prices))
    n = len(log_returns)

    # ── Jump detection (threshold method) ─────────────────────────
    lr_std = np.std(log_returns)
    lr_mean = np.mean(log_returns)
    jump_mask = np.abs(log_returns - lr_mean) > jump_threshold * lr_std

    n_jumps = int(np.sum(jump_mask))
    lambda_jump = n_jumps / n  # monthly intensity

    if n_jumps >= 2:
        jump_sizes = log_returns[jump_mask]
        mu_jump = float(np.mean(jump_sizes))
        sigma_jump = float(np.std(jump_sizes))
    elif n_jumps == 1:
        mu_jump = float(log_returns[jump_mask][0])
        sigma_jump = abs(mu_jump) * 0.5  # fallback
    else:
        mu_jump = -0.05
        sigma_jump = 0.04
        lambda_jump = 0.02  # low default

    # ── Diffusion volatility (non-jump returns only) ──────────────
    non_jump_lr = log_returns[~jump_mask]
    sigma_diff = float(np.std(non_jump_lr))

    # ── Mean-reversion speed from price gap ───────────────────────
    gap = prices / hp_trend - 1.0
    dg = np.diff(gap)
    slope, _, _, _, _ = sp_stats.linregress(gap[:-1], dg)
    theta_mr = float(max(-slope, 0.01))  # ensure positive reversion

    # ── Trend growth rate (use recent period for forward projection)
    log_trend = np.log(hp_trend)
    recent_years = 5
    recent_n = min(recent_years * 12, len(log_trend) - 1)
    trend_growth = float(np.diff(log_trend)[-recent_n:].mean() * 12)

    return {
        "sigma_diff": sigma_diff,
        "theta_mr": theta_mr,
        "lambda_jump": lambda_jump,
        "mu_jump": mu_jump,
        "sigma_jump": sigma_jump,
        "n_jumps": n_jumps,
        "last_log_price": float(np.log(prices[-1])),
        "last_log_trend": float(np.log(hp_trend[-1])),
        "trend_growth": trend_growth,
    }


# ═══════════════════════════════════════════════════════════════════════
# MinMax normalisation (using historical range, no upper clip for climate)
# ═══════════════════════════════════════════════════════════════════════

def _mean_norm_with_ref(arr, mu):
    """Mean-division normalise using reference mean μ.
    Consistent with historical _mean_norm() in 01_finance_risk_index.py.
    """
    if abs(mu) < 1e-12:
        return np.zeros_like(arr)
    return arr / mu


if __name__ == "__main__":
    t0 = time.time()
    print("=" * 60)
    print("FRI Projection — Merton Jump-Diffusion Monte Carlo")
    print("=" * 60)

    # ── Load historical FRI data ─────────────────────────────────────
    fri = pd.read_csv(config.FRI_OUTPUT_CSV)
    fri["date"] = pd.to_datetime(fri["date"])

    # ── Load CRI projection (for CVaR scaling) ───────────────────────
    proj_cri = pd.read_csv(config.CLIMATE_PROJECTION_CSV)
    proj_cri["date"] = pd.to_datetime(proj_cri["date"])

    # ── Load historical CVaR ─────────────────────────────────────────
    cvar_hist = pd.read_csv(config.CLIMATE_CVAR_CSV)
    cvar_hist["date"] = pd.to_datetime(cvar_hist["date"])

    print(f"\n[1] Historical FRI: {len(fri)} months "
          f"({fri['date'].min().strftime('%Y-%m')} → "
          f"{fri['date'].max().strftime('%Y-%m')})")

    # ═════════════════════════════════════════════════════════════════
    # 2. Fit Merton jump-diffusion from historical prices
    # ═════════════════════════════════════════════════════════════════
    print("\n[2] Fitting Merton jump-diffusion parameters...")

    prices = fri["price"].values.astype(float)
    hp_trend = fri["price_trend"].values.astype(float)

    jd = fit_jump_diffusion(prices, hp_trend)

    print(f"  Diffusion σ:  {jd['sigma_diff']:.6f}/mo "
          f"({jd['sigma_diff']*np.sqrt(12):.4f} annualized)")
    print(f"  Mean-reversion θ: {jd['theta_mr']:.4f}/mo "
          f"(half-life {np.log(2)/jd['theta_mr']:.1f} mo)")
    print(f"  Jump λ: {jd['lambda_jump']:.4f}/mo "
          f"({jd['n_jumps']} jumps detected)")
    print(f"  Jump size: μ_J={jd['mu_jump']:.4f}, σ_J={jd['sigma_jump']:.4f}")
    print(f"  Trend growth (recent 5yr): {jd['trend_growth']:.4f}/yr")
    print(f"  Last log(price)={jd['last_log_price']:.4f}, "
          f"log(trend)={jd['last_log_trend']:.4f}")

    # ── Historical normalisation ranges ───────────────────────────────
    gap_mean = fri["price_gap"].mean()
    vol_mean = fri["realized_vol"].mean()
    clim_mean = fri["climate_risk"].mean()

    # ── CVaR projection setup ─────────────────────────────────────────
    haz_full = pd.read_csv(config.CLIMATE_HAZARD_CSV)
    haz_full["date"] = pd.to_datetime(haz_full["date"])
    cri_12m_hist = haz_full["cri_12m"].dropna()
    cri_base = cri_12m_hist.iloc[0]
    cri_last = cri_12m_hist.iloc[-1]
    cvar_last = cvar_hist["cvar_12m"].dropna().iloc[-1]

    print(f"\n  Normalisation reference means:")
    print(f"    Price Gap:    {gap_mean:.6f}")
    print(f"    Realized Vol: {vol_mean:.6f}")
    print(f"    Climate CVaR: {clim_mean:.6f}")

    # ═════════════════════════════════════════════════════════════════
    # 3. Setup projection timeline
    # ═════════════════════════════════════════════════════════════════
    last_hist_date = fri["date"].max()
    proj_start = last_hist_date + pd.DateOffset(months=1)
    proj_end = pd.Timestamp(f"{config.FRI_PROJECTION_END_YEAR}-12-01")
    proj_dates = pd.date_range(proj_start, proj_end, freq="MS")
    n_steps = len(proj_dates)

    print(f"\n[3] Projection: {proj_start.strftime('%Y-%m')} → "
          f"{proj_end.strftime('%Y-%m')} ({n_steps} months)")
    print(f"    N_sim = {config.FRI_N_SIM}")

    # ═════════════════════════════════════════════════════════════════
    # 4. Monte Carlo: Merton jump-diffusion price simulation
    # ═════════════════════════════════════════════════════════════════
    print("\n[4] Running Merton jump-diffusion Monte Carlo...")

    N = config.FRI_N_SIM
    rng = np.random.default_rng(42)

    scenarios = ["Historical Baseline", "SSP2-4.5", "SSP5-8.5"]
    scenario_paths = {}

    # SSP scenario adjustments for jump intensity:
    # Higher climate risk → more frequent extreme events → more market
    # disruption.  Aligned with CRI_SSP_DAMAGE_ADJ from Climate config.
    # λ multipliers: Baseline=1.0, SSP2-4.5=1.10, SSP5-8.5=1.20
    # (housing market jumps are partly climate-driven: typhoon damage,
    #  flood risk repricing — Baldauf et al. 2020)
    scenario_lambda_mult = {
        "Historical Baseline": 1.00,
        "SSP2-4.5":            1.10,
        "SSP5-8.5":            1.20,
    }

    # Historical FRI baseline for index computation
    hist_fri_12m = fri["fri_12m"].dropna()
    fri_base = hist_fri_12m.iloc[0]

    # Historical tail for 12-mo rolling warm-up
    hist_lr_tail = np.diff(np.log(prices))[-12:]  # last 12 log-returns
    hist_raw_tail = fri["fri_raw"].dropna().values[-11:]

    # Pre-generate shared diffusion noise (all scenarios share same
    # price path randomness, differentiated only by λ and CVaR)
    W_noise = rng.standard_normal((N, n_steps))

    for scenario in scenarios:
        print(f"\n  Scenario: {scenario}")
        lambda_sc = jd["lambda_jump"] * scenario_lambda_mult[scenario]

        # ── CVaR projection: scale by CRI scenario growth ────────
        s_cri = proj_cri[proj_cri["scenario"] == scenario].copy()
        s_cri = s_cri.sort_values("date")
        cri_proj_dates = s_cri["date"].values
        cri_proj_p50 = s_cri["cri_index_p50"].values * cri_base / 100.0
        cri_df = pd.DataFrame({"date": pd.to_datetime(cri_proj_dates),
                               "cri_p50": cri_proj_p50})
        proj_df = pd.DataFrame({"date": proj_dates}).merge(
            cri_df, on="date", how="left")
        proj_df["cri_p50"] = (proj_df["cri_p50"]
                              .interpolate(method="linear")
                              .ffill().bfill())
        cri_ratio = proj_df["cri_p50"].values / cri_last
        cvar_proj = cvar_last * cri_ratio

        # Climate channel: normalise with historical mean (mean-division)
        clim_norm = cvar_proj / clim_mean  # (n_steps,)

        print(f"    λ_jump (scenario): {lambda_sc:.4f}/mo")
        print(f"    CRI ratio range: {cri_ratio.min():.3f} — {cri_ratio.max():.3f}")
        print(f"    CVaR proj range: {cvar_proj.min():.6f} — {cvar_proj.max():.6f}")

        # ── Simulate N price paths ────────────────────────────────
        # Scenario-specific RNG for jumps (so jump realisations differ)
        rng_jump = np.random.default_rng(
            42 + int(hashlib.sha256(scenario.encode()).hexdigest(), 16) % 10_000)

        all_gap_paths = np.empty((N, n_steps))
        all_vol_paths = np.empty((N, n_steps))

        for sim_i in range(N):
            # Log-price path via mean-reverting jump-diffusion
            log_P = np.empty(n_steps + 1)
            log_P[0] = jd["last_log_price"]

            # Projected HP trend: continue recent growth rate
            log_trend = np.empty(n_steps)
            for t in range(n_steps):
                log_trend[t] = (jd["last_log_trend"]
                                + jd["trend_growth"] * (t + 1) / 12.0)

            for t in range(n_steps):
                # Mean-reversion toward projected trend
                mean_rev = jd["theta_mr"] * (log_trend[t] - log_P[t])

                # Diffusion
                dW = jd["sigma_diff"] * W_noise[sim_i, t]

                # Jump (Poisson arrivals with log-normal sizes)
                n_j = rng_jump.poisson(lambda_sc)
                J = 0.0
                if n_j > 0:
                    J = float(np.sum(
                        rng_jump.normal(jd["mu_jump"], jd["sigma_jump"], n_j)))

                # Euler step: d(ln P) = θ(ln_trend - ln_P)dt + σ dW + J dN
                log_P[t + 1] = log_P[t] + mean_rev + dW + J

            # Derive sub-indicators from simulated price path
            P_sim = np.exp(log_P[1:])          # simulated prices
            trend_sim = np.exp(log_trend)       # projected trend

            # Price Gap: |P / trend - 1|
            gap_sim = np.abs(P_sim / trend_sim - 1.0)

            # Realized Vol: rolling 12-mo std of log returns
            # Prepend historical log-returns for rolling warmup
            lr_sim = np.diff(log_P)  # length n_steps
            lr_combined = np.concatenate([hist_lr_tail, lr_sim])
            vol_series = pd.Series(lr_combined).rolling(
                12, min_periods=6).std().values
            vol_sim = vol_series[len(hist_lr_tail):]

            all_gap_paths[sim_i] = gap_sim
            all_vol_paths[sim_i] = vol_sim

        # ── Normalise and composite ───────────────────────────────
        gap_norm = _mean_norm_with_ref(all_gap_paths, gap_mean)
        vol_norm = _mean_norm_with_ref(all_vol_paths, vol_mean)

        w1, w2, w3 = config.FRI_WEIGHTS
        fri_raw_paths = (
            w1 * gap_norm
            + w2 * vol_norm
            + w3 * clim_norm[np.newaxis, :]  # broadcast (1, n_steps)
        )

        # 12-month rolling mean per path (warmup with historical tail)
        fri_12m_paths = np.full_like(fri_raw_paths, np.nan)
        for sim in range(N):
            combined = np.concatenate([hist_raw_tail, fri_raw_paths[sim]])
            roll = pd.Series(combined).rolling(12, min_periods=6).mean().values
            fri_12m_paths[sim] = roll[len(hist_raw_tail):]

        # Convert to FRI index (base-100)
        fri_index_paths = config.FRI_BASE_INDEX * fri_12m_paths / fri_base

        # Compute envelopes
        p10 = np.nanpercentile(fri_index_paths, 10, axis=0)
        p50 = np.nanpercentile(fri_index_paths, 50, axis=0)
        p90 = np.nanpercentile(fri_index_paths, 90, axis=0)

        # ── Export full MC path arrays for Composite module (Iman-Conover) ──
        _skey_map = {
            "Historical Baseline": "baseline",
            "SSP2-4.5": "ssp245",
            "SSP5-8.5": "ssp585",
        }
        _npz_path = config.RESULTS_DIR / f"fri_mc_paths_{_skey_map[scenario]}.npz"
        _date_strs = np.array([d.strftime("%Y-%m-%d") for d in proj_dates])
        np.savez_compressed(
            str(_npz_path),
            all_sims=fri_index_paths,
            dates=_date_strs,
        )
        print(f"    Saved {_npz_path.name}: shape={fri_index_paths.shape}")

        # Store for characteristic-path selection after loop
        scenario_paths[scenario] = {
            "fri_index_paths": fri_index_paths,
            "p50": p50, "p10": p10, "p90": p90,
        }

        end_p50 = p50[-1]
        print(f"    End FRI (p50): {end_p50:.0f}")
        print(f"    Range [p10, p90] at 2050: [{p10[-1]:.0f}, {p90[-1]:.0f}]")

    # ── Characteristic representative path (per scenario) ─────────────
    # FRI has independent jump processes per scenario, so the same path
    # index can behave very differently.  Select per scenario:
    # among paths with endpoint in [p40, p60], pick the one whose
    # month-to-month volatility best matches historical FRI volatility.
    hist_fri_index = fri["fri_index"].dropna().values if "fri_index" in fri.columns else None
    if hist_fri_index is not None and len(hist_fri_index) > 1:
        hist_vol = np.std(np.diff(hist_fri_index))
    else:
        hist_vol = np.std(np.diff(fri["fri_12m"].dropna().values))

    # Build results with rep column
    results = []
    for scenario in scenarios:
        sp = scenario_paths[scenario]
        p50, p10, p90 = sp["p50"], sp["p10"], sp["p90"]
        paths = sp["fri_index_paths"]

        # Per-scenario characteristic path selection
        finals = paths[:, -1]
        lo40 = np.nanpercentile(finals, 40)
        hi60 = np.nanpercentile(finals, 60)
        candidates = np.where((finals >= lo40) & (finals <= hi60))[0]
        if len(candidates) == 0:
            candidates = np.arange(paths.shape[0])
        path_vols = np.array([np.std(np.diff(paths[i])) for i in candidates])
        best_idx = int(np.argmin(np.abs(path_vols - hist_vol)))
        rep_i = int(candidates[best_idx])
        rep = paths[rep_i]
        print(f"  {scenario}: char path sim={rep_i}, "
              f"hist_vol={hist_vol:.2f}, path_vol={path_vols[best_idx]:.2f}, "
              f"end_rep={rep[-1]:.0f}")

        for i in range(n_steps):
            results.append({
                "date": proj_dates[i],
                "year": proj_dates[i].year,
                "month": proj_dates[i].month,
                "scenario": scenario,
                "fri_index_rep": float(rep[i]),
                "fri_index_p50": p50[i],
                "fri_index_p10": p10[i],
                "fri_index_p90": p90[i],
            })

    # ═════════════════════════════════════════════════════════════════
    # 5. Save projection
    # ═════════════════════════════════════════════════════════════════
    print("\n[5] Saving projection...")
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    out = pd.DataFrame(results)
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(str(config.FRI_PROJECTION_CSV), index=False, encoding="utf-8-sig")
    print(f"  → {config.FRI_PROJECTION_CSV.name}: {len(out)} rows")

    # ═════════════════════════════════════════════════════════════════
    # 6. Summary
    # ═════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("PROJECTION SUMMARY")
    print("=" * 60)

    last_fri = fri.dropna(subset=["fri_index"])["fri_index"].iloc[-1]
    print(f"  Historical end: FRI = {last_fri:.0f}")

    for scenario in scenarios:
        s_data = out[out["scenario"] == scenario]
        end = s_data.iloc[-1]
        print(f"  {scenario:>20s}: FRI = {end['fri_index_p50']:.0f} "
              f"[{end['fri_index_p10']:.0f}, {end['fri_index_p90']:.0f}] at 2050")

    print(f"\n  Elapsed: {time.time() - t0:.1f}s")
    print("=" * 60)
