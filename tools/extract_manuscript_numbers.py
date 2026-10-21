# -*- coding: utf-8 -*-
"""WP7.1 - manuscript number extractor and old/new change table builder.

WHAT IT DOES
------------
1. Reads the frozen manuscript `manuscript\\PAPER_MANUSCRIPT_FINAL.docx` (read-only,
   never modified) and enumerates every paragraph and table cell in body order,
   assigning the stable IDs used by WP7.2:
       P{idx}                     body-order paragraph index
       T{tbl}#r{row}c{col}        table block index / row / cell
   It records, per entry, the paragraph style, whether the entry carries an
   OMML math object (m:oMath / m:oMathPara -> "do not replace the whole
   paragraph" whitelist), every numeric token with a +-40 character context.

2. Rebuilds the A-baseline (final-version) value registry from the archived
   WP5-A run and, independently, the OLD (frozen section 2.6) values, using the
   comparison convention of `tools\\audit_manuscript_consistency.py`
   (city = groupby(scenario, defense_profile)[EAL_*].sum();
    district = historical & baseline_nodef, nlargest(5, EAL_compound);
    per-mille = EAL_ratio_pct * 10).
   The recomputed OLD values are asserted against the frozen constants lifted
   out of `tools\\_gate_g4.py` so the registry cannot silently drift.

3. Emits three deliverables:
       docs\\_数值清单.csv        ID, style, has_math, token, context
       docs\\_NEW值_供改写.csv    every registry item with OLD and NEW + provenance
       docs\\_数字变更对照表.md    manuscript location | OLD | NEW, per section,
                                  plus the unmatched-token list for manual review
   Table 8's 20 rows are emitted with status `pending WP6`.

INPUTS  (read-only)
-------------------
  manuscript\\PAPER_MANUSCRIPT_FINAL.docx
  output_archive\\boundary_official_A_20261016_230820\\...      <- NEW values
  tools\\_gate_g4.py                                           <- OLD constants
  docs\\_执行方案_官方边界重跑与稿件更新_v1.md                   <- section 2.6 prose
  tools\\audit_manuscript_consistency.py                        <- Table 8 spec

USAGE
-----
  env\\run.ps1 tools\\extract_manuscript_numbers.py
  env\\run.ps1 tools\\extract_manuscript_numbers.py --docx <file> --out-prefix <dir>\\
  env\\run.ps1 tools\\extract_manuscript_numbers.py --old-only      # skip A archive

DEPENDENCIES
------------
Standard library only for the docx side (zipfile + xml.etree) and for CSV
parsing, so the tool runs under the pipeline env, which has neither python-docx
nor lxml. python-docx / lxml / pandas are used when present, purely as
accelerators; their absence never changes the numbers because the stdlib paths
are authoritative and their results are cross-checked when both are available.
"""

from __future__ import annotations

import argparse
import ast
import csv
import io
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCX_DEFAULT = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_FINAL.docx"
DOCS = NEWROOT / "docs"
A_ARCHIVE_DEFAULT = NEWROOT / "output_archive" / "boundary_official_A_20261016_230820"
LEGACY_ARCHIVE = NEWROOT / "output_archive" / "baseline_legacy_20261016_212711"
G4_TOOL = NEWROOT / "tools" / "_gate_g4.py"
AUDIT_TOOL = NEWROOT / "tools" / "audit_manuscript_consistency.py"
PLAN = DOCS / "_执行方案_官方边界重跑与稿件更新_v1.md"

OUT_INVENTORY = DOCS / "_数值清单.csv"
OUT_NEWVALUES = DOCS / "_NEW值_供改写.csv"
OUT_TABLE = DOCS / "_数字变更对照表.md"
OUT_SEC26 = DOCS / "_§2.6六十项对照.csv"

# Author rulings on Table 8 cells that the recompute changed. Recorded here so
# WP7.2 executes them mechanically instead of re-opening the question.
# breakpoint record §1 rows 14/15 (2026-10-17).
AUTHOR_RULINGS: dict[str, str] = {
    "t8_CFCI_TARGET_RHO": "采用重算值 −0.2% to +0.6%（原 −0.8% to ≈0%）— 作者裁定 #14",
    "t8_VOLATILITY_WINDOW": "采用重算值 −0.1% to +2.6%（原 ≈0% to +2.6%）— 作者裁定 #15",
}
# Ruled NOT to be touched (author left it open; keep the manuscript wording).
AUTHOR_KEEP: dict[str, str] = {
    "t8_V_HALF_ADJ_C": "保留稿件 0%（重算 ≈0%，数值等价）— 裁定 #16 未表态，默认不改",
}

# Exactly the item set that `tools\_gate_g4.py` compares. Measured from the
# gate's own report (docs\_基线复现校验报告.md, label=WP5-official-A):
# "12/60 项一致" is the passed/total display, and ROWS holds 57 items
# (6 city EAL + 3 defense reduction + 2 shares + exposure + district count +
#  5 Top5 + 6 ratios + CRI + 9 CRI2050 + 2 HSI + 9 HSI2050 + 2 CCHI +
#  9 CCHI2050 + building count). The 48/60 quoted in the records is this set
#  with the three non-numeric/label rows counted as the gate counts them.
SEC26_GATE_TOTAL = 57
SEC26_IDS: list[str] = (
    [f"city_eal_{s}_{p}" for s in ("hist", "ssp245", "ssp585") for p in ("nodef", "def")]
    + [f"def_reduction_{s}" for s in ("hist", "ssp245", "ssp585")]
    + ["wind_share", "surge_share", "exposure_total_t"]
    + [f"top5_eal_{i}_{d}" for i, d in enumerate(
        ["浦东新区", "杨浦区", "徐汇区", "闵行区", "虹口区"], start=1)]
    + [f"ratio_{d}" for d in ["浦东新区", "杨浦区", "徐汇区", "闵行区", "虹口区", "黄浦区"]]
    + ["cri_2023_12"]
    + [f"cri2050_{q}_{s}" for s in ("hist", "ssp245", "ssp585")
       for q in ("p10", "p50", "p90")]
    + ["hsi_terminal", "hsi_peak"]
    + [f"hsi2050_{q}_{s}" for s in ("hist", "ssp245", "ssp585")
       for q in ("p10", "p50", "p90")]
    + ["cchi_2011_12", "cchi_2023_12"]
    + [f"cchi2050_{q}_{s}" for s in ("hist", "ssp245", "ssp585")
       for q in ("p10", "p50", "p90")]
    + ["n_buildings", "n_districts"]
)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"

SCEN = {"hist": "historical", "ssp245": "SSP2-4.5", "ssp585": "SSP5-8.5"}
IDX = {"hist": "Historical Baseline", "ssp245": "SSP2-4.5", "ssp585": "SSP5-8.5"}

# Document order of the numeric tables (verified against the docx, 2026-10-17):
TABLE_MAP = {
    0: "Table 1", 1: "Table 2", 2: "Table 3", 3: "Table 4", 4: "Table 5",
    5: "Table 6 (module overview)", 6: "Table 6 (building classes)",
    7: "Table 7", 8: "Table 8", 9: "Table B1", 10: "Table 10 (figure index)",
}

# Numeric token: optional sign, 3- or 4-digit group, decimal, optional exponent,
# then an optional unit / scale / percent / per-mille / degree-Celcius suffix.
TOKEN_RE = re.compile(
    r"(?<![\w.])"
    r"([+\u2212-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|"
    r"[+\u2212-]?\d+(?:\.\d+)?(?:[eE][+\u2212-]?\d+)?)"
    r"(\s?(?:%|\u2030|\u00d7|\u00b0C|km\u00b2|km2|km|m/s|mm|m\b|bn|billion|"
    r"trillion|million|k|T\b|Mt\b|gCO2|CNY|USD))?"
)
# Heading numbers such as "1.1.2", "Methods 3", "Section 1.1-1.6" are structure,
# not data. They are still listed in the inventory (so the whitelist is complete)
# but flagged as structural.
STRUCT_RE = re.compile(r"^(?:\d+(?:\.\d+)+|\d+\.|\d+)\s*$")


# ─────────────────────────────────────────────────────────────── docx reading
@dataclass
class Entry:
    ident: str
    kind: str            # paragraph | table_cell
    style: str
    has_math: bool
    text: str
    tbl_idx: int = -1
    row: int = -1
    col: int = -1


def para_text(p) -> str:
    return "".join(t.text or "" for t in p.iter(f"{W}t"))


def para_has_math(p) -> bool:
    for el in p.iter():
        tag = el.tag
        if tag.startswith(M) and (tag.endswith("}oMath") or tag.endswith("}oMathPara")):
            return True
    return False


def para_style(p) -> str:
    st = p.find(f"{W}pPr/{W}pStyle")
    return st.get(f"{W}val") if st is not None else ""


def read_docx_stdlib(docx_path: Path):
    """Returns (entries, counts). Standard library only."""
    with zipfile.ZipFile(docx_path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    body = root.find(f"{W}body")

    counts = {
        "m_oMath": len(root.findall(f".//{M}oMath")),
        "m_oMathPara": len(root.findall(f".//{M}oMathPara")),
        "w_drawing": len(root.findall(f".//{W}drawing")),
    }

    entries: list[Entry] = []
    p_idx = 0
    t_idx = 0
    for child in body:
        if child.tag == f"{W}p":
            entries.append(Entry(f"P{p_idx}", "paragraph", para_style(child),
                                 para_has_math(child), para_text(child)))
            p_idx += 1
        elif child.tag == f"{W}tbl":
            rows = child.findall(f"{W}tr")
            for r_i, tr in enumerate(rows):
                for c_i, tc in enumerate(tr.findall(f"{W}tc")):
                    parts = [para_text(p) for p in tc.findall(f"{W}p")]
                    txt = " ".join(x for x in parts if x)
                    hm = any(para_has_math(p) for p in tc.findall(f"{W}p"))
                    style = next((para_style(p) for p in tc.findall(f"{W}p") if para_style(p)), "")
                    entries.append(Entry(f"T{t_idx}#r{r_i}c{c_i}", "table_cell", style,
                                         hm, txt, t_idx, r_i, c_i))
            t_idx += 1

    counts["paragraphs"] = p_idx
    counts["tables"] = t_idx
    return entries, counts


def read_docx_pydocx(docx_path: Path):
    """Cross-check via python-docx when available. Returns counts or None."""
    try:
        import docx  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        d = docx.Document(str(docx_path))
    except Exception:  # noqa: BLE001
        return None
    import docx as _d  # noqa: F401  (docx.Document already imported)
    xml = d.element.body.xml
    return {
        "paragraphs": len(d.paragraphs),
        "tables": len(d.tables),
        "m_oMath": xml.count("<m:oMath>") + xml.count("<m:oMath "),
        "m_oMathPara": xml.count("<m:oMathPara"),
        "w_drawing": xml.count("<w:drawing>") + xml.count("<w:drawing "),
    }


# ──────────────────────────────────────────────────────────────── CSV reading
def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Minimal CSV reader (stdlib) - sufficient for the pipeline result files."""
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(row: dict[str, str], key: str) -> float:
    val = row.get(key, "")
    if val is None or val == "":
        raise KeyError(f"missing column/value {key!r} in row {row!r}")
    return float(val)


# ────────────────────────────────────────────────── registry construction
@dataclass
class RegItem:
    section: str
    item_id: str
    label: str
    old: float | None
    new: float | None
    digits: int
    unit: str
    old_src: str
    new_src: str
    match_tokens: list[str] = field(default_factory=list)
    status: str = ""
    note: str = ""
    old_dev: str | None = None
    new_dev: str | None = None
    old_base: str | None = None
    new_base: str | None = None
    old_range: str | None = None
    new_range: str | None = None
    # per-column verdicts for Table 8 (baseline / range-of-index / max-deviation)
    base_chg: bool | None = None
    range_chg: bool | None = None
    dev_chg: bool | None = None

    def fmt(self, which: str) -> str:
        val = self.old if which == "old" else self.new
        if val is None:
            return ""
        if self.unit == "count":
            return f"{int(round(val)):,}"
        return f"{val:.{self.digits}f}"


def load_frozen_old() -> tuple[dict, dict]:
    """Lift the frozen section 2.6 constants out of tools\\_gate_g4.py."""
    src = G4_TOOL.read_text(encoding="utf-8")
    tree = ast.parse(src)
    frozen = None
    scen = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "FROZEN":
                    frozen = ast.literal_eval(node.value)
                if isinstance(tgt, ast.Name) and tgt.id == "SCEN":
                    scen = ast.literal_eval(node.value)
    if frozen is None:
        raise SystemExit(f"could not lift FROZEN out of {G4_TOOL}")
    return frozen, (scen or {})


def load_table8_spec() -> dict:
    """Lift `table8_specs` out of tools\\audit_manuscript_consistency.py."""
    src = AUDIT_TOOL.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    for tgt in sub.targets:
                        if isinstance(tgt, ast.Name) and tgt.id == "table8_specs":
                            return ast.literal_eval(sub.value)
    raise SystemExit(f"could not lift table8_specs out of {AUDIT_TOOL}")


def load_outputs(archive: Path | None) -> dict:
    """Load the A-baseline result CSVs (archive first, live outputs as fallback)."""
    if archive is not None and archive.exists():
        root, tag = archive, "archive"
    else:
        root, tag = NEWROOT, "live"

    def res(module: str, name: str) -> Path:
        return root / module / "output" / "results" / name

    out: dict = {"root": root, "tag": tag, "paths": {}, "tables": {}}

    table_specs = {
        "defense": ("Climate", "defense_sensitivity/defense_profile_eal.csv"),
        "cri": ("Climate", "shanghai_city_cri_projection.csv"),
        "cri_hist": ("Composite", "shanghai_cfci_historical.csv"),
        "hsi_hist": ("Finance", "shanghai_finance_risk_index.csv"),
        "hsi_proj": ("Finance", "shanghai_fri_projection.csv"),
        "cci_proj": ("Composite", "shanghai_cfci_projection.csv"),
    }
    for key, (module, rel) in table_specs.items():
        p = res(module, rel)
        if not p.exists():
            raise SystemExit(f"missing result file for {key}: {p}")
        out["paths"][key] = p
        out["tables"][key] = read_csv_rows(p)

    pq = root / "Climate" / "output" / "intermediate" / "building_skeleton.parquet"
    out["building_parquet"] = pq if pq.exists() else None

    # city aggregation exactly as audit_manuscript_consistency.py does it
    agg: dict[tuple[str, str], dict[str, float]] = {}
    for row in out["tables"]["defense"]:
        key = (row["scenario"], row["defense_profile"])
        slot = agg.setdefault(key, {"EAL_compound": 0.0, "EAL_wind": 0.0,
                                    "EAL_surge": 0.0, "exposure_total": 0.0})
        for col in slot:
            slot[col] += fnum(row, col)
    out["city"] = agg

    hist = [r for r in out["tables"]["defense"]
            if r["scenario"] == "historical" and r["defense_profile"] == "baseline_nodef"]
    out["hist_districts"] = sorted(hist, key=lambda r: -fnum(r, "EAL_compound"))
    return out


def row_at(rows: list[dict[str, str]], scenario: str, date: str) -> dict[str, str]:
    for r in rows:
        if r.get("scenario") == scenario and r.get("date") == date:
            return r
    raise KeyError(f"no row scenario={scenario} date={date}")


def build_registry(out: dict, frozen: dict) -> list[RegItem]:
    city = out["city"]
    p = out["paths"]
    a_src = f"A 基线 {out['tag']}: {(out['root'].name)}\\{{module}}\\output\\results\\..."
    items: list[RegItem] = []
    idx_src = f"docs\\_基线复现校验报告.md + _gate_g4.py FROZEN (label=WP5-official-A)"

    def add(section, item_id, label, old, new, digits, unit, new_file, tokens=(), note=""):
        items.append(RegItem(
            section=section, item_id=item_id, label=label, old=old, new=new,
            digits=digits, unit=unit,
            old_src="§2.6 冻结参考值（旧层口径）",
            new_src=f"{out['root'].name}/{new_file}" if new_file else "",
            match_tokens=list(tokens), note=note))

    # ---- section 2.6 : city EAL ------------------------------------------
    prof = {"nodef": "baseline_nodef", "def": "current_def_gap"}
    for scen in ("hist", "ssp245", "ssp585"):
        for pf, pfull in prof.items():
            key = (scen, pf)
            new_bn = city[(SCEN[scen], pfull)]["EAL_compound"] / 1e9
            add("2.6 城市 EAL", f"city_eal_{scen}_{pf}",
                f"城市复合 EAL {scen} / {pf}", frozen["city_eal_bn"][key], new_bn,
                3, "bn CNY", "Climate/output/results/defense_sensitivity/defense_profile_eal.csv")

    for scen in ("hist", "ssp245", "ssp585"):
        n = city[(SCEN[scen], "baseline_nodef")]["EAL_compound"]
        d = city[(SCEN[scen], "current_def_gap")]["EAL_compound"]
        add("2.6 防御削减率", f"def_reduction_{scen}",
            f"6 m 海塘削减率 {scen}", frozen["defense_reduction_pct"][scen],
            (1 - d / n) * 100, 2, "%",
            "Climate/output/results/defense_sensitivity/defense_profile_eal.csv")

    w = city[("historical", "baseline_nodef")]["EAL_wind"]
    s = city[("historical", "baseline_nodef")]["EAL_surge"]
    c = city[("historical", "baseline_nodef")]["EAL_compound"]
    add("2.6 风/潮占比", "wind_share", "风损占比 hist/nodef", frozen["wind_share_pct"],
        w / (w + s) * 100, 2, "%",
        "Climate/output/results/defense_sensitivity/defense_profile_eal.csv")
    add("2.6 风/潮占比", "surge_share", "潮损占比 hist/nodef", frozen["surge_share_pct"],
        s / (w + s) * 100, 2, "%",
        "Climate/output/results/defense_sensitivity/defense_profile_eal.csv")
    add("2.6 风/潮占比", "surge_eal_bn", "潮损 EAL hist/nodef (bn)",
        frozen["surge_share_pct"] and 6.2471, s / 1e9, 4, "bn CNY",
        "Climate/output/results/defense_sensitivity/defense_profile_eal.csv",
        note="OLD = 旧层实测 6.2471（WP4 基线）；NEW = A 基线")
    add("2.6 派生文本量", "wind_eal_bn", "风损 EAL hist/nodef (bn)", 17.9059,
        w / 1e9, 4, "bn CNY",
        "Climate/output/results/defense_sensitivity/defense_profile_eal.csv")
    ssp585_surge = city[(SCEN["ssp585"], "baseline_nodef")]["EAL_surge"]
    add("2.6 派生文本量", "surge_eal_ssp585_bn", "潮损 EAL SSP5-8.5/nodef (bn)",
        None, ssp585_surge / 1e9, 4, "bn CNY",
        "Climate/output/results/defense_sensitivity/defense_profile_eal.csv",
        note="P16 的 \"about CNY 6.2 bn to roughly CNY 16 bn\" 中的 16")

    # relative increments of each SSP over the historical no-defence city EAL
    hist_nodef = city[(SCEN["hist"], "baseline_nodef")]["EAL_compound"]
    for scen, old_display in (("ssp245", "+38%"), ("ssp585", "+66%")):
        incr = (city[(SCEN[scen], "baseline_nodef")]["EAL_compound"] / hist_nodef - 1) * 100
        add("2.6 派生文本量", f"eal_incr_{scen}", f"城市 EAL 相对历史无防御增幅 {scen}",
            None, incr, 0, "%",
            "Climate/output/results/defense_sensitivity/defense_profile_eal.csv",
            note=f"P16 稿件写 {old_display}；OLD 不是可复算量（按稿件现值记录，"
                 f"NEW 由 A 基线算得 {incr:.2f}%）")
    add("2.6 派生文本量", "compound_share_wind_pct", "风损占复合 EAL (%)",
        w / c * 100, w / c * 100, 2, "%", "")

    expo_t = sum(fnum(r, "exposure_total") for r in out["hist_districts"]) / 1e12
    add("2.6 总暴露", "exposure_total_t", "总暴露 (T CNY)", frozen["exposure_total_t"],
        expo_t, 4, "T CNY",
        "Climate/output/results/defense_sensitivity/defense_profile_eal.csv")

    for i, (district, old_val) in enumerate(frozen["top5_eal_bn"]):
        new_val = None
        for r in out["hist_districts"]:
            if r["district"] == district:
                new_val = fnum(r, "EAL_compound") / 1e9
                break
        add("2.6 区级 Top5 EAL", f"top5_eal_{i+1}_{district}", f"区级 EAL #{i+1} {district}",
            old_val, new_val, 4, "bn CNY",
            "Climate/output/results/defense_sensitivity/defense_profile_eal.csv")

    for district, old_val in frozen["district_ratio_permille"]:
        new_val = None
        for r in out["hist_districts"]:
            if r["district"] == district:
                new_val = fnum(r, "EAL_ratio_pct") * 10
                break
        add("2.6 区级 EAL/暴露", f"ratio_{district}", f"{district} EAL/暴露",
            old_val, new_val, 4, "\u2030",
            "Climate/output/results/defense_sensitivity/defense_profile_eal.csv")

    # derived text quantity: city-wide mean EAL/exposure over the 16 districts.
    # The OLD value is read from the WP4 legacy archive (not approximated), so
    # the comparison stays data-driven.
    mean_ratio_new = sum(fnum(r, "EAL_ratio_pct") * 10 for r in out["hist_districts"]) / len(
        out["hist_districts"])
    mean_ratio_old = None
    if LEGACY_ARCHIVE.exists() and LEGACY_ARCHIVE != out["root"]:
        try:
            leg = [r for r in read_csv_rows(
                LEGACY_ARCHIVE / "Climate" / "output" / "results" /
                "defense_sensitivity" / "defense_profile_eal.csv")
                if r["scenario"] == "historical" and r["defense_profile"] == "baseline_nodef"]
            if leg:
                mean_ratio_old = sum(fnum(r, "EAL_ratio_pct") * 10 for r in leg) / len(leg)
        except Exception:  # noqa: BLE001
            mean_ratio_old = None
    add("2.6 派生文本量", "city_mean_ratio", "全市平均 EAL/暴露（16 区均值）",
        mean_ratio_old, mean_ratio_new, 2, "\u2030",
        "Climate/output/results/defense_sensitivity/defense_profile_eal.csv",
        note="P19 正文写 0.38\u2030；OLD 取自 WP4 旧层归档")

    # ---- CRI --------------------------------------------------------------
    cri_hist = out["tables"]["cri_hist"]
    cri_2312 = next(fnum(r, "cri_index") for r in cri_hist if r["date"] == "2023-12-01")
    add("2.6 CRI", "cri_2023_12", "CRI 2023-12", frozen["cri_2023_12"], cri_2312, 4, "",
        "Composite/output/results/shanghai_cfci_historical.csv")
    add("2.6 CRI", "cri_1993_fold", "CRI 2023-12 相对 1993-06 基线的倍数",
        4.4, cri_2312 / 100.0, 1, "x",
        "Composite/output/results/shanghai_cfci_historical.csv",
        note="稿件 P41 写 4.4-fold（基线 100）；表内按 1 位小数")
    cri = out["tables"]["cri"]
    for scen, w50, w10, w90 in frozen["cri_2050"]:
        r = row_at(cri, IDX[scen], "2050-12-01")
        add("2.6 CRI", f"cri2050_p50_{scen}", f"CRI 2050 p50 {scen}", w50,
            fnum(r, "cri_index_p50"), 3, "", "Climate/output/results/shanghai_city_cri_projection.csv")
        add("2.6 CRI", f"cri2050_p10_{scen}", f"CRI 2050 p10 {scen}", w10,
            fnum(r, "cri_index_p10"), 2, "", "Climate/output/results/shanghai_city_cri_projection.csv")
        add("2.6 CRI", f"cri2050_p90_{scen}", f"CRI 2050 p90 {scen}", w90,
            fnum(r, "cri_index_p90"), 2, "", "Climate/output/results/shanghai_city_cri_projection.csv")

    # ---- HSI --------------------------------------------------------------
    hsi_hist = out["tables"]["hsi_hist"]
    indexed = [r for r in hsi_hist if r.get("fri_index") not in ("", None)]
    last = indexed[-1]
    peak = max(indexed, key=lambda r: fnum(r, "fri_index"))
    add("2.6 HSI", "hsi_terminal", "HSI 末值", frozen["hsi_terminal"],
        fnum(last, "fri_index"), 2, "", "Finance/output/results/shanghai_finance_risk_index.csv")
    add("2.6 HSI", "hsi_peak", "HSI 峰值", frozen["hsi_peak"],
        fnum(peak, "fri_index"), 2, "", "Finance/output/results/shanghai_finance_risk_index.csv")
    hsi_proj = out["tables"]["hsi_proj"]
    for scen, w50, w10, w90 in frozen["hsi_2050"]:
        r = row_at(hsi_proj, IDX[scen], "2050-12-01")
        add("2.6 HSI", f"hsi2050_p50_{scen}", f"HSI 2050 p50 {scen}", w50,
            fnum(r, "fri_index_p50"), 3, "", "Finance/output/results/shanghai_fri_projection.csv")
        add("2.6 HSI", f"hsi2050_p10_{scen}", f"HSI 2050 p10 {scen}", w10,
            fnum(r, "fri_index_p10"), 2, "", "Finance/output/results/shanghai_fri_projection.csv")
        add("2.6 HSI", f"hsi2050_p90_{scen}", f"HSI 2050 p90 {scen}", w90,
            fnum(r, "fri_index_p90"), 2, "", "Finance/output/results/shanghai_fri_projection.csv")

    # ---- CCHI -------------------------------------------------------------
    add("2.6 CCHI", "cchi_2011_12", "CCHI 2011-12", frozen["cchi_2011_12"],
        fnum(cri_hist[0], "cfci"), 3, "",
        "Composite/output/results/shanghai_cfci_historical.csv")
    add("2.6 CCHI", "cchi_2023_12", "CCHI 2023-12", frozen["cchi_2023_12"],
        fnum(cri_hist[-1], "cfci"), 3, "",
        "Composite/output/results/shanghai_cfci_historical.csv")
    cci_proj = out["tables"]["cci_proj"]
    for scen, w50, w10, w90 in frozen["cchi_2050"]:
        r = row_at(cci_proj, IDX[scen], "2050-12-01")
        add("2.6 CCHI", f"cchi2050_p50_{scen}", f"CCHI 2050 p50 {scen}", w50,
            fnum(r, "cfci_p50"), 3, "", "Composite/output/results/shanghai_cfci_projection.csv")
        add("2.6 CCHI", f"cchi2050_p10_{scen}", f"CCHI 2050 p10 {scen}", w10,
            fnum(r, "cfci_p10"), 2, "", "Composite/output/results/shanghai_cfci_projection.csv")
        add("2.6 CCHI", f"cchi2050_p90_{scen}", f"CCHI 2050 p90 {scen}", w90,
            fnum(r, "cfci_p90"), 2, "", "Composite/output/results/shanghai_cfci_projection.csv")

    # CCHI % increase over the 2023 terminal value (manuscript: 52%)
    add("2.6 派生文本量", "cchi_ssp585_vs_terminal_pct", "CCHI SSP5-8.5 相对 2023 末值增幅",
        52.0, (fnum(row_at(cci_proj, IDX["ssp585"], "2050-12-01"), "cfci_p50")
               / fnum(cri_hist[-1], "cfci") - 1) * 100, 0, "%",
        "Composite/output/results/shanghai_cfci_projection.csv")

    # CRI median increments of the SSPs over the historical baseline
    cb = fnum(row_at(cri, IDX["hist"], "2050-12-01"), "cri_index_p50")
    for scen, old in (("ssp245", 12.4), ("ssp585", 23.9)):
        add("2.6 派生文本量", f"cri_incr_{scen}", f"CRI 2050 中位增量 {scen}",
            old, (fnum(row_at(cri, IDX[scen], "2050-12-01"), "cri_index_p50") / cb - 1) * 100,
            1, "%", "Climate/output/results/shanghai_city_cri_projection.csv")

    add("2.6 计数", "n_buildings", "建筑数", float(frozen["n_buildings"]), None, 0, "count",
        "", note="A 基线未变（585,033）；WP7.2 不改")
    add("2.6 计数", "n_districts", "区县数", float(frozen["n_districts"]), None, 0, "count",
        "", note="不变")

    # synthetic catalogue size: read from the hazard HDF5 (1177 = 107 + 107*10)
    n_synth_total = None
    n_synth_generated = None
    haz_path = out["root"] / "Climate" / "output" / "intermediate" / "haz_TC_synth.hdf5"
    if haz_path.exists():
        try:
            import h5py  # type: ignore
            with h5py.File(haz_path, "r") as f:
                names = [x.decode() if isinstance(x, bytes) else str(x)
                         for x in f["event_name"][()]]
                n_synth_total = len(names)
                n_synth_generated = sum(1 for n in names if "_gen" in n)
        except Exception:  # noqa: BLE001
            n_synth_total = None
    add("2.6 计数", "synthetic_catalogue_n", "合成路径数（= 107 × 10，按 _genN 计数）",
        1070, n_synth_generated, 0, "count",
        "Climate/output/intermediate/haz_TC_synth.hdf5",
        note=f"稿件 P17 写 1,070 条合成实现；扫描件实测 _gen 路径 "
             f"{n_synth_generated} 条，事件总数 {n_synth_total}（含 107 条历史路径）")

    # calibration ratio: inherited from the v6 validation, not recomputed by the
    # boundary change. Reported for completeness, NOT auto-updated.
    add("2.6 派生文本量", "tc_calibration_ratio", "TC 标定比 AAL pred/obs (1995-2023)",
        0.9999, None, 4, "", "",
        note="WP7.2 不改数值；但边界与潮损口径已变，需在 WP6/WP7 复核后决定是否重算与披露")

    # the "39.5% above the historical no-defence level" claim: NOT reproducible
    # from the ratio the sentence uses (legacy layer gives ~9.6%), so the
    # recomputed value is recorded as a candidate while the manuscript number is
    # left untouched and flagged for the author.
    add("2.6 派生文本量", "residual_above_hist_nodef_pct",
        "SSP5-8.5 防御后 EAL ÷ 历史无防御 EAL − 1（候选解释）",
        None, (city[(SCEN["ssp585"], "current_def_gap")]["EAL_compound"]
               / city[(SCEN["hist"], "baseline_nodef")]["EAL_compound"] - 1) * 100,
        1, "%", "Climate/output/results/defense_sensitivity/defense_profile_eal.csv",
        note="稿件 P16/P79/P83 写 39.5%。该句的算术只给出约 9.6%（旧层同为 9.6%），"
             "故 39.5% 无法由本口径复现 —— 不要自动改，须作者确认定义")

    # ---- Table 1..5 -------------------------------------------------------
    for scen, label in (("hist", "Historical"), ("ssp245", "SSP2-4.5 (+0.3 m SLR)"),
                        ("ssp585", "SSP5-8.5 (+0.5 m SLR)")):
        n = city[(SCEN[scen], "baseline_nodef")]["EAL_compound"] / 1e9
        d = city[(SCEN[scen], "current_def_gap")]["EAL_compound"] / 1e9
        add("Table 1", f"t1_nodef_{scen}", f"T1 {label} No Defence", frozen["city_eal_bn"][(scen, "nodef")],
            n, 1, "bn", "defense_profile_eal.csv")
        add("Table 1", f"t1_def_{scen}", f"T1 {label} Current 6 m", frozen["city_eal_bn"][(scen, "def")],
            d, 1, "bn", "defense_profile_eal.csv")
        add("Table 1", f"t1_red_{scen}", f"T1 {label} Reduction",
            frozen["defense_reduction_pct"][scen], (1 - d / n) * 100,
            1 if scen == "hist" else 0, "%", "defense_profile_eal.csv",
            note="T1 第 1 行稿件写 21.5%（1 位小数）；SSP 两行写整数")

    # ---- Table 2 ----------------------------------------------------------
    # The docx rows keep their printed district LABELS; the A-baseline ranking
    # puts Minhang 3rd and Xuhui 4th (legacy had Xuhui 3rd), so rows 3 and 4
    # must exchange their numbers. `pos` maps a docx row index (0-based) to the
    # index in the A-baseline ranking whose figures belong on that row.
    T2_LABELS = [("Pudong", "浦东新区"), ("Yangpu", "杨浦区"), ("Xuhui", "徐汇区"),
                 ("Minhang", "闵行区"), ("Hongkou", "虹口区")]
    T2_POS = [0, 1, 3, 2, 4]
    T2_OLD = {
        "Pudong": (5.9, 14.8, 0.40), "Yangpu": (2.6, 3.4, 0.77), "Xuhui": (2.3, 4.1, 0.56),
        "Minhang": (2.3, 8.0, 0.28), "Hongkou": (1.7, 2.0, 0.83),
    }
    for row_i, (label_en, district) in enumerate(T2_LABELS):
        r = out["hist_districts"][T2_POS[row_i]]
        src_en = {"浦东新区": "Pudong", "杨浦区": "Yangpu", "徐汇区": "Xuhui",
                  "闵行区": "Minhang", "虹口区": "Hongkou", "黄浦区": "Huangpu"}[r["district"]]
        swapped = src_en != label_en
        old_eal, old_expo, old_ratio = T2_OLD[label_en]
        note = (f"**换位**：稿件第{row_i + 1}行标签 {label_en}，A 口径该位实为 "
                f"{src_en}（{r['district']}）" if swapped
                else f"名次未变：{src_en}（{r['district']}）")
        add("Table 2", f"t2_r{row_i + 1}_name", f"T2 第{row_i + 1}行 区名", None, None,
            0, "", "defense_profile_eal.csv", note=note, tokens=[label_en])
        add("Table 2", f"t2_r{row_i + 1}_eal", f"T2 第{row_i + 1}行 EAL（{label_en} 行）",
            old_eal, fnum(r, "EAL_compound") / 1e9, 1, "bn", "defense_profile_eal.csv",
            note=note)
        add("Table 2", f"t2_r{row_i + 1}_expo", f"T2 第{row_i + 1}行 暴露（{label_en} 行）",
            old_expo, fnum(r, "exposure_total") / 1e12, 1, "T", "defense_profile_eal.csv",
            note=note)
        add("Table 2", f"t2_r{row_i + 1}_ratio", f"T2 第{row_i + 1}行 比值（{label_en} 行）",
            old_ratio, fnum(r, "EAL_ratio_pct") * 10, 2, "\u2030",
            "defense_profile_eal.csv", note=note)

    for scen, w50, w10, w90 in frozen["cri_2050"]:
        r = row_at(cri, IDX[scen], "2050-12-01")
        add("Table 3", f"t3_p10_{scen}", f"T3 {scen} p10", w10, fnum(r, "cri_index_p10"), 0, "",
            "shanghai_city_cri_projection.csv")
        add("Table 3", f"t3_p50_{scen}", f"T3 {scen} p50", w50, fnum(r, "cri_index_p50"), 0, "",
            "shanghai_city_cri_projection.csv")
        add("Table 3", f"t3_p90_{scen}", f"T3 {scen} p90", w90, fnum(r, "cri_index_p90"), 0, "",
            "shanghai_city_cri_projection.csv")

    for scen, w50, w10, w90 in frozen["hsi_2050"]:
        r = row_at(hsi_proj, IDX[scen], "2050-12-01")
        add("Table 4", f"t4_p10_{scen}", f"T4 {scen} p10", w10, fnum(r, "fri_index_p10"), 0, "",
            "shanghai_fri_projection.csv")
        add("Table 4", f"t4_p50_{scen}", f"T4 {scen} p50", w50, fnum(r, "fri_index_p50"), 0, "",
            "shanghai_fri_projection.csv")
        add("Table 4", f"t4_p90_{scen}", f"T4 {scen} p90", w90, fnum(r, "fri_index_p90"), 0, "",
            "shanghai_fri_projection.csv")

    for scen, w50, w10, w90 in frozen["cchi_2050"]:
        r = row_at(cci_proj, IDX[scen], "2050-12-01")
        add("Table 5", f"t5_p10_{scen}", f"T5 {scen} p10", w10, fnum(r, "cfci_p10"), 0, "",
            "shanghai_cfci_projection.csv")
        add("Table 5", f"t5_p50_{scen}", f"T5 {scen} p50", w50, fnum(r, "cfci_p50"), 0, "",
            "shanghai_cfci_projection.csv")
        add("Table 5", f"t5_p90_{scen}", f"T5 {scen} p90", w90, fnum(r, "cfci_p90"), 0, "",
            "shanghai_cfci_projection.csv")

    # ---- derived text quantities that the manuscript quotes --------------
    def district_row(rows, name):
        return next((r for r in rows if r["district"] == name), None)

    ssp585_hist = [r for r in out["tables"]["defense"]
                   if r["scenario"] == "SSP5-8.5" and r["defense_profile"] == "baseline_nodef"]
    for dname, en, old_eal, old_ratio in (("杨浦区", "Yangpu", 5.4, 1.57),
                                          ("虹口区", "Hongkou", 3.5, 1.73)):
        r = district_row(ssp585_hist, dname)
        add("2.6 派生文本量", f"ssp585_eal_{dname}", f"SSP5-8.5 区级 EAL {en}",
            old_eal, fnum(r, "EAL_compound") / 1e9 if r else None, 1, "bn CNY",
            "Climate/output/results/defense_sensitivity/defense_profile_eal.csv",
            note="P21 引用的区级 SSP5-8.5 值；OLD = 稿件现值")
        add("2.6 派生文本量", f"ssp585_ratio_{dname}", f"SSP5-8.5 区级 EAL/暴露 {en}",
            old_ratio, fnum(r, "EAL_ratio_pct") * 10 if r else None, 2, "\u2030",
            "Climate/output/results/defense_sensitivity/defense_profile_eal.csv")
    for dname, en, old_pct in (("杨浦区", "Yangpu", 100.0), ("虹口区", "Hongkou", 100.0)):
        h = district_row(out["hist_districts"], dname)
        s = district_row(ssp585_hist, dname)
        old_v = fnum(h, "EAL_compound") if h else None
        new_v = (fnum(s, "EAL_compound") / fnum(h, "EAL_compound") - 1) * 100 if h and s else None
        add("2.6 派生文本量", f"ssp585_growth_{dname}", f"SSP5-8.5 区级 EAL 增幅 {en}",
            old_v and 100.0 or old_pct, new_v, 1, "%",
            "Climate/output/results/defense_sensitivity/defense_profile_eal.csv",
            note="P21 的 \"more than doubles\" 判据；OLD = 稿件表述 100%（doubles）。"
                 "若 NEW < 100 则该措辞不再成立，必须改")
        h_r = fnum(h, "EAL_ratio_pct") * 10 if h else None
        n_r = fnum(s, "EAL_ratio_pct") * 10 if s else None
        if h_r and n_r:
            add("2.6 派生文本量", f"ssp585_ratio_growth_{dname}",
                f"SSP5-8.5 区级比值增幅 {en}", 100.0, (n_r / h_r - 1) * 100, 1, "%",
                "Climate/output/results/defense_sensitivity/defense_profile_eal.csv",
                note=f"P21 用；历史比值 {h_r:.2f}\u2030 → SSP5-8.5 {n_r:.2f}\u2030")

    add("2.6 派生文本量", "cchi_target_rho", "CFCI 目标 Spearman 秩相关 ρ",
        0.358, 0.358, 3, "",
        "Composite/00_config.py",
        note="已核对：`Composite\\00_config.py:76 CFCI_TARGET_RHO = 0.358`，"
             "`config\\sensitivity_sweep.json` 的 baseline/取值也含 0.358；"
             "稿件 P49/P62 与 T8 第 20 行一致，边界切换不影响该常量")
    band_pending = "pending WP6：须由灵敏度重跑后的 Max deviation 列取值"
    # resolved bands (read from the WP6 Table 8 recompute when available)
    t8_by_id: dict[str, dict] = {}
    t8_path = DOCS / "_Table8_WP6重算.csv"
    if t8_path.exists():
        for row in read_csv_rows(t8_path):
            t8_by_id[row["sweep_id"]] = row

    def band_of(sweep_ids: tuple[str, ...]) -> tuple[str | None, str | None]:
        olds, news = [], []
        for sid in sweep_ids:
            r = t8_by_id.get(sid)
            if r is None:
                return None, None
            olds.append(r["old_max_dev"])
            news.append(r["new_max_dev"])
        return " / ".join(olds), " / ".join(news)

    for iid, lbl, p, sids in (
            ("cri_param_band_pct", "CRI 构造参数带（P42 的 ±2%）", "P42",
             ("CRI_EWMA_ALPHA", "CRI_DAMAGE_KAPPA")),
            ("t8_HSI_WEIGHT_BAND", "HSI 权重带（P66 的 ±17%）", "P66", ("FRI_WEIGHT_GAP",)),
            ("t8_CFCI_TARGET_RHO_BAND", "CFCI 目标 ρ 带（P66 的 −0.8% to ≈0%）", "P66",
             ("CFCI_TARGET_RHO",)),
            ("t8_TC_IMPACT_V_THRESH", "TC 起损阈值带（P79 的 −23% to +31%）", "P79",
             ("TC_IMPACT_V_THRESH",))):
        old_dev, new_dev = band_of(sids)
        it = RegItem(section="Table 8 派生带", item_id=iid, label=lbl, old=None, new=None,
                     digits=1, unit="%", old_src="稿件现值（旧层口径）",
                     new_src=("docs\\_Table8_WP6重算.csv（WP6 实测）" if new_dev
                              else "待 WP6 灵敏度全量重跑"),
                     status=("CHANGE" if new_dev and old_dev != new_dev
                             else ("same" if new_dev else "pending WP6")),
                     old_dev=old_dev, new_dev=new_dev,
                     note=f"{p}；Max deviation 实测 OLD={old_dev} → NEW={new_dev}"
                          if new_dev else f"{p}；{band_pending}")
        items.append(it)

    return items


def build_table8_rows(spec: dict, sweep_dir: Path, resolved_csv: Path | None = None) -> list[RegItem]:
    """Table 8's 17 parameter rows.

    Before WP6 the cells are `pending WP6`. Once `tools/wp6_table8_recompute.py`
    has produced `docs/_Table8_WP6重算.csv`, `resolved_csv` points at it and the
    rows get the measured OLD/NEW pairs instead.
    """
    resolved: dict[str, dict] = {}
    if resolved_csv is not None and resolved_csv.exists():
        for row in read_csv_rows(resolved_csv):
            resolved[row["sweep_id"]] = row

    rows: list[RegItem] = []
    have = sorted(sweep_dir.glob("sensitivity_results_*.csv")) if sweep_dir.exists() else []
    sweep_note = (f"扫描件 {len(have)} 个" if have else "无扫描件")
    for sweep_id, s in spec.items():
        old_base = old_range = old_dev = None
        new_base = new_range = new_dev = None
        base_chg = range_chg = dev_chg = None
        status = "pending WP6"
        r = resolved.get(sweep_id)
        if r is not None:
            old_base = r.get("old_baseline") or None
            new_base = r.get("new_baseline") or None
            old_range = r.get("old_range") or None
            new_range = r.get("new_range") or None
            old_dev = r.get("old_max_dev") or None
            new_dev = r.get("new_max_dev") or None
            base_chg = str(r.get("baseline_changed")).lower() == "true"
            range_chg = str(r.get("range_changed")).lower() == "true"
            dev_chg = str(r.get("dev_changed")).lower() == "true"
            status = "CHANGE" if (base_chg or range_chg or dev_chg) else "same"
        rows.append(RegItem(
            section="Table 8", item_id=f"t8_{sweep_id}", label=s["label"],
            old=None, new=None, digits=1, unit="",
            old_src="稿件 Table 8 现状（旧层口径）",
            new_src=("docs\\_Table8_WP6重算.csv（WP6 实测）" if r is not None
                     else "待 WP6 灵敏度全量重跑"),
            status=status,
            old_dev=old_dev, new_dev=new_dev,
            old_base=old_base, new_base=new_base,
            old_range=old_range, new_range=new_range,
            base_chg=base_chg, range_chg=range_chg, dev_chg=dev_chg,
            note=f"baseline={s['baseline_display']} range={s['range_display']} "
                 f"index={s['primary_index']} dev={s.get('deviation_style', '')} "
                 f"metric={s['metric_col']} [{sweep_note}]"
                 + (f" | OLD dev={old_dev} → NEW dev={new_dev}" if r is not None else "")
                 + (f" | ★{AUTHOR_RULINGS[f't8_{sweep_id}']}"
                    if f"t8_{sweep_id}" in AUTHOR_RULINGS else "")
                 + (f" | ⏸{AUTHOR_KEEP[f't8_{sweep_id}']}"
                    if f"t8_{sweep_id}" in AUTHOR_KEEP else "")))
    return rows


# ───────────────────────────────────────────────────── number-token inventory
def numeric_tokens(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in TOKEN_RE.finditer(text)]


def norm_token(tok: str) -> str:
    t = tok.strip()
    t = t.replace("\u2212", "-").replace(",", "")
    t = t.replace("%", "").replace("\u2030", "").replace("\u00d7", "")
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"(km\u00b2|km2|m/s|mm|bn|billion|trillion|million|km|k|T|Mt|CNY|USD|\u00b0C)$", "", t)
    return t


def as_number(tok: str) -> float | None:
    n = norm_token(tok)
    try:
        return float(n)
    except ValueError:
        return None


def fmt_old_new(item: RegItem) -> tuple[str, str]:
    # deviation-band items carry text ranges instead of scalars
    if item.old_dev is not None or item.new_dev is not None:
        return (item.old_dev or ""), (item.new_dev or "")

    def one(which: str) -> str:
        if item.new is None and item.old is None:
            return ""
        raw = item.old if which == "old" else item.new
        if raw is None:
            return "—"
        if item.unit == "count":
            return f"{int(round(raw)):,}"
        return f"{raw:.{item.digits}f}"
    return one("old"), one("new")


def match_tokens(items: list[RegItem], entries: list[Entry]) -> list[dict]:
    """Match each manuscript numeric token to a registry item.

    Strategy: build a lookup of every (normalised old/new string) -> item,
    then for each token compare its normalised form. Where several registry
    items share a printed value the row is reported with all candidates and the
    decision is deferred to the per-location checks in section WP7.4 of the plan.
    """
    lookup: dict[str, list[RegItem]] = {}
    for it in items:
        for which in ("old", "new"):
            raw = it.old if which == "old" else it.new
            if raw is None:
                continue
            if it.unit == "count":
                s = f"{int(round(raw)):,}"
                lookup.setdefault(s, []).append(it)
                lookup.setdefault(str(int(round(raw))), []).append(it)
            else:
                s = f"{raw:.{it.digits}f}"
                lookup.setdefault(s, []).append(it)
                # also allow the integer-rounded variant of the same quantity
                lookup.setdefault(f"{raw:.0f}", []).append(it)

    out = []
    for e in entries:
        for tok, a, b in numeric_tokens(e.text):
            nt = norm_token(tok)
            cands = lookup.get(nt, [])
            uniq = []
            for c in cands:
                if c.item_id not in [u.item_id for u in uniq]:
                    uniq.append(c)
            out.append({
                "entry": e, "token": tok, "start": a, "end": b,
                "context": re.sub(r"\s+", " ", e.text[max(0, a - 40):b + 40]).strip(),
                "candidates": uniq,
            })
    return out


ASSIGNMENTS: list[tuple[str, str, str]] = [
    # (entry id, exact scanned token text, registry item_id)
    # --- abstract / introduction -----------------------------------------
    ("P4", "24.2 billion", "city_eal_hist_nodef"),
    ("P4", "21.5%", "def_reduction_hist"),
    ("P4", "74%", "wind_share"),
    ("P4", "66%", "t1_red_ssp585"),
    ("P4", "40.2 billion", "city_eal_ssp585_nodef"),
    ("P4", "26%", "surge_share"),
    ("P4", "40%", "t1_red_ssp585"),
    ("P4", "52%", "cchi_ssp585_vs_terminal_pct"),
    ("P6", "63.3 trillion", "exposure_total_t"),
    ("P9", "585,033", "n_buildings"),
    ("P9", "63.3 trillion", "exposure_total_t"),
    # --- Results 1 -------------------------------------------------------
    ("P14", "24.2 billion", "city_eal_hist_nodef"),
    ("P14", "17.9 billion", "wind_eal_bn"),
    ("P14", "74%", "wind_share"),
    ("P14", "6.2 billion", "surge_eal_bn"),
    ("P14", "26%", "surge_share"),
    ("P14", "19.0 billion", "city_eal_hist_def"),
    ("P14", "21.5%", "def_reduction_hist"),
    ("P16", "33.3 billion", "city_eal_ssp245_nodef"),
    ("P16", "+38%", "eal_incr_ssp245"),
    ("P16", "40.2 billion", "city_eal_ssp585_nodef"),
    ("P16", "+66%", "eal_incr_ssp585"),
    ("P16", "6.2 billion", "surge_eal_bn"),
    ("P16", "16 billion", "surge_eal_ssp585_bn"),
    ("P16", "26.5 billion", "city_eal_ssp585_def"),
    ("P16", "39.5%", "residual_above_hist_nodef_pct"),
    ("P17", "0.9999", "tc_calibration_ratio"),
    ("P17", "1,070", "synthetic_catalogue_n"),
    # --- Results 2 : spatial inequality ----------------------------------
    ("P19", "5.9 billion", "top5_eal_1_浦东新区"),
    ("P19", "0.83‰", "ratio_虹口区"),
    ("P19", "0.77‰", "ratio_杨浦区"),
    ("P19", "0.68‰", "ratio_黄浦区"),
    ("P19", "0.38‰", "city_mean_ratio"),
    ("P19", "0.40‰", "ratio_浦东新区"),
    ("P21", "5.4 billion", "ssp585_eal_杨浦区"),
    ("P21", "1.57‰", "ssp585_ratio_杨浦区"),
    ("P21", "3.5 billion", "ssp585_eal_虹口区"),
    ("P21", "1.73‰", "ssp585_ratio_虹口区"),
    # --- index results ---------------------------------------------------
    ("P41", "438.9", "cri_2023_12"),
    ("P41", "4.4", "cri_1993_fold"),
    ("P42", "599", "cri2050_p50_hist"),
    ("P42", "673", "cri2050_p50_ssp245"),
    ("P42", "742", "cri2050_p50_ssp585"),
    ("P42", "12.4%", "cri_incr_ssp245"),
    ("P42", "2%", "cri_param_band_pct"),
    ("P42", "23.9%", "cri_incr_ssp585"),
    ("P48", "231", "hsi_terminal"),
    ("P48", "254", "hsi_peak"),
    ("P49", "0.358", "cchi_target_rho"),
    ("P49", "130", "cchi_2011_12"),
    ("P49", "313", "cchi_2023_12"),
    ("P49", "399", "cchi2050_p50_hist"),
    ("P49", "439", "cchi2050_p50_ssp245"),
    ("P49", "477", "cchi2050_p50_ssp585"),
    ("P49", "52%", "cchi_ssp585_vs_terminal_pct"),
    ("P66", "−0.8%", "t8_CFCI_TARGET_RHO_BAND"),
    ("P66", "52%", "cchi_ssp585_vs_terminal_pct"),
    ("P66", "17%", "t8_HSI_WEIGHT_BAND"),
    # --- discussion / conclusion -----------------------------------------
    ("P77", "74%", "wind_share"),
    ("P77", "21.5%", "def_reduction_hist"),
    ("P77", "599", "cri2050_p50_hist"),
    ("P77", "742", "cri2050_p50_ssp585"),
    ("P77", "52%", "cchi_ssp585_vs_terminal_pct"),
    ("P79", "21.5%", "def_reduction_hist"),
    ("P79", "34.2%", "def_reduction_ssp585"),
    ("P79", "39.5%", "residual_above_hist_nodef_pct"),
    ("P79", "−23%", "t8_TC_IMPACT_V_THRESH"),
    ("P79", "+31%", "t8_TC_IMPACT_V_THRESH"),
    ("P79", "2%", "cri_param_band_pct"),
    ("P83", "74%", "wind_share"),
    ("P83", "21.5%", "def_reduction_hist"),
    ("P83", "26.5 billion", "city_eal_ssp585_def"),
    ("P83", "599", "cri2050_p50_hist"),
    ("P83", "742", "cri2050_p50_ssp585"),
    ("P83", "52%", "cchi_ssp585_vs_terminal_pct"),
    # --- Table 1 ---------------------------------------------------------
    ("T0#r1c1", "24.2", "t1_nodef_hist"),
    ("T0#r1c2", "19.0", "t1_def_hist"),
    ("T0#r1c3", "21.5%", "t1_red_hist"),
    ("T0#r2c1", "33.3", "t1_nodef_ssp245"),
    ("T0#r2c2", "23.8", "t1_def_ssp245"),
    ("T0#r2c3", "28%", "t1_red_ssp245"),
    ("T0#r3c1", "40.2", "t1_nodef_ssp585"),
    ("T0#r3c2", "26.5", "t1_def_ssp585"),
    ("T0#r3c3", "34%", "t1_red_ssp585"),
    # --- Table 2 (rows 3/4 swap: Xuhui <-> Minhang) ----------------------
    ("T1#r1c1", "5.9", "t2_r1_eal"),
    ("T1#r1c2", "14.8", "t2_r1_expo"),
    ("T1#r1c3", "0.40", "t2_r1_ratio"),
    ("T1#r2c1", "2.6", "t2_r2_eal"),
    ("T1#r2c2", "3.4", "t2_r2_expo"),
    ("T1#r2c3", "0.77", "t2_r2_ratio"),
    ("T1#r3c1", "2.3", "t2_r3_eal"),
    ("T1#r3c2", "4.1", "t2_r3_expo"),
    ("T1#r3c3", "0.56", "t2_r3_ratio"),
    ("T1#r4c1", "2.3", "t2_r4_eal"),
    ("T1#r4c2", "8.0", "t2_r4_expo"),
    ("T1#r4c3", "0.28", "t2_r4_ratio"),
    ("T1#r5c1", "1.7", "t2_r5_eal"),
    ("T1#r5c2", "2.0", "t2_r5_expo"),
    ("T1#r5c3", "0.83", "t2_r5_ratio"),
    # --- Table 3 / 4 / 5 -------------------------------------------------
    ("T2#r1c1", "490", "t3_p10_hist"),
    ("T2#r1c2", "599", "t3_p50_hist"),
    ("T2#r1c3", "689", "t3_p90_hist"),
    ("T2#r2c1", "564", "t3_p10_ssp245"),
    ("T2#r2c2", "673", "t3_p50_ssp245"),
    ("T2#r2c3", "768", "t3_p90_ssp245"),
    ("T2#r3c1", "641", "t3_p10_ssp585"),
    ("T2#r3c2", "742", "t3_p50_ssp585"),
    ("T2#r3c3", "837", "t3_p90_ssp585"),
    ("T3#r1c1", "230", "t4_p10_hist"),
    ("T3#r1c2", "265", "t4_p50_hist"),
    ("T3#r1c3", "329", "t4_p90_hist"),
    ("T3#r2c1", "251", "t4_p10_ssp245"),
    ("T3#r2c2", "287", "t4_p50_ssp245"),
    ("T3#r2c3", "354", "t4_p90_ssp245"),
    ("T3#r3c1", "270", "t4_p10_ssp585"),
    ("T3#r3c2", "307", "t4_p50_ssp585"),
    ("T3#r3c3", "375", "t4_p90_ssp585"),
    ("T4#r1c1", "351", "t5_p10_hist"),
    ("T4#r1c2", "399", "t5_p50_hist"),
    ("T4#r1c3", "456", "t5_p90_hist"),
    ("T4#r2c1", "395", "t5_p10_ssp245"),
    ("T4#r2c2", "439", "t5_p50_ssp245"),
    ("T4#r2c3", "498", "t5_p90_ssp245"),
    ("T4#r3c1", "435", "t5_p10_ssp585"),
    ("T4#r3c2", "477", "t5_p50_ssp585"),
    ("T4#r3c3", "533", "t5_p90_ssp585"),
]

# Non-numeric edits that WP7.2 must still make. They are text-only, so the
# numeric scanner cannot see them; they are listed explicitly so the rewrite
# checklist is complete. WP7.5 asserts them separately.
TEXT_EDITS: list[tuple[str, str, str]] = [
    # (entry id, what changes, note)
    ("T1#r3c0", "标签 Xuhui → Minhang",
     "Table 2 第 3/4 名换位：稿件第 3 行标签原为 Xuhui，A 口径该位是 Minhang"),
    ("T1#r4c0", "标签 Minhang → Xuhui",
     "Table 2 第 3/4 名换位：稿件第 4 行标签原为 Minhang，A 口径该位是 Xuhui"),
    ("P24", "图注 `Pudong, Yangpu, and Xuhui` → `Minhang`",
     "图注 Top3 写错；A 口径前三位为 Pudong / Yangpu / Minhang"),
    ("T8#r8c0", "` adj. B_old` → `$V_{half}$ adj. B_old`",
     "T8 第 8/9/10/11 行与第 13/14 行的 $V_{half}$/α/κ 符号在提取中缺失，属公式损坏"),
    ("P194", "`Lianjia (Beike)` → `Anjuke`",
     "3000/3000 行 xiaoquurl 指向 shanghai.anjuke.com（安居客）"),
    ("P204", "`Lianjia (Beike)` → `Anjuke`", "同上"),
    ("T10", "第 8/11 行文件名修正",
     "→ fi_01_finance_risk_index.png / fi_04_fri_vs_cri_overlay.png"),
]

WHITELIST_NOTE = {
    "P59": "含 m:oMath（HP 趋势公式），禁止整段替换；只改数字 run",
    "P62": "含 m:oMath（ρ 标记），禁止整段替换；只改数字 run",
    "P252": "含 m:oMath（耦合符号），禁止整段替换；只改数字 run",
    "P253": "DA 正文，含方括号占位符，WP8 改",
}


def build_sec26_rows(items) -> tuple[list[dict], list[str]]:
    """The gate's frozen item set, each with its OLD/NEW and a verdict."""
    INVARIANT_IDS = {"n_buildings", "n_districts"}
    by_id = {it.item_id: it for it in items}
    rows: list[dict] = []
    missing: list[str] = []
    for iid in SEC26_IDS:
        it = by_id.get(iid)
        if it is None:
            missing.append(iid)
            continue
        old_s, new_s = fmt_old_new(it)
        if iid in INVARIANT_IDS:
            # building count / district count are structural invariants: they are
            # the same under every boundary layer and are asserted as such.
            verdict = "same (invariant)"
        elif it.new is None:
            verdict = "watch"
        else:
            verdict = "CHANGE" if old_s != new_s else "same"
        delta = ""
        if it.old not in (None, 0) and it.new is not None:
            delta = f"{(it.new - it.old) / abs(it.old) * 100:+.3f}%"
        rows.append({
            "item_id": iid, "section": it.section, "label": it.label,
            "old": old_s, "new": new_s, "delta": delta, "verdict": verdict,
            "digits": it.digits, "unit": it.unit,
            "note": it.note,
        })
    return rows, missing


def write_sec26(rows: list[dict], path: Path) -> tuple[int, int]:
    lines = ["item_id,section,label,OLD,NEW,delta_pct,verdict,digits,unit,note"]
    for r in rows:
        def q(s: str) -> str:
            s = (s or "").replace('"', '""')
            return f'"{s}"' if any(c in s for c in ',"') else s
        lines.append(",".join([q(r["item_id"]), q(r["section"]), q(r["label"]),
                               q(r["old"]), q(r["new"]), q(r["delta"]),
                               q(r["verdict"]), str(r["digits"]), q(r["unit"]),
                               q(r.get("note", ""))]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    n_change = sum(1 for r in rows if r["verdict"] == "CHANGE")
    return n_change, len(rows)


def write_inventory(entries: list[Entry], tokens: list[dict], out_csv: Path) -> None:
    by_entry: dict[str, list[dict]] = {}
    for t in tokens:
        by_entry.setdefault(t["entry"].ident, []).append(t)
    lines = ["ID,kind,style,has_math,token_idx,token,context"]
    for e in entries:
        toks = by_entry.get(e.ident, [])
        if not toks:
            lines.append(",".join([
                e.ident, e.kind, e.style, str(e.has_math), "", "", ""]))
            continue
        for i, t in enumerate(toks, start=1):
            ctx = t["context"].replace('"', '""')
            lines.append(",".join([
                e.ident, e.kind, e.style, str(e.has_math), str(i),
                t["token"], f'"{ctx}"']))
    out_csv.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_old_side(out: dict, frozen: dict) -> list[str]:
    """Recompute every frozen section 2.6 quantity from a run's outputs and
    assert it reproduces the frozen constants at the manuscript's precision.

    Used in `--verify-old` mode against the WP4 legacy-layer archive: if the
    convention and the frozen constants agree there, the same code path is
    trustworthy for the NEW column produced from the A archive.
    """
    warn: list[str] = []
    city = out["city"]
    hist = out["hist_districts"]

    def close(name: str, got: float, want: float, digits: int) -> None:
        if round(float(got), digits) != round(float(want), digits):
            warn.append(f"{name}: got {got!r} want {want!r} at {digits} dp")

    for (scen, prof), want in frozen["city_eal_bn"].items():
        pfull = "baseline_nodef" if prof == "nodef" else "current_def_gap"
        close(f"city EAL {scen}/{prof}", city[(SCEN[scen], pfull)]["EAL_compound"] / 1e9,
              want, 3)
    for scen, want in frozen["defense_reduction_pct"].items():
        n = city[(SCEN[scen], "baseline_nodef")]["EAL_compound"]
        d = city[(SCEN[scen], "current_def_gap")]["EAL_compound"]
        close(f"defense reduction {scen}", (1 - d / n) * 100, want, 2)
    w = city[("historical", "baseline_nodef")]["EAL_wind"]
    s = city[("historical", "baseline_nodef")]["EAL_surge"]
    close("wind share", w / (w + s) * 100, frozen["wind_share_pct"], 2)
    close("surge share", s / (w + s) * 100, frozen["surge_share_pct"], 2)
    expo = sum(fnum(r, "exposure_total") for r in hist) / 1e12
    close("exposure total", expo, frozen["exposure_total_t"], 4)
    got_top5 = [(r["district"], fnum(r, "EAL_compound") / 1e9) for r in hist[:5]]
    if [d for d, _ in got_top5] != [d for d, _ in frozen["top5_eal_bn"]]:
        warn.append(f"Top5 order: got {[d for d, _ in got_top5]} "
                    f"want {[d for d, _ in frozen['top5_eal_bn']]}")
    for (d, want), (gd, got) in zip(frozen["top5_eal_bn"], got_top5):
        close(f"Top5 EAL {d}", got, want, 4)
    for d, want in frozen["district_ratio_permille"]:
        row = next((r for r in hist if r["district"] == d), None)
        if row is None:
            warn.append(f"district missing: {d}")
            continue
        close(f"ratio {d}", fnum(row, "EAL_ratio_pct") * 10, want, 4)

    cri_hist = out["tables"]["cri_hist"]
    close("CRI 2023-12", next(fnum(r, "cri_index") for r in cri_hist
                              if r["date"] == "2023-12-01"), frozen["cri_2023_12"], 4)
    cri = out["tables"]["cri"]
    for scen, w50, w10, w90 in frozen["cri_2050"]:
        r = row_at(cri, IDX[scen], "2050-12-01")
        close(f"CRI2050 p50 {scen}", fnum(r, "cri_index_p50"), w50, 3)
        close(f"CRI2050 p10 {scen}", fnum(r, "cri_index_p10"), w10, 2)
        close(f"CRI2050 p90 {scen}", fnum(r, "cri_index_p90"), w90, 2)
    hsi_hist = out["tables"]["hsi_hist"]
    indexed = [r for r in hsi_hist if r.get("fri_index") not in ("", None)]
    close("HSI terminal", fnum(indexed[-1], "fri_index"), frozen["hsi_terminal"], 2)
    close("HSI peak", fnum(max(indexed, key=lambda r: fnum(r, "fri_index")), "fri_index"),
          frozen["hsi_peak"], 2)
    hsi_proj = out["tables"]["hsi_proj"]
    for scen, w50, w10, w90 in frozen["hsi_2050"]:
        r = row_at(hsi_proj, IDX[scen], "2050-12-01")
        close(f"HSI2050 p50 {scen}", fnum(r, "fri_index_p50"), w50, 3)
        close(f"HSI2050 p10 {scen}", fnum(r, "fri_index_p10"), w10, 2)
        close(f"HSI2050 p90 {scen}", fnum(r, "fri_index_p90"), w90, 2)
    close("CCHI 2011-12", fnum(cri_hist[0], "cfci"), frozen["cchi_2011_12"], 3)
    close("CCHI 2023-12", fnum(cri_hist[-1], "cfci"), frozen["cchi_2023_12"], 3)
    cci_proj = out["tables"]["cci_proj"]
    for scen, w50, w10, w90 in frozen["cchi_2050"]:
        r = row_at(cci_proj, IDX[scen], "2050-12-01")
        close(f"CCHI2050 p50 {scen}", fnum(r, "cfci_p50"), w50, 3)
        close(f"CCHI2050 p10 {scen}", fnum(r, "cfci_p10"), w10, 2)
        close(f"CCHI2050 p90 {scen}", fnum(r, "cfci_p90"), w90, 2)
    return warn


def verify_old_pipeline(archive: Path, frozen: dict) -> int:
    """`--verify-old ARCHIVE`: prove the frozen section 2.6 constants are the
    legacy-layer baseline this tool's convention reproduces."""
    print("=" * 78)
    print(f"OLD-side reproduction check against {archive.name}")
    print("=" * 78)
    if not archive.exists():
        print(f"MISSING: {archive}")
        return 1
    out = load_outputs(archive)
    warn = check_old_side(out, frozen)
    total = 6 + 3 + 2 + 1 + 5 + 6 + 1 + 9 + 9 + 9 + 2
    if warn:
        print(f"FAIL ({len(warn)} mismatches)")
        for w in warn:
            print(f"  - {w}")
        return 1
    print(f"PASS: every section 2.6 frozen value is reproduced "
          f"({total} quantities, manuscript precision)")
    return 0


def build_change_rows(items, entries, tokens, strict=False):
    """Return (matched rows, unmapped token rows, integrity issues)."""
    by_id = {it.item_id: it for it in items}
    ent_by_id = {e.ident: e for e in entries}
    tok_map: dict[tuple[str, str], dict] = {}
    for t in tokens:
        key = (t["entry"].ident, t["token"])
        tok_map.setdefault(key, t)

    rows = []
    problems = []
    for loc, tok, item_id in ASSIGNMENTS:
        it = by_id.get(item_id)
        if it is None:
            problems.append(f"assignment references unknown registry item {item_id} ({loc} {tok})")
            continue
        e = ent_by_id.get(loc)
        if e is None:
            problems.append(f"assignment references unknown entry {loc}")
            continue
        if tok not in e.text:
            problems.append(f"{loc}: assigned token {tok!r} not present in entry text")
            continue
        if (loc, tok) not in tok_map:
            problems.append(f"{loc}: token {tok!r} not produced by the token scanner")
            continue
        old_s, new_s = fmt_old_new(it)
        changed = (it.old is not None and it.new is not None and old_s != new_s)
        if it.status == "pending WP6" or it.section.startswith("Table 8"):
            status = "pending WP6"
        elif it.old is None and it.new is None:
            status = "CHANGE" if it.note else "watch"   # label/ordering-only edits
        elif it.old is None or it.new is None:
            status = "watch"
        else:
            status = "CHANGE" if changed else "same"
        status = status_of(it)
        rows.append({
            "loc": loc, "style": e.style, "has_math": e.has_math, "token": tok,
            "section": it.section, "item_id": it.item_id, "label": it.label,
            "old": old_s, "new": new_s, "status": status,
            "old_src": it.old_src, "new_src": it.new_src, "note": it.note,
            "context": tok_map[(loc, tok)]["context"],
        })

    assigned = {(loc, tok) for loc, tok, _ in ASSIGNMENTS}
    unmapped = []
    skip_styles = {"1", "2", "3", "4"}
    for t in tokens:
        e = t["entry"]
        if (e.ident, t["token"]) in assigned:
            continue
        if e.kind == "paragraph" and e.style in skip_styles and len(e.text) < 60:
            continue
        if e.ident.startswith("P2") and len(e.text) > 200 and "http" in e.text:
            continue
        if e.kind == "table_cell" and (e.tbl_idx in (9, 10) or e.ident.startswith("P25")):
            continue
        if not t["candidates"]:
            continue
        unmapped.append({
            "loc": e.ident, "token": t["token"], "context": t["context"],
            "candidates": " | ".join(sorted({f"{c.section}/{c.item_id}"
                                             for c in t["candidates"]})),
        })
    return rows, unmapped, problems


def write_new_values(items, t8_rows, out_csv: Path) -> None:
    lines = ["section,item_id,label,OLD,OLD_source,NEW,NEW_source,digits,unit,status,note"]
    for it in items + t8_rows:
        old_s, new_s = fmt_old_new(it)
        def q(s: str) -> str:
            s = (s or "").replace('"', '""')
            return f'"{s}"' if any(c in s for c in ',"') else s
        lines.append(",".join([
            q(it.section), q(it.item_id), q(it.label), q(old_s), q(it.old_src),
            q(new_s), q(it.new_src), str(it.digits), q(it.unit),
            q(it.status), q(it.note)]))
    out_csv.write_text("\n".join(lines) + "\n", encoding="utf-8")


def status_of(item: RegItem) -> str:
    """Single source of truth for the per-item verdict."""
    if item.status in ("CHANGE", "same", "pending WP6"):
        return item.status
    old_s, new_s = fmt_old_new(item)
    if item.old_dev is not None or item.new_dev is not None:
        if item.new_dev is None:
            return "watch"
        return "same" if item.old_dev == item.new_dev else "CHANGE"
    if item.old is None and item.new is None:
        return "CHANGE" if item.note else "watch"
    if item.old is None or item.new is None:
        return "watch"
    return "CHANGE" if old_s != new_s else "same"


def write_change_table(md: Path, rows, unmapped, problems, items, t8_rows,
                       counts, docx_path, out_root, strict, sec26_rows=None,
                       sec26_missing=None) -> None:
    n_change = sum(1 for r in rows if r["status"] == "CHANGE")
    n_same = sum(1 for r in rows if r["status"] == "same")
    n_watch = sum(1 for r in rows if r["status"] == "watch")
    sec26_rows = sec26_rows or []
    sec26_missing = sec26_missing or []
    n26_change = sum(1 for r in sec26_rows if r["verdict"] == "CHANGE")
    groups: dict[str, list[dict]] = {}
    for r in rows:
        key = r["loc"] if r["loc"].startswith("T") else "段落 " + r["loc"]
        groups.setdefault(key, []).append(r)

    L = []
    ap = L.append
    ap("# 数字变更对照表（WP7.1 产出）")
    ap("")
    ap(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    ap(f"- 底稿（只读，永不修改）：`{docx_path.name}`  {docx_path.stat().st_size:,} B")
    ap(f"- NEW 值来源：`{out_root.name}`（WP5-A 终稿口径）")
    ap(f"- OLD 值来源：`docs\\_执行方案_官方边界重跑与稿件更新_v1.md` §2.6 冻结参考值"
       f"（经 `tools\\_gate_g4.py` 的 FROZEN 常量独立复核）")
    ap(f"- 口径：`tools\\audit_manuscript_consistency.py` 的 `current_main_outputs()`")
    ap("")
    ap("## 0. 摘要")
    ap("")
    ap("| 项 | 数 |")
    ap("|---|---:|")
    ap(f"| 稿件条目（段 + 表格单元） | {counts['paragraphs'] + counts['table_cells']} |")
    ap(f"| 其中表格单元 | {counts['table_cells']} |")
    ap(f"| 段落 | {counts['paragraphs']} |")
    ap(f"| 表格 | {counts['tables']} |")
    ap(f"| `m:oMath` / `m:oMathPara` / `w:drawing` | {counts['m_oMath']} / {counts['m_oMathPara']} / {counts['w_drawing']} |")
    ap(f"| 含公式条目（span/m`oMath`，**禁整段替换**） | {counts.get('math_entries', 0)} |")
    ap(f"| 　其中表格单元 | {counts.get('math_cells', 0)} |")
    ap(f"| 　其中正文段落 | {counts.get('math_paras', 0)} |")
    ap(f"| **文字层为空的含公式条目（替换即丢公式）** | {counts.get('blank_math', 0)} |")
    ap(f"| 数值 token 总数 | {counts['tokens']} |")
    ap(f"| 对照表条目（已定位） | {len(rows)} |")
    ap(f"| 其中 **数值变化** | **{n_change}** |")
    ap(f"| 其中数值不变 | {n_same} |")
    ap(f"| 待人工判读（旧/新缺一侧） | {n_watch} |")
    n_t8 = len(t8_rows)
    n_t8_pending = sum(1 for r in t8_rows if status_of(r) == "pending WP6")
    ap(f"| Table 8 参数行 | {n_t8} |")
    ap(f"| 　其中已由 WP6 实测填充 | **{n_t8 - n_t8_pending}** |")
    if n_t8_pending:
        ap(f"| 　其中仍 `pending WP6` | {n_t8_pending} |")
    ap(f"| 未定位但可自动候选的 token | {len(unmapped)} |")
    ap(f"| 登记一致性告警 | {len(problems)} |")
    ap("")
    ap(f"### 0.1 冻结参考值（= `_gate_g4.py` 的判据集）在 A 口径下的变化："
       f"**{n26_change}/{len(sec26_rows)}**")
    ap("")
    if sec26_missing:
        ap(f"> ⚠️ 以下冻结项未在登记表中找到：{sec26_missing}")
        ap("")
    ap("| 项 | OLD | NEW | 变化 |")
    ap("|---|---:|---:|---|")
    for r in sec26_rows:
        ap(f"| {r['item_id']} | {r['old'] or '—'} | {r['new'] or '—'} | "
           f"{r['verdict']}{(' ' + r['delta']) if r['delta'] else ''} |")
    ap("")
    ap(f"> G4 报告（label = `WP5-official-A`）显示 `12/60 项一致`；本表按判据集"
       f"逐项复算得到 {n26_change}/{len(sec26_rows)} 项改变，二者互为交叉校验。")
    ap("")
    ap("> **用法**：WP7.2 改稿时按本表 `CHANGE` 行逐条替换；`same` 行不动；")
    ap("> `pending WP6` 行必须等 WP6 灵敏度重跑结束后再填；`watch` 行需人工确认。")
    ap("")
    if problems:
        ap("## 0.1 登记一致性告警（必须先解决）")
        ap("")
        for p in problems:
            ap(f"- ⚠️ {p}")
        ap("")

    ap("## 1. 逐位置对照")
    ap("")
    for key in sorted(groups, key=lambda k: (k[0] != "P", int(re.sub(r"\D", "", k.split()[-1]) or 0))):
        ap(f"### {key}")
        g0 = groups[key][0]
        tags = []
        if g0["has_math"]:
            tags.append("**含 m:oMath → 禁止整段替换，只改数字 run**")
        ap(f"- 样式 `{g0['style']}`　{'　'.join(tags) if tags else ''}".rstrip())
        ap("")
        ap("| token | OLD | NEW | 状态 | 量 | NEW 出处 |")
        ap("|---|---:|---:|---|---|---|")
        for r in groups[key]:
            nw = r["new_src"].split("/")[-1] if r["new_src"] else "—"
            ap(f"| `{r['token']}` | {r['old'] or '—'} | {r['new'] or '—'} | {r['status']} | "
               f"{r['section']} · {r['label']} | {nw} |")
        ap("")

    ap("## 2. Table 8（17 个参数行）— WP6 已实测填充")
    ap("")
    if AUTHOR_RULINGS or AUTHOR_KEEP:
        ap("### 2.0 ★ 作者已裁定的单元格（照此执行，不要再讨论）")
        ap("")
        ap("| item_id | 裁定 |")
        ap("|---|---|")
        for k, v in AUTHOR_RULINGS.items():
            ap(f"| `{k}` | ✅ **{v}** |")
        for k, v in AUTHOR_KEEP.items():
            ap(f"| `{k}` | ⏸ {v} |")
        ap("")
    ap("| # | 参数 | Baseline OLD → NEW | Range OLD → NEW | Max dev OLD → NEW | 需改的列 |")
    ap("|---:|---|---|---|---|---|")
    for i, it in enumerate(t8_rows, start=1):
        cols = []
        if it.base_chg:
            cols.append("baseline")
        if it.range_chg:
            cols.append("range")
        if it.dev_chg:
            cols.append("**max-dev**")
        flag = " / ".join(cols) if cols else "—"
        if it.item_id in AUTHOR_RULINGS:
            flag += " ★已裁定"
        elif it.item_id in AUTHOR_KEEP:
            flag += " ⏸保留原值"

        def cell(old: str | None, new: str | None, changed: bool | None) -> str:
            o, n = old or "—", new or "—"
            return f"**{o} → {n}**" if changed else f"{o} → {n}" if new else o

        ap(f"| {i} | {it.label} | "
           f"{cell(it.old_base, it.new_base, it.base_chg)} | "
           f"{cell(it.old_range, it.new_range, it.range_chg)} | "
           f"{cell(it.old_dev, it.new_dev, it.dev_chg)} | {flag} |")
    ap("")
    ap("> **执行时以 `docs\\_Table8_WP6重算.md` 为准**：那里有 baseline/range/max-dev 三列的")
    ap("> 逐行 OLD→NEW、可直接粘贴的 LaTeX 行、以及 Max deviation 的四种候选格式。")
    ap("")
    ap("> **重要（防止误改）**：17 个参数行里 **baseline 只改 3 行、range 改 10 行、")
    ap("> max-dev 只有 4 行是真实数值变化**。上表「需改的列」精确到列，")
    ap("> **不在该列里的单元格不要动**。Max deviation 对格式极敏感（边界切换只让 CRI 动 ~0.3%），")
    ap("> 机械重写会把纯排版差异当成数值更新。")
    ap("")
    ap("> **已裁定的两格照改**：`Volatility window` 与 `CFCI target ρ` 的 max-dev（★）。")
    ap("> **`V_HALF$ adj. C` 保留稿件 `0%`（⏸，裁定未表态，数值等价）。**")
    ap("")

    ap("## 2.5 非数字改写项（`TEXT_EDITS`，WP7.5 单独断言）")
    ap("")
    ap("| 位置 | 改动 | 理由 |")
    ap("|---|---|---|")
    for loc, what, why in TEXT_EDITS:
        ap(f"| {loc} | {what} | {why} |")
    ap("")

    ap("## 3. 未定位但可自动候选的 token（人工判读）")
    ap("")
    if not unmapped:
        ap("_无_")
    else:
        ap("| 位置 | token | 上下文 | 候选登记项 |")
        ap("|---|---|---|---|")
        for u in unmapped[:400]:
            ctx = u["context"].replace("|", "\\|")
            ap(f"| {u['loc']} | `{u['token']}` | {ctx} | {u['candidates']} |")
        if len(unmapped) > 400:
            ap(f"| … | … | 另有 {len(unmapped) - 400} 条见 `docs\\_数值清单.csv` | |")
    ap("")

    ap("## 4. 全量登记项（OLD vs NEW，含未上稿的量）")
    ap("")
    ap("| 分区 | item_id | 量 | OLD | NEW | 变化 | 位数 | 单位 | 备注 |")
    ap("|---|---|---|---:|---:|---|---:|---|---|")
    for it in items:
        old_s, new_s = fmt_old_new(it)
        delta = ""
        if it.old is not None and it.new is not None and it.old != 0:
            delta = f"{(it.new - it.old) / abs(it.old) * 100:+.3f}%"
        if it.old is None and it.new is None:
            mark = "**改写**" if it.note else "—"
            delta = ""
        else:
            mark = "" if old_s == new_s else "**改**"
        note = (it.note or "").replace("|", "\\|")
        ap(f"| {it.section} | `{it.item_id}` | {it.label} | {old_s or '—'} | {new_s or '—'} | "
           f"{mark}{delta} | {it.digits} | {it.unit} | {note} |")
    ap("")

    ap("## 5. 结构不变量（WP7.5 改完必须复核）")
    ap("")
    ap("| 量 | 底稿实测 | 方案要求 |")
    ap("|---|---:|---:|")
    ap(f"| 段落 | {counts['paragraphs']} | 409 |")
    ap(f"| 表格 | {counts['tables']} | 11 |")
    ap(f"| `m:oMath` | {counts['m_oMath']} | 131 |")
    ap(f"| `m:oMathPara` | {counts['m_oMathPara']} | 41 |")
    ap(f"| `w:drawing` | {counts['w_drawing']} | 37 |")
    ap("")
    if counts["paragraphs"] != 409 or counts["tables"] != 11 or counts["m_oMath"] != 131 \
            or counts["w_drawing"] != 37:
        ap("> ⚠️ 底稿计数与方案不一致，WP7.5 不变量需按**实测值**设定。")
        ap("")

    md.write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docx", default=str(DOCX_DEFAULT))
    ap.add_argument("--archive", default=str(A_ARCHIVE_DEFAULT))
    ap.add_argument("--out-dir", default=str(DOCS))
    ap.add_argument("--old-only", action="store_true",
                    help="do not read the A baseline (OLD side only)")
    ap.add_argument("--verify-old", default="",
                    help="run the section 2.6 reproduction check against this "
                         "archive (the WP4 legacy-layer baseline) and exit")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any registry/inventory integrity warning fires")
    ap.add_argument("--table8-csv", default="",
                    help="docs/_Table8_WP6重算.csv produced by wp6_table8_recompute.py; "
                         "when absent the Table 8 rows stay 'pending WP6'")
    args = ap.parse_args()

    frozen, _scen = load_frozen_old()
    if args.verify_old:
        return verify_old_pipeline(Path(args.verify_old), frozen)

    docx_path = Path(args.docx)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    inv_csv = out_dir / OUT_INVENTORY.name
    new_csv = out_dir / OUT_NEWVALUES.name
    md_path = out_dir / OUT_TABLE.name

    if len(SEC26_IDS) != SEC26_GATE_TOTAL:
        raise SystemExit(f"SEC26_IDS must hold exactly the gate's "
                         f"{SEC26_GATE_TOTAL} items, found {len(SEC26_IDS)}")
    if len(set(SEC26_IDS)) != len(SEC26_IDS):
        dupes = sorted({i for i in SEC26_IDS if SEC26_IDS.count(i) > 1})
        raise SystemExit(f"SEC26_IDS has duplicates: {dupes}")

    print("=" * 78)
    print("WP7.1 · manuscript number extractor")
    print("=" * 78)
    if not docx_path.exists():
        raise SystemExit(f"manuscript docx not found: {docx_path}")
    print(f"docx      : {docx_path}")
    print(f"size      : {docx_path.stat().st_size:,} B")

    entries, counts = read_docx_stdlib(docx_path)
    counts["table_cells"] = sum(1 for e in entries if e.kind == "table_cell")
    counts["math_entries"] = sum(1 for e in entries if e.has_math)
    counts["math_cells"] = sum(1 for e in entries if e.has_math and e.kind == "table_cell")
    counts["math_paras"] = sum(1 for e in entries if e.has_math and e.kind == "paragraph")
    counts["blank_math"] = sum(1 for e in entries if e.has_math and not e.text.strip())
    xcheck = read_docx_pydocx(docx_path)
    print(f"paragraphs: {counts['paragraphs']}  tables: {counts['tables']}  "
          f"cells: {counts['table_cells']}")
    print(f"m:oMath   : {counts['m_oMath']}  m:oMathPara: {counts['m_oMathPara']}  "
          f"w:drawing: {counts['w_drawing']}")
    if xcheck is not None:
        agree = all(xcheck[k] == counts[k] for k in
                    ("paragraphs", "tables", "m_oMath", "m_oMathPara", "w_drawing"))
        print(f"python-docx cross-check: {'AGREE' if agree else 'DISAGREE'}  {xcheck}")
        if not agree:
            print("  (python-docx counts body paragraphs only; mismatch is expected "
                  "for 'paragraphs' if any paragraph lives inside a text box)")

    tokens = match_tokens([], entries)
    counts["tokens"] = len(tokens)
    print(f"numeric tokens: {counts['tokens']}")

    frozen, _scen = load_frozen_old()
    t8_spec = load_table8_spec()
    t8_csv = Path(args.table8_csv) if args.table8_csv else (DOCS / "_Table8_WP6重算.csv")
    t8_rows = build_table8_rows(t8_spec, NEWROOT / "_sensitivity_results",
                                t8_csv if t8_csv.exists() else None)
    n_t8_resolved = sum(1 for r in t8_rows if r.status != "pending WP6")
    print(f"Table 8 rows: {len(t8_rows)}  ({n_t8_resolved} resolved from {t8_csv.name}"
          f"{'' if t8_csv.exists() else ' [missing -> pending WP6]'})")

    out_root = Path(args.archive)
    old_only = bool(args.old_only)
    if old_only or not out_root.exists():
        if not old_only:
            print(f"A archive missing ({out_root}) -> OLD side only")
        items = []
        old_only = True
        print("OLD-only mode: the NEW column and the location mapping are skipped")
    else:
        out = load_outputs(out_root)
        items = build_registry(out, frozen)
        print(f"registry items: {len(items)}   source: {out_root.name}")

    if old_only:
        # No registry => no OLD/NEW mapping. Emit the token inventory only; the
        # location table would be 126 bogus "unknown registry item" rows.
        rows, unmapped, problems = [], [], []
        counts["tokens"] = len(tokens)
        write_inventory(entries, tokens, inv_csv)
        print()
        print(f"numeric tokens: {counts['tokens']}")
        print(f"wrote {inv_csv}")
        print("skipped: _NEW值_供改写.csv and _数字变更对照表.md (no registry)")
        return 0

    rows, unmapped, problems = build_change_rows(items, entries, tokens, args.strict)
    sec26_rows: list[dict] = []
    sec26_missing: list[str] = []
    if items:
        sec26_rows, sec26_missing = build_sec26_rows(items)
        _, n26 = write_sec26(sec26_rows, out_dir / OUT_SEC26.name)
        n26_change = sum(1 for r in sec26_rows if r["verdict"] == "CHANGE")
        print(f"section 2.6 frozen items : {n26_change}/{n26} changed")
        if sec26_missing:
            print(f"  MISSING from registry: {sec26_missing}")
    write_inventory(entries, tokens, inv_csv)
    write_new_values(items, t8_rows, new_csv)
    write_change_table(md_path, rows, unmapped, problems, items, t8_rows,
                       counts, docx_path, out_root, args.strict,
                       sec26_rows, sec26_missing)

    n_change = sum(1 for r in rows if r["status"] == "CHANGE")
    print()
    print(f"located comparison rows : {len(rows)}  (CHANGE {n_change})")
    print(f"unmapped candidate tokens: {len(unmapped)}")
    print(f"integrity warnings       : {len(problems)}")
    for p in problems:
        print(f"  - {p}")
    print()
    print(f"wrote {inv_csv}")
    print(f"wrote {new_csv}")
    print(f"wrote {md_path}")
    if problems and args.strict:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
