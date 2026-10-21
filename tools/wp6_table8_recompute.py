# -*- coding: utf-8 -*-
"""WP6 post-processing: recompute manuscript Table 8 from the sensitivity sweep.

Closes the `pending WP6` rows that `tools/extract_manuscript_numbers.py` left in
docs/_数字变更对照表.md.

Methodology is a literal re-implementation of
`tools/audit_manuscript_consistency.py:build_table8_row()` so the numbers are
comparable with the pre-WP6 state:
    baseline      = the row where is_baseline == True (falls back to the middle row)
    baseline value = metric at baseline
    range value    = min–max of the metric across the sweep's 5 variations
    max deviation  = (min-max - baseline) / baseline * 100, formatted per spec

Inputs  (read-only)
    _sensitivity_results\\sensitivity_results_<ts>.csv   (85 rows, from WP6)
    manuscript\\PAPER_MANUSCRIPT_FINAL.docx               (OLD table cells)
    tools\\audit_manuscript_consistency.py                (table8_specs, lifted via AST)

Outputs
    docs\\_Table8_WP6重算.md    Table 8, 17 parameter rows: OLD (manuscript) vs NEW (WP6)
    docs\\_Table8_WP6重算.csv   same data, machine-readable

Usage
    env\\run.ps1 tools\\wp6_table8_recompute.py
    env\\run.ps1 tools\\wp6_table8_recompute.py --csv <path> --docx <path>
"""

from __future__ import annotations

import argparse
import ast
import csv
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCX_DEFAULT = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_FINAL.docx"
AUDIT_TOOL = NEWROOT / "tools" / "audit_manuscript_consistency.py"
SENS_DIR = NEWROOT / "_sensitivity_results"
OUT_MD = NEWROOT / "docs" / "_Table8_WP6重算.md"
OUT_CSV = NEWROOT / "docs" / "_Table8_WP6重算.csv"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# docx table block index for Table 8 (verified in WP7.1: T8 = Table 8)
TABLE8_BLOCK = 8


# ── formatting helpers: byte-for-byte copies of the audit tool's convention ──
def _round_half_up(value: float, digits: int = 0):
    from decimal import Decimal, ROUND_HALF_UP
    quant = Decimal("1").scaleb(-digits)
    return Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP)


def fmt_billion_value(value: float, digits: int = 1) -> str:
    return f"{_round_half_up(value / 1e9, digits):.{digits}f}"


def fmt_billion(value: float, digits: int = 1) -> str:
    return f"{fmt_billion_value(value, digits)}B"


def fmt_int(value: float) -> str:
    return str(int(_round_half_up(value, 0)))


def fmt_signed_pct(value: float, digits: int) -> str:
    sign = "+" if value >= 0 else "\u2212"
    rounded = abs(_round_half_up(value, digits))
    body = str(int(rounded)) if digits == 0 else f"{rounded:.{digits}f}"
    return f"{sign}{body}%"


def fmt_pm_pct(value: float, digits: int) -> str:
    rounded = abs(_round_half_up(value, digits))
    body = str(int(rounded)) if digits == 0 else f"{rounded:.{digits}f}"
    return f"\u00b1{body}%"


# ── spec extraction ─────────────────────────────────────────────────────────
def load_table8_specs() -> dict:
    tree = ast.parse(AUDIT_TOOL.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "table8_specs":
                    return ast.literal_eval(node.value)
    raise SystemExit(f"could not lift table8_specs out of {AUDIT_TOOL}")


def load_sweep_csv(path: Path) -> dict[str, list[dict]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["sweep_id"], []).append(r)
    return out


def baseline_row(rows: list[dict]) -> dict:
    for r in rows:
        if str(r.get("is_baseline", "")).strip().lower() in ("true", "1", "yes"):
            return r
    return rows[len(rows) // 2]


def recompute_row(sweep_rows: list[dict], spec: dict) -> dict:
    """Returns the recomputed Table 8 cell values + the OLD deviations."""
    base = baseline_row(sweep_rows)
    metric = spec["metric_col"]
    bl = float(base[metric])
    vals = [float(r[metric]) for r in sweep_rows]
    mn, mx = min(vals), max(vals)
    pmin = (mn - bl) / bl * 100.0 if bl else 0.0
    pmax = (mx - bl) / bl * 100.0 if bl else 0.0

    kind = spec["range_kind"]
    if kind == "billions_1":
        baseline_value = fmt_billion(bl, 1)
        range_value = f"{fmt_billion_value(mn, 1)}\u2013{fmt_billion_value(mx, 1)}B"
    elif kind == "int_0":
        baseline_value = fmt_int(bl)
        range_value = f"{fmt_int(mn)}\u2013{fmt_int(mx)}"
    else:
        raise ValueError(f"unknown range_kind {kind}")

    # Deviation is nearly formatting-only. Compute BOTH the style the manuscript
    # uses and the audit-tool style, so a pure formatting difference is never
    # reported as a numeric change (the WP6 boundary shift is only ~0.3%).
    def make(style: str) -> str:
        if style == "range0":
            return f"{fmt_signed_pct(pmin, 0)} to {fmt_signed_pct(pmax, 0)}"
        if style == "range1":
            return f"{fmt_signed_pct(pmin, 1)} to {fmt_signed_pct(pmax, 1)}"
        if style == "pm1":
            return fmt_pm_pct(max(abs(pmin), abs(pmax)), 1)
        if style == "approx0":
            return "$\\approx$0%"
        if style == "abs0":
            return f"{abs(pmin):.0f}% to {abs(pmax):.0f}%"
        raise ValueError(f"unknown deviation_style {style}")

    styles = ["range0", "range1", "pm1", "approx0"]
    if "deviation_override" in spec:
        # the manuscript hard-codes this cell; keep it, but still record the
        # recomputed style value so the mismatch is visible
        deviation = spec["deviation_override"]
        deviation_source = "deviation_override（稿件手写，未随扫描重算）"
    else:
        style = spec["deviation_style"]
        deviation = make(style)
        deviation_source = f"recomputed ({style})"

    return {
        "baseline_value": baseline_value,
        "range_value": range_value,
        "deviation": deviation,
        "deviation_source": deviation_source,
        "dev_styles": {s: make(s) for s in styles},
        "baseline_display": spec["baseline_display"],
        "range_display": spec["range_display"],
        "primary_index": spec["primary_index"],
        "label": spec["label"],
        "n_values": len(sweep_rows),
        "bl_raw": bl,
        "min_raw": mn,
        "max_raw": mx,
        "pmin": pmin,
        "pmax": pmax,
    }


# ── read the OLD Table 8 out of the frozen docx (text cells only) ───────────
def read_old_table8(docx_path: Path) -> list[list[str]]:
    with zipfile.ZipFile(docx_path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    tbls = root.findall(f".//{W}tbl")
    if len(tbls) <= TABLE8_BLOCK:
        raise SystemExit(f"docx has only {len(tbls)} tables, need index {TABLE8_BLOCK}")
    out = []
    for tr in tbls[TABLE8_BLOCK].findall(f"{W}tr"):
        cells = ["".join(t.text or "" for t in tc.iter(f"{W}t"))
                 for tc in tr.findall(f"{W}tc")]
        out.append(cells)
    return out


# rows of Table 8 that are group headers, not parameters
GROUP_HEADER_ROWS = {1, 12, 19}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="")
    ap.add_argument("--docx", default=str(DOCX_DEFAULT))
    ap.add_argument("--out-md", default=str(OUT_MD))
    ap.add_argument("--out-csv", default=str(OUT_CSV))
    args = ap.parse_args()

    if args.csv:
        csv_path = Path(args.csv)
    else:
        cands = sorted(SENS_DIR.glob("sensitivity_results_*.csv"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if not cands:
            raise SystemExit(f"no sensitivity_results_*.csv under {SENS_DIR}")
        csv_path = cands[0]

    print("=" * 78)
    print("WP6 post-processing - recompute manuscript Table 8")
    print("=" * 78)
    print(f"sweep CSV : {csv_path.name}  ({csv_path.stat().st_size:,} B)")
    print(f"docx      : {Path(args.docx).name}")

    specs = load_table8_specs()
    sweeps = load_sweep_csv(csv_path)
    old_tbl = read_old_table8(Path(args.docx))

    missing = [sid for sid in specs if sid not in sweeps]
    if missing:
        print(f"\n!! sweep ids missing from CSV: {missing}")
        print(f"   CSV has: {sorted(sweeps)}")
        return 2

    total_rows = sum(len(v) for v in sweeps.values())
    print(f"sweeps    : {len(sweeps)} / values: {total_rows}")

    records = []
    used_rows: set[int] = set()
    cursor = 1          # row 0 is the header row
    for sweep_id, spec in specs.items():
        rec = recompute_row(sweeps[sweep_id], spec)
        # Walk forward to the next DATA row: group-header rows (e.g. "Physical
        # vulnerability", "Index construction", "Composite") have exactly one
        # non-empty cell. Doing it this way instead of arithmetic row offsets
        # keeps the mapping correct no matter how many header rows there are.
        while cursor < len(old_tbl):
            cells = [c.strip() for c in old_tbl[cursor]]
            non_empty = sum(1 for c in cells if c)
            if cursor in used_rows or non_empty <= 1:
                cursor += 1
                continue
            break
        old_cells = old_tbl[cursor] if cursor < len(old_tbl) else []
        used_rows.add(cursor)
        cursor += 1
        old_base = old_cells[4].strip() if len(old_cells) > 4 else ""
        old_range = old_cells[5].strip() if len(old_cells) > 5 else ""
        old_dev = old_cells[6].strip() if len(old_cells) > 6 else ""
        old_label = old_cells[0].strip() if old_cells else ""
        # classify the deviation cell: pure formatting vs a real number change
        if old_dev == rec["deviation"]:
            dev_verdict = "same"
        elif old_dev in rec["dev_styles"].values():
            dev_verdict = "format-only"
        elif "deviation_override" in spec:
            dev_verdict = "manuscript-hardcoded"
        else:
            dev_verdict = "CHANGE"
        rec.update({
            "sweep_id": sweep_id,
            "docx_row": cursor - 1,
            "old_label": old_label,
            "old_base": old_base,
            "old_range": old_range,
            "old_dev": old_dev,
            "base_changed": old_base != rec["baseline_value"],
            "range_changed": old_range != rec["range_value"],
            "dev_changed": old_dev != rec["deviation"],
            "dev_verdict": dev_verdict,
        })
        records.append(rec)

    n_base = sum(1 for r in records if r["base_changed"])
    n_range = sum(1 for r in records if r["range_changed"])
    n_dev = sum(1 for r in records if r["dev_changed"])
    n_dev_real = sum(1 for r in records if r["dev_verdict"] == "CHANGE")
    n_dev_fmt = sum(1 for r in records if r["dev_verdict"] == "format-only")
    n_dev_hard = sum(1 for r in records if r["dev_verdict"] == "manuscript-hardcoded")

    print()
    print(f"{'sweep':34s} {'OLD baseline':>12s} {'NEW':>12s} {'OLD range':>16s} "
          f"{'NEW':>16s} {'OLD dev':>18s} {'NEW':>18s}")
    for r in records:
        print(f"{r['sweep_id']:34s} {r['old_base']:>12s} {r['baseline_value']:>12s} "
              f"{r['old_range']:>16s} {r['range_value']:>16s} "
              f"{r['old_dev']:>18s} {r['deviation']:>18s}")

    print()
    print(f"changed: baseline {n_base}/17, range {n_range}/17, max-deviation {n_dev}/17")
    print(f"  deviation breakdown: real CHANGE {n_dev_real}, "
          f"format-only {n_dev_fmt}, manuscript-hardcoded {n_dev_hard}")

    # ── write markdown ──────────────────────────────────────────────────────
    L = []
    ap_ = L.append
    ap_("# Table 8 重算（WP6 灵敏度全量重跑后）")
    ap_("")
    ap_(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    ap_(f"- 扫描数据：`{csv_path.name}`（{len(sweeps)} 个 sweep / {total_rows} 个取值）")
    ap_(f"- 旧值来源：`{Path(args.docx).name}` 的 Table 8 单元格（只读，未修改）")
    ap_("- 记账口径：`tools/audit_manuscript_consistency.py:build_table8_row()`")
    ap_("  （baseline = `is_baseline` 行；range = 5 个取值的 min–max；dev = (min/max − baseline)/baseline）")
    ap_("")
    ap_("## 0. 摘要")
    ap_("")
    ap_("| 项 | 17 行中改变 |")
    ap_("|---|---:|")
    ap_(f"| Baseline value 列 | **{n_base}** |")
    ap_(f"| Range of index 列 | **{n_range}** |")
    ap_(f"| Max deviation 列（字面差异） | {n_dev} |")
    ap_(f"| 　其中**真实数值改变** | **{n_dev_real}** |")
    ap_(f"| 　其中仅格式不同（数值兼容） | {n_dev_fmt} |")
    ap_(f"| 　其中稿件手写值（未重算） | {n_dev_hard} |")
    ap_("")
    ap_("> **Max deviation 列的判读**：本列对格式极敏感（`−6.3% to +6.3%` vs `−6% to +6%`）。")
    ap_("> 边界切换只让 CRI 动 ~0.3%，所以绝大多数行是**格式差异**而不是数值变化。")
    ap_("> 只有判定为 `CHANGE` 的行才需要改；`format-only` 行保持稿件原写法即可。")
    ap_("")
    ap_("> 参数名、Baseline、Range tested、Primary index 四列不随扫描变化，无需改。")
    ap_("")
    ap_("## 1. 逐行对照（17 个参数行）")
    ap_("")
    ap_("| # | 参数 | 主指标 | OLD baseline | NEW baseline | OLD range | NEW range | OLD max dev | NEW max dev | dev 判读 |")
    ap_("|---:|---|---|---:|---:|---:|---:|---:|---:|---|")
    for i, r in enumerate(records, start=1):
        mark = lambda ch: "**" if ch else ""  # noqa: E731
        ap_(f"| {i} | {r['label']} | {r['primary_index']} | "
            f"{mark(r['base_changed'])}{r['old_base'] or '—'}{mark(r['base_changed'])} | "
            f"{mark(r['base_changed'])}{r['baseline_value']}{mark(r['base_changed'])} | "
            f"{mark(r['range_changed'])}{r['old_range'] or '—'}{mark(r['range_changed'])} | "
            f"{mark(r['range_changed'])}{r['range_value']}{mark(r['range_changed'])} | "
            f"{r['old_dev'] or '—'} | "
            f"{mark(r['dev_verdict'] == 'CHANGE')}{r['deviation']}{mark(r['dev_verdict'] == 'CHANGE')} | "
            f"{r['dev_verdict']} |")
    ap_("")
    ap_("## 2. 可直接粘贴的新 Table 8（BibTeX 风格 LaTeX 行）")
    ap_("")
    ap_("```latex")
    for r in records:
        ap_(f"{r['label']} & {r['baseline_display']} & {r['range_display']} & "
            f"{r['primary_index']} & {r['baseline_value']} & {r['range_value']} & "
            f"{r['deviation']} \\\\")
    ap_("```")
    ap_("")
    ap_("## 3. 记账细节（供复核）")
    ap_("")
    ap_("| sweep | 取值数 | baseline 原始值 | min | max | min 偏差% | max 偏差% | dev 来源 |")
    ap_("|---|---:|---:|---:|---:|---:|---:|---|")
    for r in records:
        ap_(f"| {r['sweep_id']} | {r['n_values']} | {r['bl_raw']:.6g} | {r['min_raw']:.6g} | "
            f"{r['max_raw']:.6g} | {r['pmin']:+.4f} | {r['pmax']:+.4f} | "
            f"{r['deviation_source']} |")
    ap_("")
    ap_("## 4. Max deviation 列的全部候选格式（供作者选定）")
    ap_("")
    ap_("| sweep | 稿件现值 | range0 | range1 | pm1 | approx0 |")
    ap_("|---|---|---|---|---|---|")
    for r in records:
        st = r["dev_styles"]
        ap_(f"| {r['sweep_id']} | {r['old_dev']} | {st['range0']} | {st['range1']} | "
            f"{st['pm1']} | {st['approx0']} |")
    ap_("")
    Path(args.out_md).write_text("\n".join(L) + "\n", encoding="utf-8")

    # ── write CSV ───────────────────────────────────────────────────────────
    with Path(args.out_csv).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["row", "sweep_id", "label", "primary_index",
                    "old_baseline", "new_baseline", "baseline_changed",
                    "old_range", "new_range", "range_changed",
                    "old_max_dev", "new_max_dev", "dev_changed",
                    "n_values", "bl_raw", "min_raw", "max_raw", "pmin", "pmax"])
        for i, r in enumerate(records, start=1):
            w.writerow([i, r["sweep_id"], r["label"], r["primary_index"],
                        r["old_base"], r["baseline_value"], r["base_changed"],
                        r["old_range"], r["range_value"], r["range_changed"],
                        r["old_dev"], r["deviation"], r["dev_changed"],
                        r["n_values"], f"{r['bl_raw']:.10g}", f"{r['min_raw']:.10g}",
                        f"{r['max_raw']:.10g}", f"{r['pmin']:.6f}", f"{r['pmax']:.6f}"])

    print(f"\nwrote {args.out_md}")
    print(f"wrote {args.out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
