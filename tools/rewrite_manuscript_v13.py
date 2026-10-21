# -*- coding: utf-8 -*-
"""WP13.8 - v12 -> v13: the two non-numeric defects found by WP13.

v12 was numerically clean but had two editorial defects that a Nature-family
technical check would flag:

  F1  Table 4, 5, 7 and B1 were never called out in the body text (only their
      captions mentioned them)
  F2  McNamara et al. (2015) sat in the reference list but was never cited

This module fixes both with five edits that add no data value:

    1  P48    + "Forward projections to 2050 ... summarised in Table 4."
    2  P49    + "Scenario percentiles for the composite index ... Table 5."
    3  P121   + "The reference curves are listed in Table 7."
    4  P85    + "... every model parameter ... listed in Table B1."
    5  P78    + "; McNamara et al., 2015" inside the existing citation group

Four numeric tokens enter the manuscript as a result (`4`, `5`, `7`, `2015`);
they are verified by tools/_wp13_v13_delta.py.  Every other character is
untouched, so the 1,482-number audit of v12 carries over unchanged.

The edit machinery is imported from `rewrite_manuscript_v10.py`
(DocIndex / ElementText / plan_raw_repls / apply_raw), the same proven path used
for v10 and v12.

Invariants asserted before the file is written:
  * v12 is byte-exact (recorded SHA) and the earlier baselines are untouched;
  * every anchor is found exactly once and the replacement lands;
  * the document structure counts are unchanged (409 / 11 / 131 / 41 / 37);
  * the `<w:t>` run count is unchanged (1,273) - i.e. no run was split/merged;
  * only `word/document.xml` differs from v12.

USAGE
    env\\run.ps1 tools\\rewrite_manuscript_v13.py              # dry run
    env\\run.ps1 tools\\rewrite_manuscript_v13.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
MAN = NEWROOT / "manuscript"
SRC = MAN / "PAPER_MANUSCRIPT_v12.docx"
OUT = MAN / "PAPER_MANUSCRIPT_v13.docx"
REPORT = DOCS / "_v13_改写报告.json"

SRC_BYTES = 28193084
SRC_SHA = "F86428EDBF44C5465A880AFD"
V11_SHA = "7417FDE618D6C5114628B28C76C7E676141415EFA7BF50016BB13C2D472523CC"
V10_SHA = "40E306B03E2E54913CACF37CF62007226487BC3F879CE5ECADC186075BD1AD91"
FINAL_SHA = "39240D38FCF71ADB72BEA285249AFE5757E0327F26253D48BE45FA899C772F14"

STRUCT = dict(paragraphs=409, tables=11, m_oMath=131, m_oMathPara=41, w_drawing=37)
W_T_RUNS = 1273

# (loc, occurrence, old, new, why)
EDITS = [
    ("P48", 1,
     "when elevated volatility and climate-tail-risk conditions coincided.",
     "when elevated volatility and climate-tail-risk conditions coincided. "
     "Forward projections under the three scenarios are summarised in Table 4.",
     "F1: Table 4 carries the HSI 2050 percentiles and was never called out"),
    ("P49", 1,
     "visible only when the two domains are projected together.",
     "visible only when the two domains are projected together. Scenario "
     "percentiles for the composite index are given in Table 5.",
     "F1: Table 5 carries the CCHI 2050 percentiles and was never called out"),
    ("P121", 1,
     "allowing this factor to be varied in sensitivity analysis.",
     "allowing this factor to be varied in sensitivity analysis. The reference "
     "curves are listed in Table 7.",
     "F1: Table 7 carries the HAZUS reference curves and was never called out"),
    ("P85", 1,
     "and the interpretation of outputs.",
     "and the interpretation of outputs. Every model parameter, with its unit "
     "and literature source, is listed in Table B1.",
     "F1: Table B1 had no body call-out at all"),
    ("P78", 1,
     "(McNamara and Keeler, 2013; Chandra-Putra and Andrews, 2020)",
     "(McNamara and Keeler, 2013; McNamara et al., 2015; Chandra-Putra and "
     "Andrews, 2020)",
     "F2: McNamara et al. (2015) was in the reference list but never cited"),
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, NEWROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description="WP13.8 v12 -> v13 rewrite")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    src = Path(args.src)
    print("=== WP13.8 v13 rewrite ===")
    print("  source : %s (%d B)" % (src.name, src.stat().st_size))

    ok = True
    shas = {"v12": (src, SRC_SHA), "v11": (MAN / "PAPER_MANUSCRIPT_v11.docx", V11_SHA),
            "v10": (MAN / "PAPER_MANUSCRIPT_v10.docx", V10_SHA),
            "FINAL": (MAN / "PAPER_MANUSCRIPT_FINAL.docx", FINAL_SHA)}
    for name, (p, want) in shas.items():
        got = sha256(p)
        good = got.startswith(want)
        print("  %-6s %s %s" % (name, "ok " if good else "!! ", got[:16]))
        ok = ok and good
    if not ok:
        print("RESULT: ABORT (baseline drift)")
        return 2

    rw = load("rw", r"tools\rewrite_manuscript_v10.py")
    ext = load("ext", r"tools\extract_manuscript_numbers.py")

    with zipfile.ZipFile(src) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
        parts = {n: hashlib.sha256(zf.read(n)).hexdigest() for n in zf.namelist()}

    idx = rw.DocIndex(xml)
    repls: list[tuple[int, int, str]] = []
    log = []
    for loc, occ, old, new, why in EDITS:
        et = idx.element(loc)
        status, span = et.locate(old, occ)
        if status != "ok":
            print("  [FAIL] %-6s %r -> %s" % (loc, old[:40], status))
            log.append({"loc": loc, "old": old, "new": new, "why": why,
                        "status": status or "not-found"})
            ok = False
            continue
        ui, ia, ib = span
        repls.extend(rw.plan_raw_repls(et.models[ui], ia, ib, new))
        log.append({"loc": loc, "old": old, "new": new, "why": why,
                    "status": "planned"})
        print("  [PLAN] %-6s +%d chars" % (loc, len(new) - len(old)))

    if not ok:
        print("RESULT: ABORT (anchor not locatable)")
        return 1

    rw.check_overlaps(repls)
    new_xml = rw.apply_raw(xml, repls)

    tmp = DOCS / "_v13_tmp.docx"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
            tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = new_xml.encode("utf-8")
            zout.writestr(item, data)

    _e, c13 = ext.read_docx_stdlib(tmp)
    bad = {k: (c13.get(k), v) for k, v in STRUCT.items() if c13.get(k) != v}
    w_old = xml.count("<w:t>") + xml.count("<w:t ")
    w_new = new_xml.count("<w:t>") + new_xml.count("<w:t ")
    with zipfile.ZipFile(tmp) as zf:
        parts2 = {n: hashlib.sha256(zf.read(n)).hexdigest() for n in zf.namelist()}
    other = [n for n in parts if n != "word/document.xml" and parts[n] != parts2.get(n)]

    ent = {x.ident: x.text for x in _e}
    landed = []
    for row in log:
        txt = ent.get(row["loc"], "")
        # four edits append a sentence (the anchor is a prefix of the new text),
        # one inserts a citation mid-sentence (the anchor disappears)
        if row["new"].startswith(row["old"]):
            hit = txt.rstrip().endswith(row["new"].rstrip())
            gone = txt.count(row["new"]) == 1
        else:
            hit = row["new"] in txt
            gone = row["old"] not in txt
        landed.append(hit and gone)
        if not (hit and gone):
            print("  [FAIL] %s new=%s unique=%s" % (row["loc"], hit, gone))

    print("  structure : %s" % ("ok" if not bad else bad))
    print("  <w:t> runs: %d -> %d" % (w_old, w_new))
    print("  other parts changed: %s" % (other or "none"))
    print("  edits landed: %d/%d" % (sum(landed), len(landed)))

    good = (not bad and not other and w_old == w_new == W_T_RUNS
            and all(landed))
    if not good:
        print("RESULT: ABORT (invariant failure)")
        tmp.unlink(missing_ok=True)
        return 1

    rep = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "source": {"name": src.name, "bytes": src.stat().st_size, "sha256": SRC_SHA},
        "edits": log,
        "structure": c13,
        "w_t_runs": [w_old, w_new],
        "other_parts_changed": other,
    }

    if not args.apply:
        tmp.unlink(missing_ok=True)
        print("[dry-run] all invariants hold; nothing written")
        print("RESULT: DRY-RUN-OK")
        return 0

    out = Path(args.out)
    tmp.replace(out)
    rep["output"] = {"name": out.name, "bytes": out.stat().st_size,
                     "sha256": sha256(out)}
    REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    print("  wrote %s (%d B, %s)" % (out.name, out.stat().st_size,
                                     sha256(out)[:16]))
    print("RESULT: APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
