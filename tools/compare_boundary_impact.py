"""
_compare_boundary_impact.py
===========================
Step 2c / 2d of the boundary-replacement plan: compare pipeline outputs
produced with the official TianDiTu GS(2024)0650 district boundary against
the frozen pre-replacement baseline.

Baseline  : V8_ROOT/_backup_边界替换_20261016/
Current   : V8_ROOT/Climate/output/

Produces a Markdown report and prints the same tables to stdout.

Aggregations mirror _audit_manuscript_consistency.py exactly:
  - city totals      : groupby(["scenario","defense_profile"])[EAL_*].sum()
  - district ranking : defense[(scenario=="historical") &
                               (defense_profile=="baseline_nodef")].nlargest(5,"EAL_compound")

Usage:
    python _compare_boundary_impact.py [--out PATH] [--tol-dist 0.5] [--tol-city 0.05]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

NEWROOT = Path(__file__).resolve().parent.parent
CLIMATE_OUT = NEWROOT / "Climate" / "output"
# Baseline = the frozen legacy-boundary snapshot (WP4 archives it under
# output_archive/baseline_legacy_<ts>/). Resolved in main(); override with --baseline.
BASELINE = None

EAL_FILE = "defense_sensitivity/defense_profile_eal.csv"
SVI_FILE = "svi_by_district.csv"

CITY_KEY = ["scenario", "defense_profile"]
EAL_COLS = ["EAL_compound", "EAL_wind", "EAL_surge"]
DIST_SCENARIO = "historical"
DIST_PROFILE = "baseline_nodef"


def _load(root: Path, rel: str):
    p = root / rel
    return pd.read_csv(p) if p.exists() else None


def _rel_change(new, old):
    old = pd.Series(old, dtype="float64").replace(0, pd.NA)
    return (pd.Series(new, dtype="float64") - old) / old * 100.0


def _output_root(base: Path) -> Path:
    """Accept either <base>/Climate/output or a directory that IS the output root."""
    cand = base / "Climate" / "output"
    return cand if cand.exists() else base


def _resolve_baseline(explicit):
    """Resolve the legacy-boundary baseline snapshot written by WP4.

    A relative --baseline is resolved against the PACKAGE ROOT (not the process
    CWD): env\\bootstrap.py chdirs into the target script's directory, so a
    relative path from the command line would otherwise land under tools\\.
    """
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = NEWROOT / p
        return _output_root(p)
    archive = NEWROOT / "output_archive"
    cands = sorted([p for p in archive.glob("baseline_legacy_*") if p.is_dir()]) if archive.exists() else []
    if not cands:
        raise SystemExit(
            "No --baseline given and no output_archive/baseline_legacy_* found.\n"
            "Run WP4 (legacy-boundary full chain) and freeze it with tools/freeze_baseline.py first."
        )
    return _output_root(cands[-1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=None,
                    help="legacy-boundary baseline (WP4 archive); default = newest "
                         "output_archive/baseline_legacy_*")
    ap.add_argument("--out", default=str(NEWROOT / "docs" / "_边界差异对照.md"))
    ap.add_argument("--tol-dist", type=float, default=0.5,
                    help="district-level relative tolerance %% (band 1 upper bound)")
    ap.add_argument("--tol-city", type=float, default=0.05,
                    help="city-total relative tolerance %% (band 1 upper bound)")
    args = ap.parse_args()

    baseline = _resolve_baseline(args.baseline)

    lines: list[str] = []
    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    emit("# 边界替换回归报告（Step 2c / 2d 实测）")
    emit()
    emit(f"- 基线: `{baseline}`")
    emit(f"- 现输出: `{CLIMATE_OUT}`")
    emit()

    verdicts: list[str] = []

    # ── 1. SVI ──────────────────────────────────────────────────────────
    svi_b = _load(baseline / "intermediate", SVI_FILE)
    svi_n = _load(CLIMATE_OUT / "intermediate", SVI_FILE)
    emit("## 1. 区级社会脆弱性 SVI")
    emit()
    if svi_b is None or svi_n is None:
        emit(f"SKIP: missing {SVI_FILE}")
    else:
        m = svi_b.merge(svi_n, on="district", suffixes=("_base", "_new"))
        m["dSVI"] = m["SVI_new"] - m["SVI_base"]
        m["SVI_rel%"] = _rel_change(m["SVI_new"], m["SVI_base"])
        keep = ["district", "area_km2_base", "area_km2_new", "SVI_base", "SVI_new",
                "dSVI", "SVI_rel%"]
        emit(m[keep].round(4).to_string(index=False))
        emit()
        max_abs = float(m["dSVI"].abs().max())
        emit(f"- 最大 |ΔSVI| = **{max_abs:.4f}**")
        emit(f"- SVI 风险乘数效应上限 = 0.15 × {max_abs:.4f} = **{0.15 * max_abs * 100:.3f}%**")
        emit()

    # ── 2. 区级 EAL ─────────────────────────────────────────────────────
    eal_b = _load(baseline / "results", EAL_FILE)
    eal_n = _load(CLIMATE_OUT / "results", EAL_FILE)
    emit("## 2. 区级 EAL（historical / baseline_nodef）")
    emit()
    top5_b = top5_n = None
    if eal_b is None or eal_n is None:
        emit(f"SKIP: missing {EAL_FILE} — run `python run_v8.py --only C06` first.")
    else:
        sel = (eal_b["scenario"] == DIST_SCENARIO) & (eal_b["defense_profile"] == DIST_PROFILE)
        b = eal_b[sel][["district", "EAL_compound", "exposure_total", "EAL_ratio_pct"]].copy()
        sel2 = (eal_n["scenario"] == DIST_SCENARIO) & (eal_n["defense_profile"] == DIST_PROFILE)
        n = eal_n[sel2][["district", "EAL_compound", "exposure_total", "EAL_ratio_pct"]].copy()
        m = b.merge(n, on="district", suffixes=("_base", "_new"))
        m["EAL_rel%"] = _rel_change(m["EAL_compound_new"], m["EAL_compound_base"])
        m["EXP_rel%"] = _rel_change(m["exposure_total_new"], m["exposure_total_base"])
        m["RATIO_rel%"] = _rel_change(m["EAL_ratio_pct_new"], m["EAL_ratio_pct_base"])
        show = m[["district", "EAL_compound_base", "EAL_compound_new", "EAL_rel%",
                  "EXP_rel%", "RATIO_rel%"]].copy()
        emit(show.round(4).to_string(index=False))
        emit()

        top5_b = b.nlargest(5, "EAL_compound")["district"].tolist()
        top5_n = n.nlargest(5, "EAL_compound")["district"].tolist()
        emit(f"- Top5 基线: {' > '.join(top5_b)}")
        emit(f"- Top5 替换后: {' > '.join(top5_n)}")
        same = top5_b == top5_n
        emit(f"- **Top5 排序{'不变' if same else '改变'}**  ← 方案附加硬约束")
        if not same:
            verdicts.append("Top5 排序改变 → 必须上报（方案硬约束）")
        emit()

        max_dist = float(m["EAL_rel%"].abs().max())
        emit(f"- 区级 |ΔEAL| 最大 = **{max_dist:.4f}%**"
             f"（{m.loc[m['EAL_rel%'].abs().idxmax(), 'district']}）")

        # ── 3. 城市总量 ────────────────────────────────────────────────
        emit()
        emit("## 3. 城市总量（按 scenario × defense_profile 求和）")
        emit()
        cb = eal_b.groupby(CITY_KEY, as_index=False)[EAL_COLS].sum()
        cn = eal_n.groupby(CITY_KEY, as_index=False)[EAL_COLS].sum()
        cm = cb.merge(cn, on=CITY_KEY, suffixes=("_base", "_new"))
        for c in EAL_COLS:
            cm[f"{c}_rel%"] = _rel_change(cm[f"{c}_new"], cm[f"{c}_base"])
        emit(cm[["scenario", "defense_profile",
                 "EAL_compound_base", "EAL_compound_new", "EAL_compound_rel%",
                 "EAL_wind_rel%", "EAL_surge_rel%"]].round(4).to_string(index=False))
        emit()
        max_city = float(cm["EAL_compound_rel%"].abs().max())
        emit(f"- 城市 |ΔEAL_compound| 最大 = **{max_city:.4f}%**")
        emit()

        # ── 3b. 稿件相关派生指标 ───────────────────────────────────────
        emit()
        emit("## 3b. 稿件相关派生指标")
        emit()
        emit("| 指标 | 基线 | 替换后 | 变化 |")
        emit("|---|---|---|---|")
        # defence reduction % (baseline_nodef -> current_def_gap) per scenario
        for scen in sorted(cb["scenario"].unique()):
            b0 = cb[(cb["scenario"] == scen) & (cb["defense_profile"] == "baseline_nodef")]["EAL_compound"]
            b1 = cb[(cb["scenario"] == scen) & (cb["defense_profile"] == "current_def_gap")]["EAL_compound"]
            n0 = cn[(cn["scenario"] == scen) & (cn["defense_profile"] == "baseline_nodef")]["EAL_compound"]
            n1 = cn[(cn["scenario"] == scen) & (cn["defense_profile"] == "current_def_gap")]["EAL_compound"]
            if len(b0) and len(b1) and len(n0) and len(n1):
                rb = (1 - float(b1.iloc[0]) / float(b0.iloc[0])) * 100
                rn = (1 - float(n1.iloc[0]) / float(n0.iloc[0])) * 100
                emit(f"| {scen} 防御削减率 | {rb:.2f}% | {rn:.2f}% | {rn - rb:+.2f} pp |")
        # wind / surge shares
        for scen in sorted(cb["scenario"].unique()):
            for prof in ["baseline_nodef", "current_def_gap"]:
                sel_b = (cb["scenario"] == scen) & (cb["defense_profile"] == prof)
                sel_n = (cn["scenario"] == scen) & (cn["defense_profile"] == prof)
                if not sel_b.any() or not sel_n.any():
                    continue
                wb, sb_ = float(cb[sel_b]["EAL_wind"].iloc[0]), float(cb[sel_b]["EAL_surge"].iloc[0])
                wn, sn_ = float(cn[sel_n]["EAL_wind"].iloc[0]), float(cn[sel_n]["EAL_surge"].iloc[0])
                tw, ts = wb + sb_, wn + sn_
                if tw and ts:
                    emit(f"| {scen} / {prof} 风占比 | {wb / tw * 100:.2f}% | {wn / ts * 100:.2f}% | "
                         f"{wn / ts * 100 - wb / tw * 100:+.2f} pp |")
                    emit(f"| {scen} / {prof} 潮占比 | {sb_ / tw * 100:.2f}% | {sn_ / ts * 100:.2f}% | "
                         f"{sn_ / ts * 100 - sb_ / tw * 100:+.2f} pp |")
        emit()

        # ── 4. 阈值裁定 ────────────────────────────────────────────────
        def band(dist_pct: float, city_pct: float) -> str:
            """Plan §4 thresholds: band 1 iff BOTH within tolerance."""
            hi_dist, hi_city = dist_pct > 5.0, city_pct > 1.0
            if hi_dist or hi_city:
                return "第三档"
            if dist_pct <= args.tol_dist and city_pct <= args.tol_city:
                return "第一档"
            return "第二档"

        bd = band(max_dist, max_city)
        emit("## 4. 阈值裁定")
        emit()
        emit("| 判据 | 实测 | 第一档上限 | 该判据落档 |")
        emit("|---|---|---|---|")
        emit(f"| 区级最大\\|ΔEAL\\| | {max_dist:.4f}% | {args.tol_dist}% | "
             f"{'第一档' if max_dist <= args.tol_dist else ('第二档' if max_dist <= 5 else '第三档')} |")
        emit(f"| 城市最大\\|ΔEAL\\| | {max_city:.4f}% | {args.tol_city}% | "
             f"{'第一档' if max_city <= args.tol_city else ('第二档' if max_city <= 1 else '第三档')} |")
        emit()
        if bd == "第一档":
            emit("**裁定：第一档 —— 采用官方层，稿件数字不动。**")
        elif bd == "第二档":
            emit("**裁定：第二档 —— 采用官方层，需逐项更新受影响数字。**")
        else:
            emit("**裁定：第三档 —— 停止，需人工决定。**")
        emit()
        emit("### 附加硬约束（独立于档位）")
        emit()
        emit(f"- 区级 EAL Top5 排序：{'**未改变**' if same else '**已改变 → 必须上报**'}")
        if not same:
            emit(f"  - 基线: {' > '.join(top5_b)}")
            emit(f"  - 替换后: {' > '.join(top5_n)}")
            moved = [d for d, e in zip(top5_n, top5_b) if d != e]
            emit(f"  - 位次变动: {', '.join(moved)}")

    emit()
    emit("---")
    emit()
    emit("*由 `tools/compare_boundary_impact.py` 生成。判定逻辑与 `tools/audit_manuscript_consistency.py` 一致。*")

    out = Path(args.out)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWROTE {out}")
    for v in verdicts:
        print(f"!! {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
