"""Gate G4 (= acceptance criterion A1): reproduce the frozen reference values.

Recomputes every quantity in plan section 2.6 from the current pipeline outputs
and compares it with the frozen value at the precision the manuscript reports.

Methodology mirrors `tools/audit_manuscript_consistency.py:current_main_outputs()`
exactly:
  * city totals      : defense.groupby(["scenario","defense_profile"])[EAL_*].sum()
  * district ranking : defense[(scenario=="historical") &
                                (defense_profile=="baseline_nodef")].nlargest(5,"EAL_compound")
  * EAL / exposure   : EAL_ratio_pct * 10  (per mille)

Usage:
    env\\run.ps1 tools\\_gate_g4.py [--label OLD|NEW]
Writes docs\\_基线复现校验报告.md and exits non-zero on any mismatch.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

NEWROOT = Path(__file__).resolve().parent.parent
CLIMATE_RESULTS = NEWROOT / "Climate" / "output" / "results"
FINANCE_RESULTS = NEWROOT / "Finance" / "output" / "results"
COMPOSITE_RESULTS = NEWROOT / "Composite" / "output" / "results"
REPORT = NEWROOT / "docs" / "_基线复现校验报告.md"

SCEN = {"hist": "historical", "ssp245": "SSP2-4.5", "ssp585": "SSP5-8.5"}
# The index CSVs (CRI/HSI/CCHI) use the long scenario label, the EAL panel the short one.
IDX = {"hist": "Historical Baseline", "ssp245": "SSP2-4.5", "ssp585": "SSP5-8.5"}
SCEN_LABEL = [("hist", "Historical Baseline"), ("ssp245", "SSP2-4.5"), ("ssp585", "SSP5-8.5")]

# ── plan section 2.6 frozen reference values ────────────────────────────────
FROZEN = {
    "city_eal_bn": {            # (scenario, profile) -> bn CNY
        ("hist", "nodef"): 24.153, ("hist", "def"): 18.970,
        ("ssp245", "nodef"): 33.326, ("ssp245", "def"): 23.848,
        ("ssp585", "nodef"): 40.225, ("ssp585", "def"): 26.469,
    },
    "defense_reduction_pct": {"hist": 21.46, "ssp245": 28.44, "ssp585": 34.20},
    "wind_share_pct": 74.14,
    "surge_share_pct": 25.86,
    "exposure_total_t": 63.3272,
    "top5_eal_bn": [("浦东新区", 5.9286), ("杨浦区", 2.6410), ("徐汇区", 2.2898),
                    ("闵行区", 2.2530), ("虹口区", 1.6692)],
    "district_ratio_permille": [("浦东新区", 0.3995), ("杨浦区", 0.7690), ("徐汇区", 0.5573),
                                ("闵行区", 0.2815), ("虹口区", 0.8266), ("黄浦区", 0.6762)],
    "cri_2023_12": 438.8918,
    "cri_2050": [("hist", 599.032, 489.59, 689.49),
                 ("ssp245", 673.318, 563.55, 767.91),
                 ("ssp585", 742.326, 641.30, 836.98)],
    "hsi_terminal": 231.33, "hsi_peak": 254.18,
    "hsi_terminal_month": "2025-06", "hsi_peak_month": "2023-02",
    "hsi_2050": [("hist", 265.330, 229.95, 329.37),
                 ("ssp245", 287.071, 250.98, 354.10),
                 ("ssp585", 307.189, 269.69, 375.01)],
    "cchi_2011_12": 129.775, "cchi_2023_12": 312.949,
    "cchi_2050": [("hist", 398.793, 351.23, 456.21),
                  ("ssp245", 439.019, 394.50, 497.55),
                  ("ssp585", 476.949, 434.86, 533.15)],
    "n_buildings": 585033,
    "n_districts": 16,
}

ROWS = []


def check(name, got, want, digits, unit=""):
    ok = round(float(got), digits) == round(float(want), digits)
    ROWS.append({"item": name, "got": got, "want": want, "digits": digits,
                 "unit": unit, "ok": ok})
    return ok


def check_str(name, got, want):
    ok = str(got) == str(want)
    ROWS.append({"item": name, "got": got, "want": want, "digits": None,
                 "unit": "", "ok": ok})
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="NEW", help="OLD = pre-rerun copy, NEW = post-rerun")
    args = ap.parse_args()

    print("=" * 78)
    print(f"GATE G4 (= A1) · frozen-reference comparison   [label={args.label}]")
    print("=" * 78)

    defense = pd.read_csv(CLIMATE_RESULTS / "defense_sensitivity" / "defense_profile_eal.csv")
    city = defense.groupby(["scenario", "defense_profile"], as_index=False)[
        ["EAL_compound", "EAL_wind", "EAL_surge"]].sum()

    def city_eal(scen, prof):
        r = city[(city["scenario"] == SCEN[scen]) & (city["defense_profile"] == prof)].iloc[0]
        return r["EAL_compound"] / 1e9, r["EAL_wind"] / 1e9, r["EAL_surge"] / 1e9

    print("\n-- city EAL (bn CNY) --")
    for (scen, prof), want in FROZEN["city_eal_bn"].items():
        p = "baseline_nodef" if prof == "nodef" else "current_def_gap"
        got, _, _ = city_eal(scen, p)
        check(f"city EAL {scen}/{prof}", got, want, 3, "bn")
        print(f"  {scen:7s} {prof:6s} got={got:10.4f}  want={want:10.3f}")

    print("\n-- defense reduction (%) --")
    for scen, want in FROZEN["defense_reduction_pct"].items():
        n, _, _ = city_eal(scen, "baseline_nodef")
        d, _, _ = city_eal(scen, "current_def_gap")
        got = (1 - d / n) * 100
        check(f"defense reduction {scen}", got, want, 2, "%")
        print(f"  {scen:7s} got={got:7.2f}%  want={want:7.2f}%")

    print("\n-- wind / surge share, historical & baseline_nodef (%) --")
    _, w, s = city_eal("hist", "baseline_nodef")
    check("wind share hist/nodef", w / (w + s) * 100, FROZEN["wind_share_pct"], 2, "%")
    check("surge share hist/nodef", s / (w + s) * 100, FROZEN["surge_share_pct"], 2, "%")
    print(f"  wind={w / (w + s) * 100:6.2f}%  surge={s / (w + s) * 100:6.2f}%")

    print("\n-- total exposure --")
    hist = defense[(defense["scenario"] == "historical") &
                   (defense["defense_profile"] == "baseline_nodef")]
    expo_t = hist["exposure_total"].sum() / 1e12
    check("exposure total", expo_t, FROZEN["exposure_total_t"], 4, "T")
    print(f"  got={expo_t:.4f} T   want={FROZEN['exposure_total_t']} T   districts={len(hist)}")
    check("district count", len(hist), FROZEN["n_districts"], 0)

    print("\n-- district Top5 EAL (bn) --")
    got_top5 = hist.nlargest(5, "EAL_compound")[["district", "EAL_compound", "EAL_ratio_pct"]]
    got_names = got_top5["district"].tolist()
    want_names = [d for d, _ in FROZEN["top5_eal_bn"]]
    check_str("Top5 order", " > ".join(got_names), " > ".join(want_names))
    print(f"  got : {' > '.join(got_names)}")
    print(f"  want: {' > '.join(want_names)}")
    for (d, want), (_, row) in zip(FROZEN["top5_eal_bn"], got_top5.iterrows()):
        check(f"Top5 EAL {d}", row["EAL_compound"] / 1e9, want, 4, "bn")
        print(f"    {d}: {row['EAL_compound'] / 1e9:.4f}  (want {want})")

    print("\n-- district EAL / exposure (per mille) --")
    for d, want in FROZEN["district_ratio_permille"]:
        r = hist[hist["district"] == d]
        got = float(r["EAL_ratio_pct"].iloc[0]) * 10 if len(r) else float("nan")
        check(f"ratio {d}", got, want, 4, "per-mille")
        print(f"    {d}: {got:.4f}  (want {want})")

    print("\n-- CRI --")
    cfci_hist = pd.read_csv(COMPOSITE_RESULTS / "shanghai_cfci_historical.csv")
    cri_2312 = cfci_hist[cfci_hist["date"] == "2023-12-01"]["cri_index"].iloc[0]
    check("CRI 2023-12", cri_2312, FROZEN["cri_2023_12"], 4)
    print(f"  CRI 2023-12 got={cri_2312:.4f}  want={FROZEN['cri_2023_12']}")
    cri = pd.read_csv(CLIMATE_RESULTS / "shanghai_city_cri_projection.csv")
    for scen, want50, want10, want90 in FROZEN["cri_2050"]:
        r = cri[(cri["scenario"] == IDX[scen]) & (cri["date"] == "2050-12-01")].iloc[0]
        check(f"CRI2050 p50 {scen}", r["cri_index_p50"], want50, 3)
        check(f"CRI2050 p10 {scen}", r["cri_index_p10"], want10, 2)
        check(f"CRI2050 p90 {scen}", r["cri_index_p90"], want90, 2)
        print(f"  {scen:7s} p50={r['cri_index_p50']:.3f} [{r['cri_index_p10']:.2f}, "
              f"{r['cri_index_p90']:.2f}]  want {want50} [{want10}, {want90}]")

    print("\n-- HSI --")
    fri_hist = pd.read_csv(FINANCE_RESULTS / "shanghai_finance_risk_index.csv")
    last = fri_hist.iloc[-1]
    peak = fri_hist.loc[fri_hist["fri_index"].idxmax()]
    check("HSI terminal", last["fri_index"], FROZEN["hsi_terminal"], 2)
    check_str("HSI terminal month", str(last["date"])[:7], FROZEN["hsi_terminal_month"])
    check("HSI peak", peak["fri_index"], FROZEN["hsi_peak"], 2)
    check_str("HSI peak month", str(peak["date"])[:7], FROZEN["hsi_peak_month"])
    print(f"  terminal {last['fri_index']:.2f} @ {str(last['date'])[:7]}   "
          f"peak {peak['fri_index']:.2f} @ {str(peak['date'])[:7]}")
    frip = pd.read_csv(FINANCE_RESULTS / "shanghai_fri_projection.csv")
    for scen, want50, want10, want90 in FROZEN["hsi_2050"]:
        r = frip[(frip["scenario"] == IDX[scen]) & (frip["date"] == "2050-12-01")].iloc[0]
        check(f"HSI2050 p50 {scen}", r["fri_index_p50"], want50, 3)
        check(f"HSI2050 p10 {scen}", r["fri_index_p10"], want10, 2)
        check(f"HSI2050 p90 {scen}", r["fri_index_p90"], want90, 2)
        print(f"  {scen:7s} p50={r['fri_index_p50']:.3f} [{r['fri_index_p10']:.2f}, "
              f"{r['fri_index_p90']:.2f}]  want {want50} [{want10}, {want90}]")

    print("\n-- CCHI --")
    h0 = cfci_hist.iloc[0]
    hN = cfci_hist.iloc[-1]
    check("CCHI 2011-12", h0["cfci"], FROZEN["cchi_2011_12"], 3)
    check("CCHI 2023-12", hN["cfci"], FROZEN["cchi_2023_12"], 3)
    print(f"  {str(h0['date'])[:7]}={h0['cfci']:.3f}   {str(hN['date'])[:7]}={hN['cfci']:.3f}")
    cfp = pd.read_csv(COMPOSITE_RESULTS / "shanghai_cfci_projection.csv")
    for scen, want50, want10, want90 in FROZEN["cchi_2050"]:
        r = cfp[(cfp["scenario"] == IDX[scen]) & (cfp["date"] == "2050-12-01")].iloc[0]
        check(f"CCHI2050 p50 {scen}", r["cfci_p50"], want50, 3)
        check(f"CCHI2050 p10 {scen}", r["cfci_p10"], want10, 2)
        check(f"CCHI2050 p90 {scen}", r["cfci_p90"], want90, 2)
        print(f"  {scen:7s} p50={r['cfci_p50']:.3f} [{r['cfci_p10']:.2f}, "
              f"{r['cfci_p90']:.2f}]  want {want50} [{want10}, {want90}]")

    print("\n-- building count --")
    pq = NEWROOT / "Climate" / "output" / "intermediate" / "building_skeleton.parquet"
    if pq.exists():
        n = len(pd.read_parquet(pq, columns=["geometry"])) if False else len(pd.read_parquet(pq))
        check("building count", n, FROZEN["n_buildings"], 0)
        print(f"  {n:,}  (want {FROZEN['n_buildings']:,})")
    else:
        ROWS.append({"item": "building count", "got": "missing", "want": FROZEN["n_buildings"],
                     "digits": None, "unit": "", "ok": False})
        print(f"  MISSING {pq}")

    failed = [r for r in ROWS if not r["ok"]]
    total = len(ROWS)
    print("\n" + "=" * 78)
    print(f"G4 [{args.label}] = {'PASS' if not failed else 'FAIL'}   "
          f"({total - len(failed)}/{total} items match)")
    if failed:
        print("  mismatches:")
        for r in failed:
            print(f"    - {r['item']}: got {r['got']}  want {r['want']}")
    print("=" * 78)

    lines = [f"# 基线复现校验报告（G4 = A1）· label={args.label}", "",
             f"- 判据来源：`_执行方案_官方边界重跑与稿件更新_v1.md` §2.6 冻结参考值",
             f"- 比较口径：`tools/audit_manuscript_consistency.py:current_main_outputs()`",
             f"- 精度：稿件报告精度（四舍五入后逐位相同）", "",
             f"**结论：{'PASS' if not failed else 'FAIL'}**（{total - len(failed)}/{total} 项一致）", "",
             "| 项 | 实测 | 期望 | 小数位 | 单位 | 结果 |", "|---|---:|---:|---:|---|---|"]
    for r in ROWS:
        g = f"{r['got']:.{r['digits']}f}" if isinstance(r["digits"], int) and isinstance(r["got"], (int, float)) else str(r["got"])
        w = f"{r['want']:.{r['digits']}f}" if isinstance(r["digits"], int) and isinstance(r["want"], (int, float)) else str(r["want"])
        lines.append(f"| {r['item']} | {g} | {w} | {r['digits']} | {r['unit']} | "
                     f"{'✅' if r['ok'] else '❌'} |")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告已写入 {REPORT}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
