# === 01_composite_index.py ===
# Shanghai Climate-Finance Composite Index (CFCI)
#
# CFCI = sqrt(CRI × FRI)  — geometric mean, parameter-free
#
# Historical: merge CRI and FRI on overlapping months (2011-12 → 2023-12)
# Projection: path-level MC propagation with Iman-Conover rank reordering
#   → loads full MC path arrays from CRI and FRI modules
#   → applies rank correlation matching (target ρ from historical data)
#   → computes CFCI per-path, then extracts percentile envelopes
#
# References:
#   Iman & Conover (1982), Journal of Statistical Computation & Simulation
#   Junker & May (2005), Journal of Computational Finance

import importlib.util
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats
import warnings
warnings.filterwarnings("ignore")

# ── Load config ──────────────────────────────────────────────────────
_config_path = Path(__file__).resolve().parent / "00_config.py"
_spec = importlib.util.spec_from_file_location("config", _config_path)
config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config)


if __name__ == "__main__":
    t0 = time.time()
    print("=" * 60)
    print("Climate-Finance Composite Index (CFCI)")
    print("=" * 60)

    # ═════════════════════════════════════════════════════════════════
    # 1. Load historical CRI and FRI
    # ═════════════════════════════════════════════════════════════════
    print("\n[1] Loading historical indices...")

    cri = pd.read_csv(config.CRI_HISTORICAL_CSV)
    cri["date"] = pd.to_datetime(cri["date"])
    cri = cri[["date", "cri_index"]].dropna().copy()

    fri = pd.read_csv(config.FRI_HISTORICAL_CSV)
    fri["date"] = pd.to_datetime(fri["date"])
    fri = fri[["date", "fri_index"]].dropna().copy()

    print(f"  CRI: {len(cri)} months "
          f"({cri['date'].min().strftime('%Y-%m')} → "
          f"{cri['date'].max().strftime('%Y-%m')})")
    print(f"  FRI: {len(fri)} months "
          f"({fri['date'].min().strftime('%Y-%m')} → "
          f"{fri['date'].max().strftime('%Y-%m')})")

    # ═════════════════════════════════════════════════════════════════
    # 2. Compute historical CFCI (overlapping period only)
    # ═════════════════════════════════════════════════════════════════
    print("\n[2] Computing historical CFCI...")

    merged = cri.merge(fri, on="date", how="inner").sort_values("date")
    merged["cfci"] = np.sqrt(merged["cri_index"] * merged["fri_index"])

    print(f"  Overlapping period: "
          f"{merged['date'].min().strftime('%Y-%m')} → "
          f"{merged['date'].max().strftime('%Y-%m')} "
          f"({len(merged)} months)")
    print(f"  CFCI range: {merged['cfci'].min():.1f} → "
          f"{merged['cfci'].max():.1f}")
    print(f"  CFCI start: {merged['cfci'].iloc[0]:.1f}, "
          f"end: {merged['cfci'].iloc[-1]:.1f}")

    # Save historical
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    hist_out = merged[["date", "cri_index", "fri_index", "cfci"]].copy()
    hist_out["date"] = hist_out["date"].dt.strftime("%Y-%m-%d")
    hist_out.to_csv(str(config.CFCI_HISTORICAL_CSV),
                    index=False, encoding="utf-8-sig")
    print(f"  → {config.CFCI_HISTORICAL_CSV.name}: {len(hist_out)} rows")

    # ═════════════════════════════════════════════════════════════════
    # 3. Path-level MC projection CFCI (Iman-Conover rank reordering)
    # ═════════════════════════════════════════════════════════════════
    print("\n[3] Computing projection CFCI (path-level MC, Iman-Conover)...")

    # ── Iman-Conover: pair ENTIRE trajectories (not per time step) ───
    # Determines a single permutation so that the Spearman rank
    # correlation of path-level summary statistics matches the target.
    # Each CFCI path is then a coherent time series.
    #
    # Algorithm (Iman & Conover, 1982):
    #   1. Summarise each path → scalar (time-averaged index)
    #   2. Rank the two summary vectors → R (N × 2)
    #   3. Cholesky of target corr → L_t,  of current rank corr → L_0
    #   4. T = L_t @ inv(L_0);   R* = R @ T^T
    #   5. Re-rank R* column-wise → new_order
    #   6. Permute original paths by mapping sorted order through new_order

    def iman_conover_pair(cri_paths, fri_paths, target_corr):
        """Return (cri_perm, fri_perm) index arrays for path pairing."""
        N = cri_paths.shape[0]

        # summary: time-averaged index level per path
        cri_means = np.mean(cri_paths, axis=1)
        fri_means = np.mean(fri_paths, axis=1)

        # rank
        R = np.column_stack([
            sp_stats.rankdata(cri_means),
            sp_stats.rankdata(fri_means),
        ])

        # current rank correlation
        C0 = np.corrcoef(R, rowvar=False)

        # Cholesky transformation
        L_t = np.linalg.cholesky(target_corr)
        L_0 = np.linalg.cholesky(C0)
        T = L_t @ np.linalg.inv(L_0)

        # adjusted scores → re-rank
        R_star = R @ T.T
        new_order = np.column_stack([
            np.argsort(np.argsort(R_star[:, 0])),
            np.argsort(np.argsort(R_star[:, 1])),
        ])

        # permutations: row i uses path sort_idx[new_order[i]]
        sort_cri = np.argsort(cri_means)
        sort_fri = np.argsort(fri_means)

        return sort_cri[new_order[:, 0]], sort_fri[new_order[:, 1]]

    # ── Target correlation matrix ────────────────────────────────────
    rho = config.CFCI_TARGET_RHO
    target_corr = np.array([[1.0, rho],
                            [rho, 1.0]])
    print(f"  Target Spearman rho: {rho:.3f}")

    # ── Load CRI/FRI percentile CSVs for output compatibility ────────
    cri_proj = pd.read_csv(config.CRI_PROJECTION_CSV)
    cri_proj["date"] = pd.to_datetime(cri_proj["date"])
    fri_proj = pd.read_csv(config.FRI_PROJECTION_CSV)
    fri_proj["date"] = pd.to_datetime(fri_proj["date"])

    scenarios = sorted(set(cri_proj["scenario"]) & set(fri_proj["scenario"]))
    print(f"  Scenarios: {scenarios}")

    proj_results = []

    for scenario in scenarios:
        print(f"\n  [{scenario}]")

        # Load full MC path arrays
        cri_npz = np.load(str(config.CRI_MC_PATHS[scenario]))
        fri_npz = np.load(str(config.FRI_MC_PATHS[scenario]))

        cri_all = cri_npz["all_sims"]     # (N_cri, T_cri)
        fri_all = fri_npz["all_sims"]     # (N_fri, T_fri)
        cri_dates = pd.to_datetime(cri_npz["dates"])
        fri_dates = pd.to_datetime(fri_npz["dates"])

        # Align on overlapping dates
        common_dates = np.intersect1d(cri_dates, fri_dates)
        cri_mask = np.isin(cri_dates, common_dates)
        fri_mask = np.isin(fri_dates, common_dates)
        cri_paths = cri_all[:, cri_mask]   # (N_cri, T_common)
        fri_paths = fri_all[:, fri_mask]   # (N_fri, T_common)
        proj_dates = pd.DatetimeIndex(common_dates)
        T = len(proj_dates)

        N_cri = cri_paths.shape[0]
        N_fri = fri_paths.shape[0]

        # Equalise path count (subsample the larger set)
        N = min(N_cri, N_fri)
        rng = np.random.default_rng(42)
        if N_cri > N:
            cri_paths = cri_paths[rng.choice(N_cri, N, replace=False)]
        if N_fri > N:
            fri_paths = fri_paths[rng.choice(N_fri, N, replace=False)]

        print(f"    CRI paths: {cri_paths.shape}, FRI paths: {fri_paths.shape}")

        # ── Path-level IC: single permutation for entire trajectory ──
        cri_perm, fri_perm = iman_conover_pair(
            cri_paths, fri_paths, target_corr)

        cri_paired = cri_paths[cri_perm]   # (N, T)
        fri_paired = fri_paths[fri_perm]   # (N, T)

        # Verify achieved correlation
        achieved_rho = sp_stats.spearmanr(
            np.mean(cri_paired, axis=1),
            np.mean(fri_paired, axis=1))[0]
        print(f"    Achieved Spearman rho (path-level): {achieved_rho:.3f}")

        # Compute CFCI per path: geometric mean (coherent trajectories)
        cfci_paths = np.sqrt(cri_paired * fri_paired)

        # Percentile envelopes from path distribution
        p50 = np.nanpercentile(cfci_paths, 50, axis=0)
        p10 = np.nanpercentile(cfci_paths, 10, axis=0)
        p90 = np.nanpercentile(cfci_paths, 90, axis=0)

        # ── Characteristic representative path ──────────────────────────
        # Among paths with endpoint in [p40, p60], pick the one whose
        # month-to-month volatility best matches historical CFCI.
        hist_cfci_vals = merged["cfci"].values
        hist_vol = np.std(np.diff(hist_cfci_vals))
        finals = cfci_paths[:, -1]
        lo40 = np.nanpercentile(finals, 40)
        hi60 = np.nanpercentile(finals, 60)
        candidates = np.where((finals >= lo40) & (finals <= hi60))[0]
        if len(candidates) == 0:
            candidates = np.arange(cfci_paths.shape[0])
        path_vols = np.array([np.std(np.diff(cfci_paths[i]))
                              for i in candidates])
        best_idx = int(np.argmin(np.abs(path_vols - hist_vol)))
        rep_i = int(candidates[best_idx])
        cfci_rep = cfci_paths[rep_i]
        print(f"    Characteristic path: sim={rep_i}, "
              f"hist_vol={hist_vol:.2f}, path_vol={path_vols[best_idx]:.2f}")

        # Also get CRI/FRI medians for output table
        s_cri = (cri_proj[cri_proj["scenario"] == scenario]
                 [["date", "cri_index_p50"]].copy())
        s_fri = (fri_proj[fri_proj["scenario"] == scenario]
                 [["date", "fri_index_p50"]].copy())
        s_merged = s_cri.merge(s_fri, on="date", how="inner").sort_values("date")

        n_out = len(s_merged)
        s_merged["cfci_p50"] = p50[:n_out]
        s_merged["cfci_p10"] = p10[:n_out]
        s_merged["cfci_p90"] = p90[:n_out]
        s_merged["cfci_rep"] = cfci_rep[:n_out]
        s_merged["scenario"] = scenario

        proj_results.append(s_merged[[
            "date", "scenario",
            "cri_index_p50", "fri_index_p50",
            "cfci_p50", "cfci_p10", "cfci_p90", "cfci_rep",
        ]])

        end = s_merged.iloc[-1]
        print(f"    CFCI@2050 = {end['cfci_p50']:.0f} "
              f"[{end['cfci_p10']:.0f}, {end['cfci_p90']:.0f}]  "
              f"rep={end['cfci_rep']:.0f}")

        # Per-time-step correlation diagnostic
        step_rhos = np.array([
            sp_stats.spearmanr(cri_paired[:, t], fri_paired[:, t])[0]
            for t in range(T)])
        print(f"    Time-step rho: mean={step_rhos.mean():.3f}, "
              f"range=[{step_rhos.min():.3f}, {step_rhos.max():.3f}]")

    proj_out = pd.concat(proj_results, ignore_index=True)
    proj_out["date"] = proj_out["date"].dt.strftime("%Y-%m-%d")
    proj_out.to_csv(str(config.CFCI_PROJECTION_CSV),
                    index=False, encoding="utf-8-sig")
    print(f"  → {config.CFCI_PROJECTION_CSV.name}: {len(proj_out)} rows")

    # ═════════════════════════════════════════════════════════════════
    # 4. Summary
    # ═════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("CFCI SUMMARY")
    print("=" * 60)

    # Historical trajectory
    first = merged.iloc[0]
    last = merged.iloc[-1]
    peak = merged.loc[merged["cfci"].idxmax()]
    print(f"  Historical CFCI:")
    print(f"    Start: {first['cfci']:.0f} ({first['date'].strftime('%Y-%m')})")
    print(f"    End:   {last['cfci']:.0f} ({last['date'].strftime('%Y-%m')})")
    print(f"    Peak:  {peak['cfci']:.0f} ({peak['date'].strftime('%Y-%m')})")
    print(f"    Growth: {(last['cfci']/first['cfci'] - 1)*100:.0f}% total, "
          f"{((last['cfci']/first['cfci'])**(12/len(merged)) - 1)*100:.1f}% annualized")

    # CRI-FRI-CFCI correlation matrix
    corr_cf = merged["cri_index"].corr(merged["fri_index"])
    corr_cc = merged["cri_index"].corr(merged["cfci"])
    corr_fc = merged["fri_index"].corr(merged["cfci"])
    print(f"\n  Correlation matrix (historical overlap):")
    print(f"    CRI-FRI:  r = {corr_cf:.3f}")
    print(f"    CRI-CFCI: r = {corr_cc:.3f}")
    print(f"    FRI-CFCI: r = {corr_fc:.3f}")

    print(f"\n  Elapsed: {time.time() - t0:.1f}s")
    print("=" * 60)
