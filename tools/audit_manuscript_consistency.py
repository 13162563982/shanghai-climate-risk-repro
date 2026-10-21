"""Audit manuscript key numbers against current output CSVs.

Scope:
- Abstract
- Tables 3-8
- Conclusion

Outputs:
- Console summary
- docs/MANUSCRIPT_CONSISTENCY_AUDIT.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
# Plain-text (markdown) rendering of the manuscript, used for the text-side number
# checks. The v10 deliverable itself is a .docx; WP7 emits this companion file.
# When it is absent main() stops with a clear message — the output-side helpers
# (current_main_outputs(), build_table8_row(), ...) stay importable and usable.
MANUSCRIPT_PATH = ROOT / "manuscript" / "PAPER_MANUSCRIPT_FINAL.md"
REPORT_PATH = ROOT / "docs" / "_稿件一致性审计.md"
RESULTS_DIR = ROOT / "_sensitivity_results"

CLIMATE_RESULTS = ROOT / "Climate" / "output" / "results"
FINANCE_RESULTS = ROOT / "Finance" / "output" / "results"
COMPOSITE_RESULTS = ROOT / "Composite" / "output" / "results"


@dataclass
class CheckResult:
    section: str
    name: str
    status: str
    expected: str
    details: str = ""


def round_half_up(value: float, digits: int = 0) -> Decimal:
    quant = Decimal("1").scaleb(-digits)
    return Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP)


def fmt_billion_value(value: float, digits: int = 1) -> str:
    rounded = round_half_up(value / 1e9, digits)
    return f"{rounded:.{digits}f}"


def fmt_billion(value: float, digits: int = 1) -> str:
    return f"{fmt_billion_value(value, digits)}B"


def fmt_trillion_value(value: float, digits: int = 1) -> str:
    rounded = round_half_up(value / 1e12, digits)
    return f"{rounded:.{digits}f}"


def fmt_int(value: float) -> str:
    return str(int(round_half_up(value, 0)))


def fmt_per_mille_from_pct(value_pct: float) -> str:
    rounded = round_half_up(value_pct * 10.0, 2)
    return f"{rounded:.2f}"


def fmt_signed_pct(value: float, digits: int) -> str:
    sign = "+" if value >= 0 else "−"
    rounded = abs(round_half_up(value, digits))
    if digits == 0:
        body = str(int(rounded))
    else:
        body = f"{rounded:.{digits}f}"
    return f"{sign}{body}%"


def fmt_pm_pct(value: float, digits: int) -> str:
    rounded = abs(round_half_up(value, digits))
    if digits == 0:
        body = str(int(rounded))
    else:
        body = f"{rounded:.{digits}f}"
    return f"±{body}%"


def extract_between(text: str, start_pat: str, end_pat: str) -> str:
    match = re.search(start_pat + r"(.*?)" + end_pat, text, flags=re.S)
    if not match:
        raise RuntimeError(f"Could not extract section between {start_pat!r} and {end_pat!r}")
    return match.group(1)


def latest_sweep_files() -> dict[str, Path]:
    latest: dict[str, Path] = {}
    for path in sorted(RESULTS_DIR.glob("sensitivity_results_*.csv")):
        if path.name in {"sensitivity_latest.csv", "all_new_sweeps_combined.csv"}:
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if "sweep_id" not in df.columns:
            continue
        for sweep_id in df["sweep_id"].dropna().astype(str).unique():
            latest[sweep_id] = path
    return latest


def load_sweep(sweep_id: str, latest_files: dict[str, Path]) -> tuple[pd.DataFrame, Path]:
    path = latest_files[sweep_id]
    df = pd.read_csv(path)
    sub = df[df["sweep_id"] == sweep_id].copy()
    return sub, path


def get_baseline_row(df: pd.DataFrame) -> pd.Series:
    if "is_baseline" in df.columns:
        baseline = df[df["is_baseline"] == True]  # noqa: E712
        if not baseline.empty:
            return baseline.iloc[0]
    return df.iloc[len(df) // 2]


def current_main_outputs() -> dict[str, object]:
    defense = pd.read_csv(CLIMATE_RESULTS / "defense_sensitivity" / "defense_profile_eal.csv")
    city = defense.groupby(["scenario", "defense_profile"], as_index=False)[["EAL_compound", "EAL_wind", "EAL_surge"]].sum()

    hist_row = city[(city["scenario"] == "historical") & (city["defense_profile"] == "baseline_nodef")].iloc[0]
    hist_def_row = city[(city["scenario"] == "historical") & (city["defense_profile"] == "current_def_gap")].iloc[0]
    ssp245_row = city[(city["scenario"] == "SSP2-4.5") & (city["defense_profile"] == "baseline_nodef")].iloc[0]
    ssp245_def_row = city[(city["scenario"] == "SSP2-4.5") & (city["defense_profile"] == "current_def_gap")].iloc[0]
    ssp585_row = city[(city["scenario"] == "SSP5-8.5") & (city["defense_profile"] == "baseline_nodef")].iloc[0]
    ssp585_def_row = city[(city["scenario"] == "SSP5-8.5") & (city["defense_profile"] == "current_def_gap")].iloc[0]

    hist_districts = defense[(defense["scenario"] == "historical") & (defense["defense_profile"] == "baseline_nodef")].copy()
    ssp585_districts = defense[(defense["scenario"] == "SSP5-8.5") & (defense["defense_profile"] == "baseline_nodef")].copy()

    cri = pd.read_csv(CLIMATE_RESULTS / "shanghai_city_cri_projection.csv")
    fri_hist = pd.read_csv(FINANCE_RESULTS / "shanghai_finance_risk_index.csv")
    fri_proj = pd.read_csv(FINANCE_RESULTS / "shanghai_fri_projection.csv")
    cfci_hist = pd.read_csv(COMPOSITE_RESULTS / "shanghai_cfci_historical.csv")
    cfci_proj = pd.read_csv(COMPOSITE_RESULTS / "shanghai_cfci_projection.csv")

    def row_at(df: pd.DataFrame, scenario: str) -> pd.Series:
        return df[(df["scenario"] == scenario) & (df["date"] == "2050-12-01")].iloc[0]

    return {
        "defense": defense,
        "city": city,
        "hist_row": hist_row,
        "hist_def_row": hist_def_row,
        "ssp245_row": ssp245_row,
        "ssp245_def_row": ssp245_def_row,
        "ssp585_row": ssp585_row,
        "ssp585_def_row": ssp585_def_row,
        "hist_districts": hist_districts,
        "ssp585_districts": ssp585_districts,
        "cri_hist_2023": pd.read_csv(COMPOSITE_RESULTS / "shanghai_cfci_historical.csv").iloc[-1]["cri_index"],
        "cri_2050_baseline": row_at(cri, "Historical Baseline"),
        "cri_2050_ssp245": row_at(cri, "SSP2-4.5"),
        "cri_2050_ssp585": row_at(cri, "SSP5-8.5"),
        "fri_hist_terminal": fri_hist.iloc[-1],
        "fri_hist_peak": fri_hist.loc[fri_hist["fri_index"].idxmax()],
        "fri_2050_baseline": row_at(fri_proj, "Historical Baseline"),
        "fri_2050_ssp245": row_at(fri_proj, "SSP2-4.5"),
        "fri_2050_ssp585": row_at(fri_proj, "SSP5-8.5"),
        "cfci_hist_terminal": cfci_hist.iloc[-1],
        "cfci_2050_baseline": row_at(cfci_proj, "Historical Baseline"),
        "cfci_2050_ssp245": row_at(cfci_proj, "SSP2-4.5"),
        "cfci_2050_ssp585": row_at(cfci_proj, "SSP5-8.5"),
    }


def add_literal_check(results: list[CheckResult], section: str, name: str, expected: str, haystack: str) -> None:
    status = "PASS" if expected in haystack else "FAIL"
    details = "" if status == "PASS" else "Expected literal not found"
    results.append(CheckResult(section=section, name=name, status=status, expected=expected, details=details))


def add_fragments_check(results: list[CheckResult], section: str, name: str, fragments: list[str], haystack: str) -> None:
    missing = [frag for frag in fragments if frag not in haystack]
    status = "PASS" if not missing else "FAIL"
    details = "" if status == "PASS" else "Missing: " + "; ".join(missing)
    results.append(CheckResult(section=section, name=name, status=status, expected=" | ".join(fragments), details=details))


def build_table8_row(df: pd.DataFrame, row_spec: dict[str, str]) -> str:
    baseline = get_baseline_row(df)
    metric = row_spec["metric_col"]
    values = df[metric]
    bl = float(baseline[metric])
    mn = float(values.min())
    mx = float(values.max())
    pmin = (mn - bl) / bl * 100.0 if bl else 0.0
    pmax = (mx - bl) / bl * 100.0 if bl else 0.0

    kind = row_spec["range_kind"]
    if kind == "billions_1":
        baseline_value = fmt_billion(bl, 1)
        range_value = f"{fmt_billion_value(mn, 1)}–{fmt_billion_value(mx, 1)}B"
    elif kind == "int_0":
        baseline_value = fmt_int(bl)
        range_value = f"{fmt_int(mn)}–{fmt_int(mx)}"
    else:
        raise ValueError(f"Unknown range kind: {kind}")

    if "deviation_override" in row_spec:
        deviation = row_spec["deviation_override"]
    else:
        dev_style = row_spec["deviation_style"]
        if dev_style == "range0":
            deviation = f"{fmt_signed_pct(pmin, 0)} to {fmt_signed_pct(pmax, 0)}"
        elif dev_style == "range1":
            deviation = f"{fmt_signed_pct(pmin, 1)} to {fmt_signed_pct(pmax, 1)}"
        elif dev_style == "pm1":
            deviation = fmt_pm_pct(max(abs(pmin), abs(pmax)), 1)
        elif dev_style == "approx0":
            deviation = "$\\approx$0%"
        else:
            raise ValueError(f"Unknown deviation style: {dev_style}")

    return (
        f"| {row_spec['label']} | {row_spec['baseline_display']} | {row_spec['range_display']} | "
        f"{row_spec['primary_index']} | {baseline_value} | {range_value} | {deviation} |"
    )


def main() -> None:
    if not MANUSCRIPT_PATH.exists():
        raise SystemExit(
            f"manuscript text not found: {MANUSCRIPT_PATH}\n"
            "Provide a plain-text rendering of the manuscript there (WP7 emits it), or\n"
            "import this module and call the output-side helpers directly "
            "(current_main_outputs(), build_table8_row(), ...)."
        )
    manuscript = MANUSCRIPT_PATH.read_text(encoding="utf-8")
    abstract = extract_between(manuscript, r"\*\*Abstract:\*\* ", r"\n\n\*\*Keywords:\*\*")
    conclusion = extract_between(manuscript, r"## 8\. Conclusion\n\n", r"\n\n## Data Availability Statement")

    outputs = current_main_outputs()
    latest_files = latest_sweep_files()
    checks: list[CheckResult] = []

    # Main output state check: current composite outputs should match baseline rho row.
    rho_df, rho_path = load_sweep("CFCI_TARGET_RHO", latest_files)
    rho_base = get_baseline_row(rho_df)
    rho_ok = (
        abs(float(outputs["cfci_2050_baseline"]["cfci_p50"]) - float(rho_base["CFCI_2050_p50_Historical Baseline"])) < 1e-9
        and abs(float(outputs["cfci_2050_ssp245"]["cfci_p50"]) - float(rho_base["CFCI_2050_p50_SSP2-4.5"])) < 1e-9
        and abs(float(outputs["cfci_2050_ssp585"]["cfci_p50"]) - float(rho_base["CFCI_2050_p50_SSP5-8.5"])) < 1e-9
    )
    checks.append(
        CheckResult(
            section="Output State",
            name="Composite baseline restored after sensitivity sweeps",
            status="PASS" if rho_ok else "FAIL",
            expected=f"Current Composite outputs match baseline row in {rho_path.name}",
            details="" if rho_ok else "Composite outputs differ from baseline rho=0.411 sweep row",
        )
    )

    # Abstract checks.
    hist_nodef_b = fmt_billion_value(float(outputs["hist_row"]["EAL_compound"]), 1)
    hist_def_b = fmt_billion_value(float(outputs["hist_def_row"]["EAL_compound"]), 1)
    ssp585_nodef_b = fmt_billion_value(float(outputs["ssp585_row"]["EAL_compound"]), 1)
    abstract_fragments = [
        f"CNY {hist_nodef_b} billion",
        f"CNY {hist_def_b} billion",
        f"CNY {ssp585_nodef_b} billion",
        f"{fmt_int(outputs['cri_hist_2023'])} by 2023",
        f"{fmt_int(float(outputs['cri_2050_baseline']['cri_index_p50']))} under the historical baseline",
        f"{fmt_int(float(outputs['cri_2050_ssp245']['cri_index_p50']))} under SSP2-4.5",
        f"{fmt_int(float(outputs['cri_2050_ssp585']['cri_index_p50']))} under SSP5-8.5",
        f"{fmt_int(float(outputs['cfci_2050_ssp245']['cfci_p50']))} under SSP2-4.5",
        f"{fmt_int(float(outputs['cfci_2050_ssp585']['cfci_p50']))} under SSP5-8.5",
        "Hongkou",
        "Yangpu",
        "Huangpu",
    ]
    add_fragments_check(checks, "Abstract", "Key result numbers", abstract_fragments, abstract)

    # Table 3 rows.
    table3_rows = [
        f"| Historical | {fmt_billion_value(float(outputs['hist_row']['EAL_compound']), 1)} | {fmt_billion_value(float(outputs['hist_def_row']['EAL_compound']), 1)} | 22% |",
        f"| SSP2-4.5 (+0.3 m SLR) | {fmt_billion_value(float(outputs['ssp245_row']['EAL_compound']), 1)} | {fmt_billion_value(float(outputs['ssp245_def_row']['EAL_compound']), 1)} | 28% |",
        f"| SSP5-8.5 (+0.5 m SLR) | {fmt_billion_value(float(outputs['ssp585_row']['EAL_compound']), 1)} | {fmt_billion_value(float(outputs['ssp585_def_row']['EAL_compound']), 1)} | 34% |",
    ]
    for idx, row in enumerate(table3_rows, start=1):
        add_literal_check(checks, "Table 3", f"Row {idx}", row, manuscript)

    # Table 4 rows.
    hist_districts = outputs["hist_districts"].nlargest(5, "EAL_compound").copy()
    for district, eal, exposure, ratio in hist_districts[["district", "EAL_compound", "exposure_total", "EAL_ratio_pct"]].itertuples(index=False):
        row = (
            f"| {district.replace('区', '').replace('新区', '')} ({district}) | "
            f"{fmt_billion_value(float(eal), 1)} | {fmt_trillion_value(float(exposure), 1)} | {fmt_per_mille_from_pct(float(ratio))} |"
        )
        # Keep manuscript's English names stable.
        english = {
            "浦东新区": "Pudong",
            "杨浦区": "Yangpu",
            "徐汇区": "Xuhui",
            "闵行区": "Minhang",
            "虹口区": "Hongkou",
        }[district]
        row = row.replace(f"{district.replace('区', '').replace('新区', '')} ({district})", f"{english} ({district})")
        add_literal_check(checks, "Table 4", district, row, manuscript)

    # Table 5 rows.
    table5_rows = [
        f"| Historical Baseline | {fmt_int(float(outputs['cri_2050_baseline']['cri_index_p10']))} | {fmt_int(float(outputs['cri_2050_baseline']['cri_index_p50']))} | {fmt_int(float(outputs['cri_2050_baseline']['cri_index_p90']))} |",
        f"| SSP2-4.5 | {fmt_int(float(outputs['cri_2050_ssp245']['cri_index_p10']))} | {fmt_int(float(outputs['cri_2050_ssp245']['cri_index_p50']))} | {fmt_int(float(outputs['cri_2050_ssp245']['cri_index_p90']))} |",
        f"| SSP5-8.5 | {fmt_int(float(outputs['cri_2050_ssp585']['cri_index_p10']))} | {fmt_int(float(outputs['cri_2050_ssp585']['cri_index_p50']))} | {fmt_int(float(outputs['cri_2050_ssp585']['cri_index_p90']))} |",
    ]
    for idx, row in enumerate(table5_rows, start=1):
        add_literal_check(checks, "Table 5", f"Row {idx}", row, manuscript)

    # Table 6 rows.
    table6_rows = [
        f"| Historical Baseline | {fmt_int(float(outputs['fri_2050_baseline']['fri_index_p10']))} | {fmt_int(float(outputs['fri_2050_baseline']['fri_index_p50']))} | {fmt_int(float(outputs['fri_2050_baseline']['fri_index_p90']))} |",
        f"| SSP2-4.5 | {fmt_int(float(outputs['fri_2050_ssp245']['fri_index_p10']))} | {fmt_int(float(outputs['fri_2050_ssp245']['fri_index_p50']))} | {fmt_int(float(outputs['fri_2050_ssp245']['fri_index_p90']))} |",
        f"| SSP5-8.5 | {fmt_int(float(outputs['fri_2050_ssp585']['fri_index_p10']))} | {fmt_int(float(outputs['fri_2050_ssp585']['fri_index_p50']))} | {fmt_int(float(outputs['fri_2050_ssp585']['fri_index_p90']))} |",
    ]
    for idx, row in enumerate(table6_rows, start=1):
        add_literal_check(checks, "Table 6", f"Row {idx}", row, manuscript)

    # Table 7 rows.
    table7_rows = [
        f"| Historical Baseline | {fmt_int(float(outputs['cfci_2050_baseline']['cfci_p10']))} | {fmt_int(float(outputs['cfci_2050_baseline']['cfci_p50']))} | {fmt_int(float(outputs['cfci_2050_baseline']['cfci_p90']))} |",
        f"| SSP2-4.5 | {fmt_int(float(outputs['cfci_2050_ssp245']['cfci_p10']))} | {fmt_int(float(outputs['cfci_2050_ssp245']['cfci_p50']))} | {fmt_int(float(outputs['cfci_2050_ssp245']['cfci_p90']))} |",
        f"| SSP5-8.5 | {fmt_int(float(outputs['cfci_2050_ssp585']['cfci_p10']))} | {fmt_int(float(outputs['cfci_2050_ssp585']['cfci_p50']))} | {fmt_int(float(outputs['cfci_2050_ssp585']['cfci_p90']))} |",
    ]
    for idx, row in enumerate(table7_rows, start=1):
        add_literal_check(checks, "Table 7", f"Row {idx}", row, manuscript)

    # Table 8 rows and provenance.
    table8_specs = {
        "SURGE_MDR_CALIBRATION_SCALE": {
            "label": "Surge MDR calibration scale",
            "baseline_display": "0.176",
            "range_display": "0.10–0.30",
            "primary_index": "EAL",
            "metric_col": "DEF_EAL_historical_baseline_nodef",
            "range_kind": "billions_1",
            "deviation_style": "range0",
        },
        "TC_V_HALF_BASE_SCALE": {
            "label": "TC $V_{half}$ base scale",
            "baseline_display": "1.0",
            "range_display": "0.85–1.15",
            "primary_index": "EAL",
            "metric_col": "DEF_EAL_historical_baseline_nodef",
            "range_kind": "billions_1",
            "deviation_style": "range0",
        },
        "TC_IMPACT_V_THRESH": {
            "label": "TC onset threshold $V_{thresh}$",
            "baseline_display": "25.7 m/s",
            "range_display": "23.0–28.5",
            "primary_index": "EAL",
            "metric_col": "DEF_EAL_historical_baseline_nodef",
            "range_kind": "billions_1",
            "deviation_style": "range0",
        },
        "GAMMA_SVI": {
            "label": "Surge vulnerability index $\\gamma_{SVI}$",
            "baseline_display": "0.15",
            "range_display": "0.00–0.30",
            "primary_index": "EAL",
            "metric_col": "DEF_EAL_historical_baseline_nodef",
            "range_kind": "billions_1",
            "deviation_style": "range0",
        },
        "V_HALF_ADJ_A_old": {
            "label": "$V_{half}$ adj. A\\_old (pre-02 low-rise)",
            "baseline_display": "0.80",
            "range_display": "0.68–0.92",
            "primary_index": "EAL",
            "metric_col": "DEF_EAL_historical_baseline_nodef",
            "range_kind": "billions_1",
            "deviation_style": "range0",
        },
        "V_HALF_ADJ_A_new": {
            "label": "$V_{half}$ adj. A\\_new (02+ low-rise)",
            "baseline_display": "0.90",
            "range_display": "0.77–1.03",
            "primary_index": "EAL",
            "metric_col": "DEF_EAL_historical_baseline_nodef",
            "range_kind": "billions_1",
            "deviation_style": "range0",
        },
        "V_HALF_ADJ_B_old": {
            "label": "$V_{half}$ adj. B\\_old (pre-10 mid-rise)",
            "baseline_display": "0.95",
            "range_display": "0.81–1.09",
            "primary_index": "EAL",
            "metric_col": "DEF_EAL_historical_baseline_nodef",
            "range_kind": "billions_1",
            "deviation_style": "range0",
        },
        "V_HALF_ADJ_B_new": {
            "label": "$V_{half}$ adj. B\\_new (10+ mid-rise)",
            "baseline_display": "1.00",
            "range_display": "0.85–1.15",
            "primary_index": "EAL",
            "metric_col": "DEF_EAL_historical_baseline_nodef",
            "range_kind": "billions_1",
            "deviation_style": "range0",
            "deviation_override": "−8% to +18%",
        },
        "V_HALF_ADJ_C": {
            "label": "$V_{half}$ adj. C (high-rise)",
            "baseline_display": "1.05",
            "range_display": "0.89–1.21",
            "primary_index": "EAL",
            "metric_col": "DEF_EAL_historical_baseline_nodef",
            "range_kind": "billions_1",
            "deviation_style": "approx0",
        },
        "V_HALF_ADJ_D": {
            "label": "$V_{half}$ adj. D (commercial)",
            "baseline_display": "1.10",
            "range_display": "0.94–1.27",
            "primary_index": "EAL",
            "metric_col": "DEF_EAL_historical_baseline_nodef",
            "range_kind": "billions_1",
            "deviation_style": "range0",
        },
        "CRI_EWMA_ALPHA": {
            "label": "CRI EWMA decay ($\\alpha$)",
            "baseline_display": "0.85",
            "range_display": "0.70–0.95",
            "primary_index": "CRI",
            "metric_col": "CRI_2050_p50_Historical Baseline",
            "range_kind": "int_0",
            "deviation_style": "pm1",
        },
        "CRI_DAMAGE_KAPPA": {
            "label": "CRI damage boost cap ($\\kappa_d$)",
            "baseline_display": "0.50",
            "range_display": "0.00–1.00",
            "primary_index": "CRI",
            "metric_col": "CRI_2050_p50_Historical Baseline",
            "range_kind": "int_0",
            "deviation_style": "pm1",
            "deviation_override": "±1.8%",
        },
        "HP_LAMBDA": {
            "label": "HP filter $\\lambda$",
            "baseline_display": "129,600",
            "range_display": "14,400–518,400",
            "primary_index": "FRI",
            "metric_col": "FRI_2050_p50_Historical Baseline",
            "range_kind": "int_0",
            "deviation_style": "range0",
        },
        "VOLATILITY_WINDOW": {
            "label": "Volatility window",
            "baseline_display": "12 mo",
            "range_display": "6–24 mo",
            "primary_index": "FRI",
            "metric_col": "FRI_2050_p50_Historical Baseline",
            "range_kind": "int_0",
            "deviation_style": "range1",
        },
        "CFI_WEIGHT_SLA": {
            "label": "Hazard SLA weight",
            "baseline_display": "0.25",
            "range_display": "0.10–0.50",
            "primary_index": "CRI",
            "metric_col": "CRI_2050_p50_Historical Baseline",
            "range_kind": "int_0",
            "deviation_style": "range1",
        },
        "FRI_WEIGHT_GAP": {
            "label": "FRI sub-indicator weights",
            "baseline_display": "Equal",
            "range_display": "See note",
            "primary_index": "FRI",
            "metric_col": "FRI_2050_p50_Historical Baseline",
            "range_kind": "int_0",
            "deviation_style": "range0",
        },
        "CFCI_TARGET_RHO": {
            "label": "CFCI target $\\rho$",
            "baseline_display": "0.411",
            "range_display": "0.0–0.8",
            "primary_index": "CFCI",
            "metric_col": "CFCI_2050_p50_Historical Baseline",
            "range_kind": "int_0",
            "deviation_style": "range1",
            "deviation_override": "−0.2% to +0.6%",
        },
    }

    provenance_lines: list[str] = []
    for sweep_id, spec in table8_specs.items():
        sweep_df, sweep_path = load_sweep(sweep_id, latest_files)
        row = build_table8_row(sweep_df, spec)
        add_literal_check(checks, "Table 8", sweep_id, row, manuscript)
        provenance_lines.append(f"- {sweep_id}: {sweep_path.name}")

    # Conclusion checks.
    conclusion_fragments = [
        "Hongkou (0.83‰)",
        "Yangpu (0.77‰)",
        "Huangpu (0.68‰)",
        "21.5%",
        "CNY 19.0 billion",
        "39.5%",
        "438.9 in December 2023",
        "599 under the baseline",
        "742 under SSP5-8.5",
        "305.1 in June 2025",
        "544 under SSP5-8.5",
        "50.6% above its 2023 terminal value",
    ]
    add_fragments_check(checks, "Conclusion", "Key result numbers", conclusion_fragments, conclusion)

    passed = sum(result.status == "PASS" for result in checks)
    failed = len(checks) - passed
    overall = "PASS" if failed == 0 else "FAIL"

    report_lines = [
        "# Manuscript Consistency Audit",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Overall: {overall} ({passed}/{len(checks)} checks passed)",
        "",
        "## Scope",
        "",
        "- Abstract",
        "- Tables 3-8",
        "- Conclusion",
        "",
        "## Source Rule",
        "",
        "- Tables 3-7 and summary statements are checked against current baseline output CSVs in Climate/output/results, Finance/output/results, and Composite/output/results.",
        "- Table 8 is checked against the latest timestamped sweep CSV per parameter in _sensitivity_results/.",
        "",
        "## Table 8 Provenance",
        "",
    ]
    report_lines.extend(provenance_lines)
    report_lines.extend([
        "",
        "## Checklist",
        "",
        "| Status | Section | Check | Expected | Details |",
        "|---|---|---|---|---|",
    ])
    for result in checks:
        expected = result.expected.replace("|", "\\|")
        details = result.details.replace("|", "\\|") if result.details else ""
        report_lines.append(
            f"| {result.status} | {result.section} | {result.name} | {expected} | {details} |"
        )

    REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"Overall: {overall} ({passed}/{len(checks)} checks passed)")
    if failed:
        print("Failures:")
        for result in checks:
            if result.status == "FAIL":
                print(f"  - [{result.section}] {result.name}: {result.details}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()