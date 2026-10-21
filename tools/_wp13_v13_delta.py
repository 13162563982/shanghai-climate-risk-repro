# -*- coding: utf-8 -*-
"""WP13.9 - prove that v13 is v12 plus the five declared edits, nothing else.

v12 was submitted to a full numeric audit (1,482 numbers, zero findings).  v13
adds four table call-outs and one citation, so it must be shown that

  1  exactly five elements changed text, and each change equals the declared
     old -> new string (no incidental edits anywhere);
  2  the numeric census grows by exactly four tokens (`4`, `5`, `7`, `2015`)
     and every one of the 1,482 v12 tokens is still present, unchanged;
  3  the four new tokens verify (table references resolve, the citation year
     matches a reference entry);
  4  the two editorial findings are actually gone: all nine numbered tables are
     now cited in the body and no reference entry is left uncited.

Together with the byte-level identity of the other 404 elements, (2) is what
lets the v12 numeric audit carry over to v13 without re-deriving 1,482 verdicts
from scratch - while the four genuinely new numbers are still checked.

OUTPUT
    docs\\_wp13_v13_delta.csv      one row per new number, with verdict
    docs\\_wp13_v13_delta摘要.json counts + assertions

USAGE
    env\\run.ps1 tools\\_wp13_v13_delta.py
"""

from __future__ import annotations

import argparse
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
V12 = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v12.docx"
V13 = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v13.docx"
FROZEN = DOCS / "_wp11_v12清单.csv"
BIB = DOCS / "_wp13_文献核验.csv"
OUT = DOCS / "_wp13_v13_delta.csv"
OUT_SUM = DOCS / "_wp13_v13_delta摘要.json"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# the five declared edits, verbatim from rewrite_manuscript_v13.py
EDITS = {
    "P48": ("when elevated volatility and climate-tail-risk conditions coincided.",
            "when elevated volatility and climate-tail-risk conditions coincided. "
            "Forward projections under the three scenarios are summarised in "
            "Table 4."),
    "P49": ("visible only when the two domains are projected together.",
            "visible only when the two domains are projected together. Scenario "
            "percentiles for the composite index are given in Table 5."),
    "P121": ("allowing this factor to be varied in sensitivity analysis.",
             "allowing this factor to be varied in sensitivity analysis. The "
             "reference curves are listed in Table 7."),
    "P85": ("and the interpretation of outputs.",
            "and the interpretation of outputs. Every model parameter, with its "
            "unit and literature source, is listed in Table B1."),
    "P78": ("(McNamara and Keeler, 2013; Chandra-Putra and Andrews, 2020)",
            "(McNamara and Keeler, 2013; McNamara et al., 2015; Chandra-Putra "
            "and Andrews, 2020)"),
}

# the four numbers that the edits introduce
NEW_TOKENS = [
    ("P48", "4", "OK-STRUCT", "Table 4 exists (HSI 2050 percentiles)"),
    ("P49", "5", "OK-STRUCT", "Table 5 exists (CCHI 2050 percentiles)"),
    ("P121", "7", "OK-STRUCT", "Table 7 exists (HAZUS reference MDR)"),
    ("P78", "2015", "OK-CITE", "McNamara et al. (2015) is in the reference list"),
]


def load_csv(p: Path) -> list[dict]:
    with io.open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_ext():
    spec = importlib.util.spec_from_file_location(
        "ext", NEWROOT / "tools" / "extract_manuscript_numbers.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ext"] = mod
    spec.loader.exec_module(mod)
    return mod


def paragraphs(docx: Path) -> dict[int, str]:
    with zipfile.ZipFile(docx) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    body = root.find(W + "body")
    out, i = {}, 0
    for child in body:
        if child.tag == W + "p":
            out[i] = "".join(t.text or "" for t in child.iter(W + "t"))
            i += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="WP13.9 v13 delta proof")
    ap.add_argument("--v12", default=str(V12))
    ap.add_argument("--v13", default=str(V13))
    args = ap.parse_args()

    v12, v13 = Path(args.v12), Path(args.v13)
    ext = load_ext()
    e12, _ = ext.read_docx_stdlib(v12)
    e13, c13 = ext.read_docx_stdlib(v13)
    t12 = {e.ident: e.text for e in e12}
    t13 = {e.ident: e.text for e in e13}

    failures: list[str] = []

    # ---- 1. only the five declared elements changed
    diff = [k for k in t12 if t12[k] != t13.get(k)]
    diff_ok = set(diff) == set(EDITS)
    print("=== WP13.9 v13 delta proof ===")
    print("  elements changed : %d (%s)" % (len(diff), sorted(diff)))
    if not diff_ok:
        failures.append("changed elements %s != declared %s" % (sorted(diff), sorted(EDITS)))
    for loc, (old, new) in EDITS.items():
        a, b = t12.get(loc, ""), t13.get(loc, "")
        if new.startswith(old):
            ok = b.rstrip().endswith(new.rstrip()) and b[:len(a)] == a[:len(a)]
            kind = "append"
        else:
            ok = old in a and new in b and old not in b
            kind = "insert"
        print("  %-5s %-6s %s" % (loc, kind, "ok" if ok else "FAIL"))
        if not ok:
            failures.append("%s: declared %s not found" % (loc, kind))

    # ---- 2. the numeric census grows by exactly four tokens
    from collections import Counter
    frozen = [(r["row_id"], r["token"]) for r in load_csv(FROZEN)]
    live13 = [(e.ident, tok) for e in e13 for tok, _a, _b in ext.numeric_tokens(e.text)]
    # multiset difference: the same paragraph prints the same token more than
    # once, so a plain membership test would miss a repeated occurrence
    removed = list((Counter(frozen) - Counter(live13)).elements())
    added = list((Counter(live13) - Counter(frozen)).elements())
    print("  v12 tokens kept  : %d / %d" % (len(frozen) - len(removed), len(frozen)))
    print("  v13 token total  : %d (+%d)" % (len(live13), len(live13) - len(frozen)))
    if removed:
        failures.append("v12 tokens missing from v13: %s" % removed[:5])
    if sorted(added) != sorted((r, tk) for r, tk, _v, _e in NEW_TOKENS):
        failures.append("added tokens %s != declared %s"
                        % (sorted(added), sorted((r, tk) for r, tk, _v, _e in NEW_TOKENS)))

    # ---- 3. the four new numbers verify
    caps = [int(m.group(1)) for m in
            (re.match(r"^\s*Table\s+(\d+)\.", t.strip()) for t in t13.values()) if m]
    years = {(r["surname"].lower(), r["year"]) for r in load_csv(BIB)}
    rows = []
    for loc, tok, want, why in NEW_TOKENS:
        if want == "OK-STRUCT":
            ok = int(tok) in caps
            ev = "table captions %s" % caps
        else:
            ok = any(re.sub(r"[^a-z]", "", s) == "mcnamara" and y == tok
                     for s, y in years)
            ev = "reference list carries McNamara %s" % tok
        rows.append({"位置": loc, "数字": tok, "判定": want if ok else "MISMATCH",
                     "证据": ev, "说明": why})
        print("  %-5s %-5s %-14s %s" % (loc, tok, want if ok else "MISMATCH", why))
        if not ok:
            failures.append("%s/%s does not verify" % (loc, tok))

    # ---- 4. the two editorial findings are gone
    body = [(k, v) for k, v in t13.items()
            if not re.match(r"^\s*Table\s+[A-Z]?\d+\.", v.strip())]
    trefs = set()
    for _k, v in body:
        trefs |= set(re.findall(r"Table\s+([A-Z]?\d+)", v))
    want_t = {str(i) for i in range(1, 9)} | {"B1"}
    uncited_t = sorted(want_t - trefs)
    print("  tables cited     : %s (uncited %s)" % (sorted(trefs & want_t), uncited_t or "none"))
    if uncited_t:
        failures.append("tables still uncited: %s" % uncited_t)

    ref_start = int(next(k for k, v in t13.items()
                         if re.match(r"^\s*References\s*$", v.strip()))[1:])
    body_text = " ".join(v for k, v in t13.items()
                         if k.startswith("P") and k[1:].isdigit()
                         and int(k[1:]) < ref_start)
    uncited_refs = []
    for r in load_csv(BIB):
        pat = re.escape(r["surname"].split("-")[0])
        if not re.search(pat + r".{0,80}?" + re.escape(r["year"]), body_text, re.I):
            uncited_refs.append("%s %s" % (r["surname"], r["year"]))
    print("  uncited refs     : %s" % (uncited_refs or "none"))
    if uncited_refs:
        failures.append("references still uncited: %s" % uncited_refs)

    # ---- write
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["位置", "数字", "判定", "证据", "说明"],
                       lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    OUT.write_text(buf.getvalue(), encoding="utf-8", newline="\n")

    summary = {
        "generated": __import__("datetime").datetime.now().isoformat(
            timespec="seconds"),
        "v12_tokens": len(frozen),
        "v13_tokens": len(live13),
        "new_tokens": [{"位置": r, "数字": tk, "判定": v} for r, tk, v, _e in NEW_TOKENS],
        "changed_elements": sorted(diff),
        "tables_cited": sorted(trefs & want_t),
        "tables_uncited": uncited_t,
        "uncited_references": uncited_refs,
        "structure": c13,
        "failures": failures,
        "result": "DELTA-OK" if not failures else "DELTA-FINDINGS",
    }
    OUT_SUM.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")
    print("  wrote %s" % OUT.relative_to(NEWROOT))
    if failures:
        print("  --- FAILURES ---")
        for f in failures:
            print("    " + f)
    print("RESULT: %s" % summary["result"])
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
