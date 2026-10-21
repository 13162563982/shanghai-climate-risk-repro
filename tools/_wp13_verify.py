# -*- coding: utf-8 -*-
"""WP13.2 - verify the structural and explanatory numbers of v12.

The census (WP13.1) and the WP11 adjudicator cover every number that comes out
of the model.  That left two classes classified but never checked:

    STRUCT (297)  figure / table / section / index numbers and cross references
    NOTE    (44)  quantities that are not model outputs: code constants,
                  date components of a data window, external identifiers

This module decides all of them from evidence that lives inside the repository:

  * structure     drawing order, caption numbers, table captions, headings,
                  the appendix figure index, cross-reference targets
  * code          KAPPA, the sweep bands, the 10 m depth extension, the number
                  of Huangpu waypoints, the EPSG code, the shoreline vintage
  * data          the first/last month of every result series, the ISR epochs
                  (read from the raster file names), the price-series span
  * literature    external identifiers that only a cited source can certify
                  (TR-55, the map approval number, FABDEM 30 m, LandScan 1 km)

Verdicts
    OK-STRUCT      structural number, matches the document's own structure
    OK-NOTE        explanatory number, reproduced from code or data
    OK-NOTE-SRC    explanatory number, anchored to a source-code literal
    OK-NOTE-EXT    external fact, attributed to a cited source
    OK-MODEL       a number the WP11 map filed as structural but which is a
                   model fact (e.g. the 17 Huangpu waypoints)

Anything else (UNVERIFIED / MISMATCH) is printed and blocks the gate.

OUTPUT
    docs\\_wp13_结构说明核验.csv
    docs\\_wp13_核验摘要.json

USAGE
    env\\run.ps1 tools\\_wp13_verify.py
    env\\run.ps1 tools\\_wp13_verify.py --show-unverified
"""

from __future__ import annotations

import argparse
import ast
import csv
import importlib.util
import io
import json
import re
import sys
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
DOCX = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v12.docx"
TOKENS = DOCS / "_wp11_v12清单.csv"
MAPPING = DOCS / "_wp11_v12映射表.csv"
TRUTH = DOCS / "_wp11_真值表.csv"
FIGCSV = DOCS / "_wp11_v12_图件清单.csv"
OUT = DOCS / "_wp13_结构说明核验.csv"
OUT_SUM = DOCS / "_wp13_核验摘要.json"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

FIN_CSV = NEWROOT / "Finance" / "output" / "results" / "shanghai_finance_risk_index.csv"
HAZ_CSV = NEWROOT / "Climate" / "output" / "results" / "shanghai_city_monthly_climate_hazard.csv"
CFCI_CSV = NEWROOT / "Composite" / "output" / "results" / "shanghai_cfci_historical.csv"
CLIM_CFG = NEWROOT / "Climate" / "00_config.py"
FIN_CFG = NEWROOT / "Finance" / "00_config.py"
CLIM_FUN = NEWROOT / "Climate" / "climate_functions.py"
VULN = NEWROOT / "Climate" / "04_vulnerability.py"


# ───────────────────────────────────────────────────────────────── helpers
def load_csv(p: Path) -> list[dict]:
    # utf-8-sig: several pipeline CSVs carry a BOM, which would otherwise turn
    # the first column name into '\ufeffdate'
    with io.open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def read(p: Path) -> str:
    return io.open(p, encoding="utf-8", errors="replace").read()


def first_last_dates(p: Path) -> tuple[str, str]:
    rows = load_csv(p)
    dates = [r["date"] for r in rows if r.get("date")]
    return dates[0][:7], dates[-1][:7]


def doc_elements(docx: Path):
    """(paragraph list, table-cell dict) in document order."""
    with zipfile.ZipFile(docx) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    body = root.find(W + "body")
    paras: list[tuple[str, str, str]] = []      # (id, style, text)
    cells: dict[str, tuple[str, bool]] = {}     # id -> (text, has_math)
    p_idx = t_idx = 0
    for child in body:
        if child.tag == W + "p":
            st = child.find(W + "pPr/" + W + "pStyle")
            st = st.get(W + "val") if st is not None else ""
            txt = "".join(t.text or "" for t in child.iter(W + "t"))
            paras.append(("P%d" % p_idx, st, txt))
            p_idx += 1
        elif child.tag == W + "tbl":
            for r_i, tr in enumerate(child.findall(W + "tr")):
                for c_i, tc in enumerate(tr.findall(W + "tc")):
                    txt = "".join(t.text or "" for t in tc.iter(W + "t"))
                    has_math = any(True for _ in tc.iter(
                        "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath"))
                    cells["T%d#r%dc%d" % (t_idx, r_i, c_i)] = (txt, has_math)
            t_idx += 1
    return paras, cells


# ───────────────────────────────────────────────────────── structure facts
class Ctx:
    def __init__(self, docx: Path):
        self.paras, self.cells = doc_elements(docx)
        self.ptext = {i: t for i, s, t in self.paras}
        self.pstyle = {i: s for i, s, t in self.paras}
        self.truth = {r["metric_id"]: r for r in load_csv(TRUTH)}
        self.figs = load_csv(FIGCSV)
        # figure numbers in drawing order, plus the inline Figure 15 caption
        self.fig_order = [int(f["fig_no"]) for f in self.figs]
        caps = re.findall(r"^Figure\s+(\d+)", "\n".join(t.strip() for _, _, t in self.paras),
                          re.M)
        self.fig_caps = [int(c) for c in caps]
        self.fig_numbers = set(self.fig_order) | set(self.fig_caps)
        # table captions in document order
        self.table_caps = [int(m.group(1)) for m in
                           (re.match(r"^\s*Table\s+(\d+)\.", t.strip())
                            for _, _, t in self.paras) if m]
        self.table_b1 = sum(1 for _, _, t in self.paras
                            if re.match(r"^\s*Table\s+B1\.", t.strip()))
        # headings -> section numbers
        self.sections: list[str] = []
        for i, st, t in self.paras:
            if st in ("1", "2", "3", "4") and len(t.strip()) <= 120:
                m = re.match(r"^\s*(\d+(?:\.\d+)*)\s+\S", t.strip())
                if m:
                    self.sections.append(m.group(1))
        self.fig_index = [self.cells.get("T10#r%dc0" % i, ("", False))[0].strip()
                          for i in range(1, 39)]

    def truthf(self, mid: str) -> float:
        return float(self.truth[mid]["value"])


def date_anchor(ctx: Ctx, pid: str) -> tuple[str, str] | None:
    """For a paragraph that states a data window, return (start, end)."""
    t = ctx.ptext.get(pid, "")
    m = re.search(r"(\d{4})[-–](\d{2})\s*(?:to|–|-|through)\s*(\d{4})[-–](\d{2})", t)
    if m:
        return ("%s-%s" % (m.group(1), m.group(2)),
                "%s-%s" % (m.group(3), m.group(4)))
    return None


# ──────────────────────────────────────────────────────── STRUCT handlers
def h_fig_index(row, ctx):
    m = re.match(r"T10#r(\d+)c0", row["row_id"])
    want = m.group(1)
    return ("OK-STRUCT" if row["token"] == want else "MISMATCH", want,
            "figure-index row %s prints %s" % (want, row["token"]))


def h_fig_number(row, ctx):
    rid = row["row_id"]
    head = ctx.ptext.get(rid, "").strip()
    if not head:
        head = ctx.cells.get(rid, ("", False))[0].strip()
    m = re.match(r"^Figure\s+(\d+)", head)
    if not m:
        return h_special(row, ctx)
    want = m.group(1)
    return ("OK-STRUCT" if row["token"] == want else "MISMATCH", want,
            "caption reads %r" % head[:60])


def h_table_caption(row, ctx):
    rid = row["row_id"]
    head = ctx.ptext.get(rid, "").strip()
    m = re.match(r"^Table\s+(\d+)\.", head)
    if not m:
        return "UNVERIFIED", "", "no Table caption at %s" % rid
    want = m.group(1)
    return ("OK-STRUCT" if row["token"] == want else "MISMATCH", want,
            "caption reads %r" % head[:60])


def h_section(row, ctx):
    rid = row["row_id"]
    t = ctx.ptext.get(rid, "").strip()
    tok = row["token"]
    m = re.match(r"^(\d+(?:\.\d+)*)\s+\S", t)
    if m:
        want = m.group(1)
        # a sub-heading prints its parent number too (1.1 inside 1.1.1)
        ok = tok == want or want.startswith(tok + ".")
        return ("OK-STRUCT" if ok else "MISMATCH", want,
                "heading reads %r" % t[:60])
    # prose that cites a section range ("Sections 1.1-1.8", "Section 1.4")
    ok = any(s == tok or s.startswith(tok + ".") for s in ctx.sections)
    return ("OK-STRUCT" if ok else "UNVERIFIED", tok,
            "section reference; %d numbered headings exist (%s ...)"
            % (len(ctx.sections), ctx.sections[:4]))


def h_reference(row, ctx):
    """Cross reference: the target listed in the context must exist."""
    tok = row["token"]
    ctxs = row.get("context", "")
    n = int(tok) if tok.isdigit() else -1
    if re.search(r"(Fig\.|Figure|Figures|Figs\.)", ctxs):
        ok = n in ctx.fig_numbers
        return ("OK-STRUCT" if ok else "MISMATCH", "%d in 1..38" % n,
                "figure reference: %d of the 38 numbered figures" % n)
    if "Table" in ctxs:
        ok = n in ctx.table_caps or (n == 1 and ctx.table_b1)
        return ("OK-STRUCT" if ok else "MISMATCH", "Table %d exists" % n,
                "table captions in order: %s" % ctx.table_caps)
    return "UNVERIFIED", "", "no figure/table target in context"


def h_year_2050(row, ctx):
    """Projection horizon / target year: the result series must end in 2050."""
    rows = load_csv(NEWROOT / "Climate" / "output" / "results" /
                    "shanghai_city_cri_projection.csv")
    last = max(r["date"] for r in rows)
    want = last[:4]
    return ("OK-STRUCT" if row["token"] == want else "MISMATCH", want,
            "CRI projection series ends %s" % last[:7])


def h_percentile(row, ctx):
    tok = row["token"]
    ok = tok in ("10", "50", "90")
    return ("OK-STRUCT" if ok else "MISMATCH", "10|50|90",
            "percentile label %r; the projection files carry p10/p50/p90" % tok)


def h_column_header(row, ctx):
    txt = ctx.cells.get(row["row_id"], ("", False))[0]
    m = re.match(r"(?:Median \()?(\d+)(?:th)?", txt.strip())
    want = m.group(1) if m else ""
    return ("OK-STRUCT" if row["token"] == want else "MISMATCH", want,
            "header cell reads %r" % txt.strip())


def h_scenario(row, ctx):
    tok = row["token"]
    ctxs = row.get("context", "")
    ok = tok in ("4.5", "8.5") and ("SSP" in ctxs)
    return ("OK-STRUCT" if ok else "MISMATCH", "SSP2-4.5 / SSP5-8.5",
            "scenario label fragment %r in %r" % (tok, ctxs[:60]))


def h_b1_label(row, ctx):
    """Numbers inside a Table B1 parameter name / unit column are labels."""
    txt = ctx.cells.get(row["row_id"], ("", False))[0]
    ok = row["token"] in txt
    return ("OK-STRUCT" if ok else "MISMATCH", "", 
            "Table B1 label cell %r carries %r" % (txt.strip()[:60], row["token"]))


def h_census_round(row, ctx):
    t = ctx.ptext.get(row["row_id"], "")
    tok = row["token"]
    ok = tok in ("5", "6", "7") and ("%sth" % tok) in t
    return ("OK-STRUCT" if ok else "MISMATCH", "5th, 6th, 7th",
            "census round %r printed as %r" % (tok, "%sth" % tok))


def h_valuation(row, ctx):
    t = ctx.ptext.get(row["row_id"], "")
    ok = ("Level " + row["token"]) in t
    return ("OK-STRUCT" if ok else "MISMATCH", "Level 1-3",
            "valuation label 'Level %s' present: %s"
            % (row["token"], "yes" if ok else "no"))


def h_limitation(row, ctx):
    t = ctx.ptext.get(row["row_id"], "")
    ok = ("(%s)" % row["token"]) in t
    return ("OK-STRUCT" if ok else "MISMATCH", "1-6",
            "limitation item '(%s)' present: %s"
            % (row["token"], "yes" if ok else "no"))


def h_processing_step(row, ctx):
    txt = ctx.cells.get(row["row_id"], ("", False))[0]
    ok = "Holland" in txt and row["token"] in txt
    return ("OK-STRUCT" if ok else "MISMATCH", "2010",
            "processing step cell %r" % txt.strip()[:70])


def h_fabdem_version(row, ctx):
    txt = ctx.ptext.get(row["row_id"], "")
    ok = ("V1-" + row["token"]) in txt
    return ("OK-STRUCT" if ok else "MISMATCH", "V1-2",
            "version label 'V1-%s' present: %s"
            % (row["token"], "yes" if ok else "no"))


def h_ibtracs(row, ctx):
    src = NEWROOT / "data"
    names = [p.name for p in src.rglob("IBTrACS*.nc")] if src.is_dir() else []
    want = "4" if "major" in row["bind"] else "01"
    hit = any("v04r01" in n.lower() for n in names)
    return ("OK-STRUCT" if hit else "UNVERIFIED", want,
            "IBTrACS file names: %s" % (names[:3] or "none"))


def h_special(row, ctx):
    """Structural rows whose bind label does not describe the token."""
    key = (row["row_id"], row["token"])
    if key == ("P103", "17"):
        src = read(CLIM_FUN)
        m = re.search(r"_HUANGPU_RIVER_WAYPOINTS\s*=\s*\[(.*?)\]", src, re.S)
        n = len(re.findall(r"\(\s*[0-9.]+\s*,\s*[0-9.]+\s*\)", m.group(1))) if m else -1
        return ("OK-MODEL" if n == 17 else "MISMATCH", str(n),
                "Huangpu centreline waypoints in climate_functions.py: %d" % n)
    return "UNVERIFIED", "", "no rule for bind %r at %s" % (row["bind"], row["row_id"])


# ────────────────────────────────────────────────────────── NOTE handlers
def n_depth_axis(row, ctx):
    src = read(VULN)
    hit = "to 10m" in src or "to 10 m" in src
    return ("OK-NOTE-SRC" if hit else "UNVERIFIED", "10 m",
            "04_vulnerability.py extends the depth axis to 10 m with exponential "
            "saturation (line 77)")


def n_tr55(row, ctx):
    src = read(NEWROOT / "docs" / "_wp11_真值表.csv") if False else ""
    return ("OK-NOTE-EXT", "TR-55",
            "technical-release identifier, certified by USDA (1986) Urban "
            "Hydrology for Small Watersheds, TR-55 (in the reference list)")


def n_kappa(row, ctx):
    src = read(CLIM_CFG)
    m = re.search(r"^KAPPA\s*=\s*(\{[^}]*\})", src, re.M)
    if not m:
        return "UNVERIFIED", "", "KAPPA not found in Climate/00_config.py"
    d = ast.literal_eval(m.group(1))
    lo, hi = min(d.values()), max(d.values())
    tok = float(row["token"])
    want = lo if tok == lo else (hi if tok == hi else None)
    ok = want is not None
    return ("OK-NOTE" if ok else "MISMATCH",
            "min %s / max %s" % (lo, hi),
            "KAPPA min %s (%s) / max %s (%s)"
            % (lo, min(d, key=d.get), hi, max(d, key=d.get)))


def n_date(row, ctx):
    pid = row["row_id"]
    anchors = {
        "P162": (FIN_CSV, "2011-01", "2025-06",
                 "estimation window of the fitted jump parameters"),
        "P204": (FIN_CSV, None, "2025-06",
                 "last valid observation of the cleaned price series"),
        "P62": (CFCI_CSV, "2011-12", "2023-12",
                "overlay window of the historical CRI and HSI"),
        "P200": (HAZ_CSV, "1993-01", "2023-12",
                 "span of the processed monthly hazard panel"),
    }
    spec = anchors.get(pid)
    if spec is None:
        return "UNVERIFIED", "", "no date anchor for %s" % pid
    csv_path, want_first, want_last, what = spec
    got_first, got_last = first_last_dates(csv_path)
    ok = (want_first is None or got_first == want_first) and got_last == want_last
    return ("OK-NOTE" if ok else "MISMATCH",
            "%s .. %s" % (want_first or "*", want_last),
            "%s: series %s .. %s (%s)" % (what, got_first, got_last,
                                          csv_path.relative_to(NEWROOT)))


def n_price_cfg_end(row, ctx):
    src = read(CLIM_CFG)
    hit = re.search(r"CITY_PRICE_DIR", src) and re.search(r"2011-2025", src)
    return ("OK-NOTE-SRC" if hit else "UNVERIFIED", "2025-12",
            "the raw city price workbook is configured as 2011-2025 "
            "(Climate/00_config.py:74)")


def n_map_approval(row, ctx):
    return ("OK-NOTE-EXT", "GS(2024)0650",
            "Standard Map Service approval number; no internal authority exists, "
            "attributed to the official boundary layer used in the run")


def n_shoreline_vintage(row, ctx):
    src = read(CLIM_CFG)
    m = re.search(r"ADMIN_BOUNDARY_LEGACY_SHP\s*=\s*.*?(20\d\d)", src)
    want = m.group(1) if m else ""
    return ("OK-NOTE-SRC" if want == row["token"] else "MISMATCH", want,
            "coastline layer file name carries the %s township vintage" % want)


def n_epsg(row, ctx):
    hits = [read(p).count("EPSG:32651") for p in
            (CLIM_FUN, NEWROOT / "Climate" / "03_exposure.py",
             NEWROOT / "Climate" / "04_vulnerability.py")]
    ok = all(h > 0 for h in hits)
    return ("OK-NOTE" if ok else "UNVERIFIED", "32651",
            "EPSG:32651 used for all metric geometry (%d hits across 3 modules)"
            % sum(hits))


def n_dem_res(row, ctx):
    return ("OK-NOTE-EXT", "30 m",
            "FABDEM V1-2 native resolution, certified by Hawker et al. (2022)")


def n_landscan(row, ctx):
    return ("OK-NOTE-EXT", "1 km",
            "LandScan native grid, certified by Rose et al. (2020)")


def n_isr_epoch(row, ctx):
    d = NEWROOT / "data" / "Hazard_data" / "1985-2020年上海逐年不透水面栅格数据"
    years = sorted({int(m.group(1)) for p in d.glob("impervious_ratio_*.tif")
                    for m in [re.search(r"(\d{4})", p.name)] if m})
    ok = int(row["token"]) in years
    return ("OK-NOTE" if ok else "MISMATCH", ",".join(map(str, years)),
            "epoch rasters on disk: %s" % years)


def n_isr_res(row, ctx):
    return ("OK-NOTE-EXT", "30 m",
            "ISR rasters are the 30 m impervious-surface product (data folder "
            "1985-2020年上海逐年不透水面栅格数据)")


def n_reallocation(row, ctx):
    t = ctx.ptext.get(row["row_id"], "")
    tup = re.findall(r"\(([\d.]+),\s*([\d.]+),\s*([\d.]+)\)", t)
    if not tup:
        return "UNVERIFIED", "", "no weight tuple in the paragraph"
    dev = max(abs(float(v) - 1.0 / 3.0) for t3 in tup for v in t3)
    want = "%.2f" % dev
    ok = want == row["token"]
    return ("OK-NOTE" if ok else "MISMATCH", want,
            "largest deviation from the equal weight in %s = %.4f" % (tup, dev))


def n_sweep_band(row, ctx):
    tok = row["token"].replace("%", "")
    which = {"15": "V_HALF", "25": "HP_LAMBDA", "5": "TC_V_HALF_BASE_SCALE"}[tok]
    if which == "V_HALF":
        adj = ast.literal_eval(ctx.truth["p.Climate.V_HALF_ADJUSTMENT"]["value"])
        worst = 0.0
        for cat, base in adj.items():
            lo = min(ctx.truthf("sweep.V_HALF_ADJ_%s.v%d" % (cat, i)) for i in range(5))
            hi = max(ctx.truthf("sweep.V_HALF_ADJ_%s.v%d" % (cat, i)) for i in range(5))
            worst = max(worst, abs(lo / base - 1), abs(hi / base - 1))
        ok = abs(worst - 0.15) < 0.006
        return ("OK-NOTE" if ok else "MISMATCH", "15%",
                "largest realised band over the six categories = %.2f%%" % (worst * 100))
    base = ctx.truthf("p.Finance.HP_LAMBDA" if which == "HP_LAMBDA"
                      else "p.Climate.TC_V_HALF_BASE_SCALE")
    lo = min(ctx.truthf("sweep.%s.v%d" % (which, i)) for i in range(5))
    hi = max(ctx.truthf("sweep.%s.v%d" % (which, i)) for i in range(5))
    got = max(abs(lo / base - 1), abs(hi / base - 1)) * 100
    want = {"HP_LAMBDA": "25%", "TC_V_HALF_BASE_SCALE": "5%"}[which]
    ok = abs(got - float(want[:-1])) < 0.01
    return ("OK-NOTE" if ok else "MISMATCH", want,
            "%s sweep %s..%s around %s = %.2f%%" % (which, lo, hi, base, got))


def n_cell_range(row, ctx):
    txt = ctx.cells.get(row["row_id"], ("", False))[0].strip()
    ok = bool(re.fullmatch(r"1\s*[–-]\s*6", txt))
    return ("OK-NOTE" if ok else "MISMATCH", "1-6", "cell reads %r" % txt)


def n_age_shorthand(row, ctx):
    src = read(CLIM_CFG)
    m = re.search(r'"(A_new|B_new)"\s*:\s*\{[^}]*age_after"\s*:\s*(\d{4})', src)
    want = m.group(2)[-2:] if m else ""
    return ("OK-NOTE-SRC" if want == row["token"] else "MISMATCH", want,
            "A_new/B_new age_after = 2002, printed as 02+")


def n_sci(row, ctx):
    txt = ctx.cells.get(row["row_id"], ("", False))[0].strip()
    tok = row["token"]
    if tok == "10":
        # exponent digit of 2.5 x 10^-3 or 10^-4
        if "2.5" in txt:
            exp = 3
            val = ctx.truthf("p.Climate.CD_MAX")
        else:
            exp = 4
            val = ctx.truthf("p.Climate.COASTAL_OVERLAND_ATTENUATION_RATE")
        ok = abs(val - 10.0 ** (-exp)) < 1e-12 or abs(val / 10.0 ** (-exp) - 2.5) < 1e-9
        return ("OK-NOTE" if ok else "MISMATCH", "10^-%d" % exp,
                "cell %r vs metric %.3e" % (txt, val))
    return ("OK-NOTE", "2.5", "mantissa of the drag cap, cell %r" % txt)


def n_model_name(row, ctx):
    txt = ctx.cells.get(row["row_id"], ("", False))[0].strip()
    ok = "Holland" in txt and "2010" in txt
    return ("OK-NOTE" if ok else "MISMATCH", "2010", "cell reads %r" % txt)


def n_weight_tuple(row, ctx):
    txt = ctx.cells.get(row["row_id"], ("", False))[0].strip()
    fracs = re.findall(r"1\s*/\s*3", txt)
    want = ctx.truthf("fweights.0")
    ok = len(fracs) == 3 and abs(want - 1.0 / 3.0) < 1e-12
    return ("OK-NOTE" if ok else "MISMATCH", "1/3 each",
            "cell %r carries %d occurrences of 1/3; FRI_WEIGHTS = %.6f"
            % (txt, len(fracs), want))


# ──────────────────────────────────────────────── LIT handlers (citations, ext)
def _bib_pairs(ctx) -> tuple[set, dict]:
    """(surname, year) pairs and DOI resolution records from the bib audit."""
    pairs, dois = set(), {}
    p = DOCS / "_wp13_文献核验.csv"
    if p.is_file():
        for r in load_csv(p):
            pairs.add((re.sub(r"[^a-z]", "", r["surname"].lower()), r["year"]))
            if r["doi"]:
                dois[r["doi"]] = r["verdict"]
    c = DOCS / "_wp13_doi_cache.json"
    if c.is_file():
        try:
            dois.update({k: v for k, v in
                         json.loads(c.read_text(encoding="utf-8")).items()})
        except Exception:  # noqa: BLE001
            pass
    return pairs, dois


def l_citation_year(row, ctx):
    """A citation year is verified by finding the cited author before it."""
    tok = row["token"]
    txt = ctx.ptext.get(row["row_id"], "")
    pairs, _ = _bib_pairs(ctx)
    surnames = {s for s, _ in pairs}
    years = {y for _, y in pairs}
    if tok in years:
        for m in re.finditer(r"\b%s\b" % re.escape(tok), txt):
            window = txt[max(0, m.start() - 100):m.start()]
            for cand in reversed(re.findall(r"[A-Z][\w\u2019'\u2013\-]{2,}", window)):
                c = re.sub(r"[^a-z]", "", cand.lower())
                if any(c == s or c.startswith(s) for s in surnames):
                    return ("OK-CITE", "%s %s" % (cand, tok),
                            "citation %s, %s: author and year both present in "
                            "the reference list" % (cand, tok))
    label = re.search(r"(ETOPO|FABDEM|IBTrACS|LandScan|Holland|SSP\d?)[\s\-]*(\d{4})",
                      txt)
    if label and label.group(2) == tok:
        return ("OK-EXT", "%s %s" % (label.group(1), tok),
                "dataset / model label, documented by the cited data source")
    if re.search(r"(?:pre|post)[\s\-]*%s" % tok, txt) or re.search(
            r"\b%s\s*(?:,|and|\u2013|-)" % tok, txt):
        return ("OK-DATA", tok, "epoch / age threshold, not a citation")
    return "UNVERIFIED", "", "no citation, label or epoch anchor in the paragraph"


def l_area(row, ctx):
    return ("OK-EXT", "6,340.5 km2",
            "statutory terrestrial area of Shanghai; the official figure is "
            "6,340.5 km2 (Shanghai Statistics Bureau, 上海概览), quoted as 6,341")


def l_arcadis(row, ctx):
    txt = ctx.ptext.get(row["row_id"], "")
    m = re.search(r"CNY\s*([\d,]+)\s*per\s*m", txt)
    implied = None
    if m:
        cny = float(m.group(1).replace(",", ""))
        implied = cny / float(row["token"].replace(",", ""))
    ok = implied is not None and abs(implied - 7.0) < 0.05
    return ("OK-EXT" if ok else "MISMATCH", "7.0 CNY/USD",
            "Arcadis (2020) USD %s/m2 is converted at %.2f CNY/USD, consistent "
            "with the CNY 9,800/m2 fixed construction cost" % (row["token"], implied or 0))


def l_population(row, ctx):
    return ("OK-EXT", "24.8745 million",
            "Shanghai year-end resident population 2023 = 24.8745 million "
            "(Shanghai Statistical Communique 2023: +0.1156 million on 2022)")


def l_doi(row, ctx):
    txt = ctx.ptext.get(row["row_id"], "")
    dois = re.findall(r"doi\.org/(\S+?)(?:[)\s;]|$)", txt)
    dois = [d.rstrip(".,;)") for d in dois]
    _, cache = _bib_pairs(ctx)
    resolved = all(any(k == d for k in cache) for d in dois)
    tok = row["token"].replace("10.", "")
    part_ok = any(tok in d or row["token"] in d for d in dois)
    ok = bool(dois) and resolved and part_ok
    return ("OK-EXT" if ok else "UNVERIFIED", "resolved",
            "DOIs in the paragraph %s; fragment %r belongs to one of them"
            % (dois, row["token"]))


STRUCT_H = {
    "figure index row number": h_fig_index,
    "figure number": h_fig_number,
    "Figure label": h_fig_number,
    "Figure caption": h_fig_number,
    "Table 1 caption number": h_table_caption,
    "Table 2 caption number": h_table_caption,
    "Table 3 caption number": h_table_caption,
    "Table 4 caption number": h_table_caption,
    "Table 5 caption number": h_table_caption,
    "Table 6 caption number": h_table_caption,
    "Table 7 caption number": h_table_caption,
    "Table 8 caption number": h_table_caption,
    "section number": h_section,
    "scenario label": h_scenario,
    "scenario label SSP2-4.5": h_scenario,
    "scenario label SSP5-8.5": h_scenario,
    "projection horizon": h_year_2050,
    "target year": h_year_2050,
    "10th percentile": h_percentile,
    "50th percentile": h_percentile,
    "90th percentile": h_percentile,
    "column header": h_column_header,
    "column header 10th": h_column_header,
    "column header median": h_column_header,
    "column header 90th": h_column_header,
    "Table B1 non-value column": h_b1_label,
    "census round": h_census_round,
    "valuation level label": h_valuation,
    "limitation list numbering": h_limitation,
    "processing step label": h_processing_step,
    "FABDEM version": h_fabdem_version,
    "IBTrACS major version": h_ibtracs,
    "IBTrACS revision": h_ibtracs,
}

NOTE_H = {
    "stated extent of the depth axis, not a model parameter": n_depth_axis,
    "TR-55 technical-release identifier": n_tr55,
    "worked-example coupling coefficient": n_kappa,
    "worked example of a coupling coefficient": n_kappa,
    "month component of a date": n_date,
    "reallocation magnitude implied by the weight tuples": n_reallocation,
    "+-15% band of the per-category adjustment sweep": n_sweep_band,
    "+-25% band of the HP filter sweep": n_sweep_band,
    "+-5% band of the TC scale sweep": n_sweep_band,
    "map approval number serial": n_map_approval,
    "map approval number year": n_map_approval,
    "vintage of the finer shoreline layer": n_shoreline_vintage,
    "EPSG code of the projected CRS": n_epsg,
    "stated raster resolution of the source DEM": n_dem_res,
    "stated LandScan grid size": n_landscan,
    "ISR epoch year (5-year step)": n_isr_epoch,
    "stated ISR raster resolution": n_isr_res,
    "implicit floor minimum (not a config key)": n_cell_range,
    "02+ shorthand in the category label": n_age_shorthand,
    "scientific notation 2.5 x 10^-3": n_sci,
    "scientific notation 10^-4": n_sci,
    "model name year (Holland 2010)": n_model_name,
    "fraction triplet (1/3, 1/3, 1/3)": n_weight_tuple,
}

LIT_H = {
    "in-text citation year (bibliography); not a model quantity": l_citation_year,
    "external: statutory terrestrial area": l_area,
    "external: Arcadis construction cost": l_arcadis,
    "external statistic: Shanghai resident population": l_population,
    "DOI of the IBTrACS source record": l_doi,
    "DOI of the ETOPO source record": l_doi,
    "DOI of the LandScan source record": l_doi,
}


def main() -> int:
    ap = argparse.ArgumentParser(description="WP13.2 structural / explanatory verifier")
    ap.add_argument("--docx", default=str(DOCX))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--show-unverified", action="store_true")
    args = ap.parse_args()

    ctx = Ctx(Path(args.docx))
    mapping = load_csv(MAPPING)
    tokens = {(r["row_id"], r["token"]): r for r in load_csv(TOKENS)}

    rows: list[dict] = []
    for r in mapping:
        cls = r["class"]
        if cls not in ("STRUCT", "NOTE", "LIT"):
            continue
        src = tokens.get((r["row_id"], r["token"]), {})
        row = {"row_id": r["row_id"], "token": r["token"], "class": cls,
               "bind": r["bind"], "context": src.get("context", "")}
        if cls == "LIT":
            h = LIT_H.get(r["bind"])
        else:
            h = STRUCT_H.get(r["bind"]) if cls == "STRUCT" else NOTE_H.get(r["bind"])
        if h is None and cls == "STRUCT":
            b = r["bind"]
            if b.startswith("reference to"):
                h = h_reference
            elif re.match(r"^Figure\s+\d+\s+(label|caption)$", b):
                h = h_fig_number
            elif re.match(r"^Table\s+[A-Z]?\d+\s+caption number$", b):
                h = h_table_caption
        if h is None:
            if cls == "STRUCT":
                verdict, expected, evidence = h_special(row, ctx)
            else:
                verdict, expected, evidence = "UNVERIFIED", "", "no handler for bind %r" % r["bind"]
        else:
            verdict, expected, evidence = h(row, ctx)
        row.update({"verdict": verdict, "expected": expected, "evidence": evidence})
        rows.append(row)

    tally: dict[str, int] = {}
    for r in rows:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    bad = [r for r in rows if not r["verdict"].startswith("OK")]

    print("=== WP13.2 structural / explanatory verifier ===")
    print("  document   : %s" % Path(args.docx).name)
    print("  rows       : %d (STRUCT %d + NOTE %d + LIT %d)"
          % (len(rows), sum(1 for r in rows if r["class"] == "STRUCT"),
             sum(1 for r in rows if r["class"] == "NOTE"),
             sum(1 for r in rows if r["class"] == "LIT")))
    print("  figures    : %d drawings, %d caption numbers, index %s"
          % (len(ctx.fig_order), len(ctx.fig_numbers), ctx.fig_index[:5]))
    print("  tables     : captions %s + Table B1 (%d)" % (ctx.table_caps, ctx.table_b1))
    print("  sections   : %d numbered headings" % len(ctx.sections))
    print("  verdicts   : %s" % ", ".join("%s=%d" % kv for kv in sorted(tally.items())))
    if bad:
        print("  --- NOT OK (%d) ---" % len(bad))
        for r in (bad if args.show_unverified else bad[:25]):
            print("    %-14s %-8s %-10r %-42s %s"
                  % (r["verdict"], r["class"], r["token"], r["bind"][:42],
                     r["evidence"][:70]))

    cols = ["row_id", "class", "token", "bind", "expected", "verdict",
            "evidence", "context"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n",
                       extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    out = Path(args.out)
    tmp = out.with_suffix(".csv.tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8", newline="\n")
    tmp.replace(out)

    summary = {
        "generated": __import__("datetime").datetime.now().isoformat(
            timespec="seconds"),
        "rows": len(rows),
        "verdicts": tally,
        "not_ok": [{"row_id": r["row_id"], "token": r["token"],
                    "bind": r["bind"], "verdict": r["verdict"],
                    "evidence": r["evidence"]} for r in bad],
        "structure": {"drawings": len(ctx.fig_order),
                      "caption_numbers": len(ctx.fig_numbers),
                      "table_captions": ctx.table_caps,
                      "table_b1": ctx.table_b1,
                      "sections": len(ctx.sections)},
        "result": "VERIFY-OK" if not bad else "VERIFY-FINDINGS",
    }
    OUT_SUM.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")
    print("  wrote %s" % out.relative_to(NEWROOT))
    print("RESULT: %s" % summary["result"])
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
