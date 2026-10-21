# -*- coding: utf-8 -*-
"""WP13.1 - close the numeric census: add the OMML (equation) numbers.

WHY THIS FILE EXISTS
--------------------
WP11 counted 1,385 numeric tokens from `w:t` runs only.  The manuscript also
carries 131 `m:oMath` objects whose text lives in `m:t` runs, which the
`w:t`-based reader cannot see.  Thirty-eight of those equations carry numbers
that appear nowhere in the prose - the monthly HP smoothing parameter
(129,600), the EWMA alpha (0.85), the shelf width/depth (550 km / 55 m), the
CLIMADA drag-coefficient constants (0.75 / 0.067 / 2.5e-3) - so the WP11 census
was not exhaustive.

Naively concatenating `m:t` runs also *invents* numbers, because a fraction
`1/3` is stored as runs "1" and "3", `129,600` as "129" "," "600" and `10^-3`
as "10" "-" "3".  This module therefore rebuilds each equation from the OMML
structure (m:f fraction, m:sSup superscript, m:sSub subscript), inserts a space
at every letter/digit run boundary (`min` + `0.75` -> `min 0.75`), and only
then tokenises.

Every resulting number is bound to an explicit authority:

    MATH-CONST    model constant held in a config: compared with the truth table
    MATH-SRC      constant hard-coded in a module source line: the literal is
                  re-extracted from that file and compared
    MATH-FRAC     a printed fraction such as 1/3: checked against the weight tuple
    MATH-CALC     an arithmetic identity printed in the text
    MATH-NOTATION a symbol index / exponent / clamp bound: no data content

Any number the rule table does not cover is reported as UNCLASSIFIED and blocks
the gate, exactly like WP11's map.

It also re-extracts the `w:t` tokens and asserts they still equal the frozen
`docs\\_wp11_v12清单.csv` row for row (0 drift), so the census cannot silently
change under the audit.

OUTPUT
    docs\\_wp13_公式数字.csv        one row per OMML number, with verdict
    docs\\_wp13_普查摘要.json       counts + drift + verdict tally

USAGE
    env\\run.ps1 tools\\_wp13_census.py
    env\\run.ps1 tools\\_wp13_census.py --dump     # print reconstructed equations
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import re
import sys
import zipfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import xml.etree.ElementTree as ET

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
DOCX = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v12.docx"
FROZEN_TOKENS = DOCS / "_wp11_v12清单.csv"
TRUTH = DOCS / "_wp11_真值表.csv"
OUT_MATH = DOCS / "_wp13_公式数字.csv"
OUT_SUM = DOCS / "_wp13_普查摘要.json"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"

K_CONST = "MATH-CONST"
K_SRC = "MATH-SRC"
K_FRAC = "MATH-FRAC"
K_CALC = "MATH-CALC"
K_IDENT = "MATH-IDENT"
K_NOT = "MATH-NOTATION"

# ───────────────────────────────────────────────────────────── OMML rebuild
SKIP = {M + t for t in ("fPr", "rPr", "ctrlPr", "sSupPr", "sSubPr", "sSubSupPr",
                        "dPr", "naryPr", "radPr", "funcPr", "limLowPr",
                        "limUppPr", "accPr", "barPr", "groupChrPr", "boxPr",
                        "borderBoxPr", "phantPr", "eqArrPr", "mPr", "argPr")}


def mpieces(node, acc: list[str] | None = None) -> list[str]:
    """Flatten one OMML node into run-level pieces, keeping structure markers.

    Markers: ``^`` superscript, ``_`` subscript, ``(`` ``)`` ``/`` fraction.
    Pieces are joined later with a letter/digit boundary rule, because Word
    stores ``min`` and ``0.75`` as two runs and a naive join yields
    ``min0.75``, which the tokeniser would then drop.
    """
    acc = [] if acc is None else acc
    if node is None:
        return acc
    tag = node.tag
    if tag == M + "r":
        acc.append("".join(t.text or "" for t in node.iter(M + "t")))
        return acc
    if tag == M + "t":
        acc.append(node.text or "")
        return acc
    if tag in SKIP:
        return acc
    if tag == M + "f":
        acc.append("(")
        mpieces(node.find(M + "num"), acc)
        acc.append(")/(")
        mpieces(node.find(M + "den"), acc)
        acc.append(")")
        return acc
    if tag == M + "sSup":
        mpieces(node.find(M + "e"), acc)
        acc.append("^")
        mpieces(node.find(M + "sup"), acc)
        return acc
    if tag == M + "sSub":
        mpieces(node.find(M + "e"), acc)
        acc.append("_")
        mpieces(node.find(M + "sub"), acc)
        return acc
    if tag == M + "sSubSup":
        mpieces(node.find(M + "e"), acc)
        acc.append("_")
        mpieces(node.find(M + "sub"), acc)
        acc.append("^")
        mpieces(node.find(M + "sup"), acc)
        return acc
    for c in node:
        mpieces(c, acc)
    return acc


def _join(parts: list[str]) -> str:
    """Join pieces, inserting a space at every letter->digit run boundary."""
    out = ""
    for p in parts:
        if not p:
            continue
        if out and out[-1].isalpha() and p[0].isdigit():
            out += " "
        out += p
    return out


def mtext(node) -> str:
    """Rebuild the readable text of one OMML node (structure aware)."""
    return _join(mpieces(node))


# ───────────────────────────────────────────────────────── math tokenisation
MEXP = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
                  r"\^(-?\d+)(?!\d|\.\d)")
MNUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?!\d|\.\d)")


def math_tokens(text: str):
    """Tokenise reconstructed equation text.

    Subscripts are normalised to spaces first, so ``MA_12`` yields the window
    length 12 instead of hiding it behind the underscore.  A number raised to a
    signed integer power (``10^-3``) is returned as one token with its value.
    """
    t = text.replace("_", " ")
    out = []
    taken = []
    for m in MEXP.finditer(t):
        base = float(m.group(1).replace(",", ""))
        exp = int(m.group(2).replace("\u2212", "-"))
        out.append((m.group(0), base ** exp, m.start(), m.end()))
        taken.append((m.start(), m.end()))
    for m in MNUM.finditer(t):
        lo, hi = m.start(), m.end()
        if any(a < hi and lo < b for a, b in taken):
            continue
        out.append((m.group(0), float(m.group(1).replace(",", "")), lo, hi))
    out.sort(key=lambda x: x[2])
    return out


def digits_of(tok: str) -> int:
    core = re.sub(r"[^0-9.]", "", tok.split("^")[0])
    return len(core.split(".")[1]) if "." in core else 0


def print_at(value, dp: int) -> str:
    q = Decimal(1).scaleb(-dp)
    return str(Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP))


# ──────────────────────────────────────────────────── authority rule table
# Each element lists its numbers in document order: (raw_token, class, bind, note)
#   metric:<id>          compare with docs/_wp11_真值表.csv
#   src:<file>:<literal> the literal must occur in the module source and match
#   frac:<num>/<den>     a printed fraction; check the config weight tuple
#   calc:<expr>          arithmetic identity that must hold exactly
#   notation             symbol index / exponent / clamp bound, no data content
MATH_RULES: dict[str, list[tuple[str, str, str, str]]] = {
    "P59": [("129,600", K_CONST, "metric:p.Finance.HP_LAMBDA",
             "HP monthly smoothing parameter, Figure 10 caption")],
    "P62": [("0.358", K_CONST, "metric:p.Composite.CFCI_TARGET_RHO",
             "dependence target, Figure 11 caption")],
    "T5#r1c3": [("1", K_NOT, "notation", "constant term of (1 + kappa_d S)")],
    "T5#r2c3": [("1", K_FRAC, "frac:1/3", "equal weight, numerator"),
                ("3", K_FRAC, "frac:1/3", "equal weight, denominator")],
    "P136": [("1", K_NOT, "notation", "constant term of (1 + dISR)"),
             ("1", K_NOT, "notation", "constant term of (1 + kappa MDR)")],
    "P157": [("129,600", K_CONST, "metric:p.Finance.HP_LAMBDA",
              "HP monthly smoothing parameter (Methods 1.7)")],
    "P160": [("1", K_FRAC, "frac:1/3", "equal weight, numerator"),
             ("3", K_FRAC, "frac:1/3", "equal weight, denominator")],
    "P192": [("550", K_CONST, "metric:p.Climate.L_SHELF_M",
              "effective shelf width printed in km (L_SHELF_M = 550,000 m)"),
             ("55", K_CONST, "metric:p.Climate.H_SHELF_M",
              "mean shelf depth printed in m")],
    "P320": [("1", K_NOT, "notation", "constant term of (1 + kappa_d S)")],
    "P322": [("1", K_NOT, "notation", "constant term inside ln(1 + M/EAL)"),
             ("1", K_NOT, "notation", "lag weight constant"),
             ("1", K_NOT, "notation", "constant term of (1 - alpha)")],
    "P323": [("0.85", K_CONST, "metric:p.Climate.CRI_EWMA_ALPHA",
              "EWMA smoothing parameter")],
    "P326": [("1", K_NOT, "notation", "constant term of the Holland profile")],
    "P334": [("2", K_NOT, "notation", "squared wind speed in the surge set-up")],
    "P335": [("3", K_CONST, "metric:p.Climate.FETCH_RMAX_FACTOR",
              "effective fetch = 3 x R_max")],
    "P337": [("0.75", K_SRC, "src:Climate/climate_functions.py:0.75",
              "drag coefficient intercept"),
             ("0.067", K_SRC, "src:Climate/climate_functions.py:0.067",
              "drag coefficient slope per m/s"),
             ("10^-3", K_SRC, "src:Climate/climate_functions.py:1e-3",
              "10^-3 scaling of the drag coefficients"),
             ("2.5", K_CONST, "metric:p.Climate.CD_MAX",
              "cap of the drag coefficient (printed as 2.5 x 10^-3)"),
             ("10^-3", K_SRC, "src:Climate/climate_functions.py:1e-3",
              "10^-3 scaling of the drag cap")],
    "P339": [("1", K_NOT, "notation", "indicator function 1{...}"),
             ("0", K_NOT, "notation", "depth floor inside max(...)")],
    "P342": [("0", K_NOT, "notation", "overtopping depth floor")],
    "P346": [("0", K_NOT, "notation", "clamp lower bound"),
             ("1", K_NOT, "notation", "clamp upper bound"),
             ("0", K_NOT, "notation", "clamp lower bound"),
             ("2", K_NOT, "notation", "exponent of the smoothstep"),
             ("3", K_NOT, "notation", "smoothstep polynomial coefficient"),
             ("2", K_NOT, "notation", "smoothstep polynomial coefficient")],
    "P347": [("0", K_NOT, "notation", "clamp lower bound"),
             ("0", K_NOT, "notation", "clamp lower bound"),
             ("1", K_NOT, "notation", "clamp upper bound")],
    "P349": [("1", K_NOT, "notation", "indicator function 1{TWL>0}"),
             ("0", K_NOT, "notation", "indicator threshold"),
             ("0", K_NOT, "notation", "clamp lower bound"),
             ("1", K_NOT, "notation", "clamp upper bound")],
    "P351": [("2", K_NOT, "notation", "exponent of the intensity factor")],
    "P354": [("3", K_NOT, "notation", "exponent of the Emanuel MDR sigmoid"),
             ("1", K_NOT, "notation", "constant term of 1 + v^3"),
             ("3", K_NOT, "notation", "exponent of the Emanuel MDR sigmoid"),
             ("0", K_NOT, "notation", "floor of max(|V|-V_thresh, 0)")],
    "P356": [("1", K_NOT, "notation", "constant term of the SVI amplifier")],
    "P361": [("1", K_NOT, "notation", "outer constant term of the compound MDR"),
             ("1", K_NOT, "notation", "wind-damage constant term"),
             ("1", K_NOT, "notation", "surge-damage constant term")],
    "P363": [("1", K_NOT, "notation", "constant term of (1 + dISR)"),
             ("1", K_NOT, "notation", "constant term of (1 + kappa MDR)")],
    "P366": [("1", K_NOT, "notation", "constant term of (1 + kappa_d S)")],
    "P368": [("1", K_NOT, "notation", "lower summation bound j = 1")],
    "P369": [("1", K_NOT, "notation", "constant term inside log(1 + M/EAL)"),
             ("1", K_NOT, "notation", "lag weight constant"),
             ("1", K_NOT, "notation", "constant term of (1 - alpha)")],
    "P371": [("1", K_NOT, "notation", "time index t+1"),
             ("0", K_NOT, "notation", "mean-reversion level of Z")],
    "P372": [("1", K_NOT, "notation", "time index t+1"),
             ("1", K_NOT, "notation", "time index t+1")],
    "P373": [("0", K_NOT, "notation", "clip lower bound"),
             ("1", K_NOT, "notation", "clip upper bound")],
    "P375": [("1", K_NOT, "notation", "logistic capacity term"),
             ("1", K_NOT, "notation", "logistic capacity term"),
             ("1", K_NOT, "notation", "logistic capacity term")],
    "P376": [("1", K_NOT, "notation", "logistic capacity term"),
             ("1", K_NOT, "notation", "logistic capacity term"),
             ("1", K_NOT, "notation", "logistic capacity term")],
    "P378": [("100", K_CONST, "metric:p.Climate.CRI_BASE_INDEX",
              "CRI base level"),
             ("12", K_SRC, "src:Climate/07_climate_index.py:rolling(12",
              "moving-average window in the CRI normalisation"),
             ("12", K_SRC, "src:Climate/07_climate_index.py:rolling(12",
              "moving-average window in the CRI normalisation"),
             ("0", K_NOT, "notation", "subscript of the base month t0")],
    "P381": [("1", K_FRAC, "frac:1/3", "equal weight, numerator"),
             ("3", K_FRAC, "frac:1/3", "equal weight, denominator")],
    "P383": [("1", K_NOT, "notation", "constant term of the relative gap")],
    "P385": [("12", K_CONST, "metric:p.Finance.VOLATILITY_WINDOW",
              "rolling window of the realised volatility")],
    "P387": [("1600", K_IDENT, "ident:1600*(12/4)**4",
              "annual HP smoothing parameter; the printed identity must close"),
             ("12", K_NOT, "notation", "months per year in the conversion"),
             ("4", K_NOT, "notation", "months per quarter in the conversion"),
             ("4", K_NOT, "notation", "power-law exponent of the HP convention"),
             ("129,600", K_CONST, "metric:p.Finance.HP_LAMBDA",
              "monthly HP smoothing parameter = 1600 x (12/4)^4")],
    "P389": [("1", K_NOT, "notation", "time index t+1"),
             ("1", K_NOT, "notation", "time index t+1"),
             ("1", K_NOT, "notation", "lower summation bound k = 1")],
    "P390": [("2", K_NOT, "notation", "variance exponent of the jump size")],
    "P392": [],
    "P394": [("2025", K_CONST, "metric:data.cprice.y1",
              "last year of the city price series, the CVaR deflator base")],
    "P396": [("100", K_CONST, "metric:p.Finance.FRI_BASE_INDEX",
              "HSI base level"),
             ("12", K_CONST, "metric:p.Finance.VOLATILITY_WINDOW",
              "moving-average window in the HSI normalisation"),
             ("12", K_CONST, "metric:p.Finance.VOLATILITY_WINDOW",
              "moving-average window in the HSI normalisation"),
             ("0", K_NOT, "notation", "subscript of the base month t0")],
    "P401": [("1", K_NOT, "notation", "numerator of 1/T"),
             ("1", K_NOT, "notation", "numerator of 1/T"),
             ("1", K_NOT, "notation", "lower summation bound"),
             ("1", K_NOT, "notation", "lower summation bound")],
    "P402": [("0.358", K_CONST, "metric:p.Composite.CFCI_TARGET_RHO",
              "dependence target of the Iman-Conover reordering")],
    "P404": [("0.358", K_CONST, "metric:p.Composite.CFCI_TARGET_RHO",
              "dependence target of the Iman-Conover reordering")],
}


# ─────────────────────────────────────────────────────────────── helpers
def load_ext():
    spec = importlib.util.spec_from_file_location(
        "ext", NEWROOT / "tools" / "extract_manuscript_numbers.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ext"] = mod
    spec.loader.exec_module(mod)
    return mod


def load_csv(p: Path) -> list[dict]:
    with io.open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest().upper()


def element_math(docx: Path) -> list[dict]:
    """Every paragraph / table cell that carries numbers inside m:oMath."""
    with zipfile.ZipFile(docx) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    body = root.find(W + "body")
    out: list[dict] = []
    p_idx = t_idx = 0
    for child in body:
        if child.tag == W + "p":
            eqs = ["".join(mtext(m)) for m in child.iter(M + "oMath")]
            txt = "".join(t.text or "" for t in child.iter(W + "t"))
            if any(any(ch.isdigit() for ch in e) for e in eqs):
                out.append({"row_id": "P%d" % p_idx, "kind": "paragraph",
                            "math": " | ".join(eqs), "text": txt})
            p_idx += 1
        elif child.tag == W + "tbl":
            for r_i, tr in enumerate(child.findall(W + "tr")):
                for c_i, tc in enumerate(tr.findall(W + "tc")):
                    eqs = ["".join(mtext(m)) for m in tc.iter(M + "oMath")]
                    txt = "".join(t.text or "" for t in tc.iter(W + "t"))
                    if any(any(ch.isdigit() for ch in e) for e in eqs):
                        out.append({"row_id": "T%d#r%dc%d" % (t_idx, r_i, c_i),
                                    "kind": "table_cell",
                                    "math": " | ".join(eqs), "text": txt})
            t_idx += 1
    return out


def verify(row: dict, truth: dict) -> tuple[str, str, str]:
    """(verdict, expected, evidence) for one equation number."""
    cls, bind, tok = row["cls"], row["bind"], row["token"]
    dp = digits_of(tok)

    if cls == K_NOT:
        return "OK-MATH-NOTATION", "", "symbol index / exponent, no data content"

    if cls == K_FRAC:
        frac = bind.split(":", 1)[1]
        num, den = frac.split("/")
        want = float(num) / float(den)
        keys = sorted(k for k in truth if k.startswith("fweights."))
        vals = [float(truth[k]["value"]) for k in keys]
        ok = len(vals) == 3 and all(abs(v - want) < 1e-12 for v in vals)
        return ("OK-MATH-FRAC" if ok else "MISMATCH", frac,
                "FRI_WEIGHTS = %s vs %s" % ([round(v, 6) for v in vals], frac))

    if bind.startswith("metric:"):
        mid = bind.split(":", 1)[1]
        t = truth.get(mid)
        if t is None:
            return "NO-METRIC", "", "metric %r absent from the truth table" % mid
        val = float(t["value"])
        if mid.endswith("L_SHELF_M"):        # printed in km
            val = val / 1000.0
        elif mid.endswith("CD_MAX"):          # printed as 2.5 with a 10^-3 factor
            val = val * 1000.0
        exp = print_at(val, dp)
        got = tok.replace(",", "")
        ok = exp == str(Decimal(got))
        return ("OK-MATH-CONST" if ok else "MISMATCH", exp,
                "%s = %s (%s)" % (mid, t["value"], t["source"]))

    if bind.startswith("src:"):
        rel, literal = bind[4:].split(":", 1)
        path = NEWROOT / rel
        if not path.is_file():
            return "NO-SOURCE", "", "%s not found" % rel
        src = io.open(path, encoding="utf-8", errors="replace").read()
        hits = src.count(literal)
        if not hits:
            return "NO-SOURCE", "", "literal %r absent from %s" % (literal, rel)
        m = re.search(r"\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", literal)
        want = float(m.group(0)) if m else None
        if "^" in tok:
            got = row["value"]
            ok = want is not None and abs(got - want) <= 1e-15
            exp = repr(want)
        else:
            exp = print_at(want, dp) if want is not None else ""
            ok = bool(exp) and exp == str(Decimal(tok.replace(",", "")))
        return ("OK-MATH-SRC" if ok else "MISMATCH", exp,
                "%s: %r x%d" % (rel, literal, hits))

    if cls == K_IDENT:
        expr = bind.split(":", 1)[1]
        want = eval(expr, {"__builtins__": {}}, {})  # noqa: S307 - fixed literal
        nums = [float(x.replace(",", "")) for x in
                re.findall(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", row["math"])]
        last = nums[-1] if nums else None
        ok = last is not None and abs(want - last) < 1e-9
        return ("OK-MATH-IDENT" if ok else "MISMATCH", print_at(want, 0),
                "identity %s = %s; equation closes on %s"
                % (expr, want, last))

    if bind.startswith("calc:"):
        expr = bind.split(":", 1)[1]
        want = eval(expr, {"__builtins__": {}}, {})  # noqa: S307 - fixed literal
        exp = print_at(want, dp)
        ok = exp == str(Decimal(tok.replace(",", "")))
        return ("OK-MATH-CALC" if ok else "MISMATCH", exp,
                "%s = %s" % (expr, want))

    return "UNCLASSIFIED", "", "no rule"


def main() -> int:
    ap = argparse.ArgumentParser(description="WP13.1 OMML numeric census")
    ap.add_argument("--docx", default=str(DOCX))
    ap.add_argument("--out", default=str(OUT_MATH))
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()

    docx = Path(args.docx)
    truth = {r["metric_id"]: r for r in load_csv(TRUTH)}
    elems = element_math(docx)

    if args.dump:
        for e in elems:
            toks = [t[0] for t in math_tokens(e["math"])]
            print("%-14s %-60r %s" % (e["row_id"], e["math"][:60], toks))
        return 0

    # ---- w:t drift assertion against the frozen WP11 census
    ext = load_ext()
    entries, counts = ext.read_docx_stdlib(docx)
    live = []
    for e in entries:
        for tok, a, b in ext.numeric_tokens(e.text):
            live.append((e.ident, tok))
    frozen = [(r["row_id"], r["token"]) for r in load_csv(FROZEN_TOKENS)]
    drift = [i for i, (a, b) in enumerate(zip(live, frozen)) if a != b]
    if len(live) != len(frozen):
        drift.append(("length", len(live), len(frozen)))

    # ---- equation numbers
    rows: list[dict] = []
    unclass: list[str] = []
    for e in elems:
        toks = math_tokens(e["math"])
        spec = MATH_RULES.get(e["row_id"], [])
        if [t[0] for t in toks] != [t[0] for t in spec]:
            unclass.append("%s: document %r != rules %r"
                           % (e["row_id"], [t[0] for t in toks],
                              [t[0] for t in spec]))
            continue
        for idx, (raw, val, a, b) in enumerate(toks):
            _, cls, bind, note = spec[idx]
            row = {"row_id": e["row_id"], "kind": e["kind"], "carrier": "m:t",
                   "seq": idx + 1, "token": raw, "value": val,
                   "digits": digits_of(raw), "cls": cls, "bind": bind,
                   "note": note, "math": e["math"],
                   "context": re.sub(r"\s+", " ", e["math"])[:160]}
            verdict, expected, evidence = verify(row, truth)
            if verdict == "UNCLASSIFIED":
                unclass.append("%s#%d %r" % (e["row_id"], idx + 1, raw))
            row.update({"verdict": verdict, "expected": expected,
                        "evidence": evidence})
            rows.append(row)

    tally: dict[str, int] = {}
    for r in rows:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    bad = {k: v for k, v in tally.items()
           if k in ("MISMATCH", "NO-METRIC", "NO-SOURCE", "UNCLASSIFIED")}

    print("=== WP13.1 OMML numeric census ===")
    print("  document        : %s (%d B, %s)"
          % (docx.name, docx.stat().st_size, sha256(docx)[:16]))
    print("  w:t token census: live %d vs frozen %d (drift %d)"
          % (len(live), len(frozen), len(drift)))
    print("  equations       : %d elements, %d numbers" % (len(elems), len(rows)))
    print("  verdicts        : %s" % ", ".join("%s=%d" % kv
                                                for kv in sorted(tally.items())))
    n_not = tally.get("OK-MATH-NOTATION", 0)
    n_sub = sum(v for k, v in tally.items()
                if k.startswith("OK-MATH") and k != "OK-MATH-NOTATION")
    print("  substantive     : %d constants + %d notation = %d"
          % (n_sub, n_not, n_sub + n_not))
    if unclass:
        print("  --- UNCLASSIFIED (%d) ---" % len(unclass))
        for u in unclass:
            print("    " + u)
    if bad:
        print("  --- FINDINGS ---")
        for r in rows:
            if r["verdict"] in bad:
                print("    %-10s %-14s %-8r expected %s | %s"
                      % (r["verdict"], r["row_id"], r["token"],
                         r["expected"], r["evidence"][:80]))

    cols = ["row_id", "kind", "carrier", "seq", "token", "value", "digits",
            "cls", "bind", "expected", "verdict", "evidence", "context", "note"]
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
        "docx": docx.name,
        "docx_sha": sha256(docx),
        "w_t_tokens_live": len(live),
        "w_t_tokens_frozen": len(frozen),
        "w_t_drift": len(drift),
        "math_elements": len(elems),
        "math_numbers": len(rows),
        "math_substantive": n_sub,
        "math_notation": n_not,
        "verdicts": tally,
        "unclassified": unclass,
        "result": "CENSUS-OK" if (not bad and not unclass and not drift)
                  else "CENSUS-FINDINGS",
    }
    OUT_SUM.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")
    print("  wrote %s" % out.relative_to(NEWROOT))
    print("  wrote %s" % OUT_SUM.relative_to(NEWROOT))
    print("RESULT: %s" % summary["result"])
    return 0 if summary["result"] == "CENSUS-OK" else 1


if __name__ == "__main__":
    sys.exit(main())
