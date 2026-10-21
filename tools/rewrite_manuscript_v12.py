# -*- coding: utf-8 -*-
"""WP11.6 - apply the alignment corrections found by _wp11_check.py.

Eleven falsifiable edits, all inside a single `<w:t>` run, none touching a
formula, a figure or a table structure:

  1  P42           CRI 10th-90th percentile ranges  -> the values Table 3 prints
  2  P93           Knutson intensity factors 1.05/1.10 -> the applied 1.0324/1.0442
  3  T9 r15        same factor, Table B1 value cell
  4  T9 r16        same factor, Table B1 value cell
  5  T8 r20        CFCI target-rho deviation band  -> recomputed -0.4% to +0.2%
  6  P66           the same band in the prose
  7  T8 r9         V_half adj. B_new max deviation +18% -> +17%
  8  P75           Figure 14 caption no longer claims a scenario breakdown

The edit machinery is imported from `rewrite_manuscript_v10.py` (ParaModel /
ElementText / DocIndex / plan_raw_repls / apply_raw) so the OMML guard and the
entity-decoding path are the ones already proven on v10.

Invariants asserted before the file is written:
  * every needle is found exactly where expected, and the replacement lands;
  * the document structure counts are unchanged (409 paragraphs / 11 tables /
    131 m:oMath / 41 m:oMathPara / 37 drawings);
  * the number of `<w:t>` runs is unchanged;
  * only `word/document.xml` differs from v11.

USAGE
-----
  env\\run.ps1 tools\\rewrite_manuscript_v12.py              # dry run
  env\\run.ps1 tools\\rewrite_manuscript_v12.py --apply
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
SRC = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v11.docx"
OUT = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v12.docx"
REPORT = DOCS / "_v12_改写报告.json"

SRC_BYTES = 28193070
SRC_SHA = "7417FDE618D6C5114628B28C76C7E676141415EFA7BF50016BB13C2D472523CC"
FROZEN = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_FINAL.docx"
FROZEN_SHA = "39240D38FCF71ADB72BEA285249AFE5757E0327F26253D48BE45FA899C772F14"
V10 = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v10.docx"
V10_SHA = "40E306B03E2E54913CACF37CF62007226487BC3F879CE5ECADC186075BD1AD91"

STRUCT = dict(paragraphs=409, tables=11, m_oMath=131, m_oMathPara=41, w_drawing=37)
MINUS = "\u2212"

# (loc, occurrence, old, new, why)
EDITS = [
    ("P42", 1,
     "ranges of 490\u2013689, 564\u2013768 and 641\u2013837",
     "ranges of 491\u2013692, 565\u2013770 and 643\u2013840",
     "the printed ranges were the pre-A-baseline values; Table 3 in the same "
     "paragraph already carries 491/692, 565/770, 643/840"),
    ("P93", 1,
     "The resulting intensity factors for 2050 are 1.05 (SSP2-4.5) and 1.10 (SSP5-8.5).",
     "The resulting intensity factors for 2050 are 1.0324 (SSP2-4.5) and 1.0442 (SSP5-8.5).",
     "the run log records 1.0324 / 1.0442; 1.05/1.10 is only the silent "
     "fallback constant in 00_config.py"),
    ("T9#r15c2", 1, "1.05", "1.0324",
     "Table B1 must print the applied Knutson factor, not the config fallback"),
    ("T9#r16c2", 1, "1.10", "1.0442",
     "Table B1 must print the applied Knutson factor, not the config fallback"),
    ("T8#r20c6", 1,
     MINUS + "0.2% to +0.6%", MINUS + "0.4% to +0.2%",
     "recomputed from the same sweep: -0.417% to +0.248%"),
    ("P66", 1,
     "deviation " + MINUS + "0.2% to +0.6%",
     "deviation " + MINUS + "0.4% to +0.2%",
     "same band as Table 8 r20"),
    ("T8#r9c6", 1, MINUS + "8% to +18%", MINUS + "8% to +17%",
     "recomputed max deviation is +17.47%, which prints as +17%"),
    ("P75", 1, "across scenarios",
     "over the 2011\u20132023 historical period",
     "Figure 14 renders the historical decomposition only (three component "
     "panels); it carries no scenario dimension"),
    ("P49", 1,
     "an empirical rank correlation of \u03c1 = 0.358, and the geometric-mean",
     "a rank correlation of \u03c1 = 0.358, the calibrated dependence target "
     "used in the paired projection, and the geometric-mean",
     "0.358 is CFCI_TARGET_RHO, not the empirical statistic (Spearman 0.3231, "
     "Pearson 0.3593); P62 already calls it the calibrated dependence target "
     "[author ruling A1-a, 2026-10-18]"),
    # --- A2: the 0.9999 ratio has no v8 provenance.  The observed-loss
    # workbook in data/ carries no Shanghai row at all, so the v6 calibration
    # cannot be recomputed; the A-baseline expectation is 1.0020.  The claim is
    # kept qualitatively and the false four-digit precision is dropped.
    ("P9", 1,
     "with a period-matched ratio of 0.9999 (1995\u20132023)",
     "with a period-matched ratio of approximately unity (1995\u20132023)",
     "A2: 0.9999 is a v6 statistic recorded only in a config comment; under the "
     "official boundary the ratio is 1.0020, so the four-digit claim cannot be "
     "sustained [author ruling A2-b, 2026-10-18]"),
    ("P17", 1,
     "(period-matched calibration fit ratio of 0.9999)",
     "(period-matched calibration fit ratio of approximately unity)",
     "A2: same statistic, same reason"),
    ("P251", 1,
     "period-matched AAL pred/obs = 0.9999 for 1995\u20132023",
     "period-matched AAL pred/obs \u2248 1.00 for 1995\u20132023",
     "A2: quote the A-baseline expectation to the precision it supports"),
]

# A3: body prose that carries a heading style (breaks the outline and pulls the
# Discussion into one keepNext chain).  Style id only; no text change.
# P17 is heading 4; the five Discussion paragraphs are heading 3.
STYLE_FIX = {"P17": "4", "P77": "3", "P78": "3", "P79": "3", "P80": "3",
             "P81": "3"}
STYLE_TO = "a0"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def load_rewriter():
    spec = importlib.util.spec_from_file_location(
        "rw", NEWROOT / "tools" / "rewrite_manuscript_v10.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rw"] = mod
    spec.loader.exec_module(mod)
    return mod


def load_extractor():
    spec = importlib.util.spec_from_file_location(
        "ext", NEWROOT / "tools" / "extract_manuscript_numbers.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ext"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description="WP11.6 v11 -> v12 rewrite")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    src = Path(args.src)
    print("=== WP11.6 v12 rewrite ===")
    print("  source : %s (%d B)" % (src.name, src.stat().st_size))

    ok = True
    if sha256(src) != SRC_SHA:
        print("  ! source SHA differs from the recorded v11 baseline")
        ok = False
    if sha256(FROZEN) != FROZEN_SHA:
        print("  ! frozen FINAL changed")
        ok = False
    if sha256(V10) != V10_SHA:
        print("  ! v10 changed")
        ok = False
    if not ok:
        print("RESULT: ABORT (baseline drift)")
        return 2

    rw = load_rewriter()
    ext = load_extractor()

    with zipfile.ZipFile(src) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
        names = zf.namelist()
        parts = {n: hashlib.sha256(zf.read(n)).hexdigest() for n in names}

    idx = rw.DocIndex(xml)
    repls: list[tuple[int, int, str]] = []
    log = []
    for loc, occ, old, new, why in EDITS:
        et = idx.element(loc)
        status, span = et.locate(old, occ)
        if status != "ok":
            print("  [FAIL] %-10s %r -> %s" % (loc, old[:46], status))
            log.append({"loc": loc, "old": old, "new": new, "why": why,
                        "status": status or "not-found"})
            ok = False
            continue
        ui, ia, ib = span
        model = et.models[ui]
        repls.extend(rw.plan_raw_repls(model, ia, ib, new))
        log.append({"loc": loc, "old": old, "new": new, "why": why,
                    "status": "planned"})
        print("  [PLAN] %-10s %r -> %r" % (loc, old[:40], new[:40]))

    if not ok:
        print("RESULT: ABORT (%d edit(s) not locatable)" % len(
            [x for x in log if x["status"] != "planned"]))
        return 1

    # ---- A3: heading style -> Body Text on the prose paragraphs
    style_log = []
    for loc, want in STYLE_FIX.items():
        lo, hi = idx.paragraph_content(loc)
        seg = xml[lo:hi]
        m = re.search(r'<w:pStyle\b[^>]*?w:val="([^"]*)"', seg)
        if not m or m.group(1) != want:
            print("  [FAIL] %-6s pStyle is %r, expected %r"
                  % (loc, m.group(1) if m else None, want))
            style_log.append({"loc": loc, "status": "not-found"})
            ok = False
            continue
        repls.append((lo + m.start(1), lo + m.end(1), STYLE_TO))
        style_log.append({"loc": loc, "from": want, "to": STYLE_TO,
                          "status": "planned"})
        print("  [PLAN] %-6s pStyle %r -> %r" % (loc, want, STYLE_TO))

    if not ok:
        print("RESULT: ABORT (style edit not locatable)")
        return 1

    rw.check_overlaps(repls)
    new_xml = rw.apply_raw(xml, repls)

    # ---- invariants on the rewritten XML
    entries, counts = ext.read_docx_stdlib_bytes(new_xml.encode("utf-8")) \
        if hasattr(ext, "read_docx_stdlib_bytes") else (None, None)
    with zipfile.ZipFile(src) as zf:
        pass
    tmp_docx = DOCS / "_v12_tmp.docx"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
            tmp_docx, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = new_xml.encode("utf-8")
            zout.writestr(item, data)
    _e, c12 = ext.read_docx_stdlib(tmp_docx)
    bad = {k: (c12.get(k), v) for k, v in STRUCT.items() if c12.get(k) != v}
    print("  structure: %s" % ("ok" if not bad else bad))

    w_t_old = xml.count("<w:t>") + xml.count("<w:t ")
    w_t_new = new_xml.count("<w:t>") + new_xml.count("<w:t ")
    print("  <w:t> runs: %d -> %d" % (w_t_old, w_t_new))

    with zipfile.ZipFile(tmp_docx) as zf:
        parts2 = {n: hashlib.sha256(zf.read(n)).hexdigest() for n in zf.namelist()}
    other = [n for n in parts if n != "word/document.xml" and parts[n] != parts2.get(n)]
    print("  other parts changed: %s" % (other or "none"))

    # ---- verify the edits landed
    _e2, _c2 = ext.read_docx_stdlib(tmp_docx)
    ent = {x.ident: x.text for x in _e2}
    sty = {x.ident: x.style for x in _e2}
    landed = []
    for row in log:
        txt = ent.get(row["loc"], "")
        hit = row["new"] in txt
        gone = row["old"] not in txt
        landed.append(hit and gone)
        if not (hit and gone):
            print("  [FAIL] %s: new=%s old_gone=%s" % (row["loc"], hit, gone))
    print("  edits landed: %d/%d" % (sum(landed), len(landed)))

    style_ok = []
    for row in style_log:
        got = sty.get(row["loc"], "")
        style_ok.append(got == STYLE_TO)
        if got != STYLE_TO:
            print("  [FAIL] %s: pStyle is %r" % (row["loc"], got))
    print("  style edits landed: %d/%d" % (sum(style_ok), len(style_ok)))

    good = (not bad and not other and w_t_old == w_t_new and all(landed)
            and all(style_ok))
    if not good:
        print("RESULT: ABORT (invariant failure)")
        tmp_docx.unlink(missing_ok=True)
        return 1

    rep = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "source": {"name": src.name, "bytes": src.stat().st_size,
                   "sha256": SRC_SHA},
        "edits": log,
        "style_edits": style_log,
        "structure": c12,
        "w_t_runs": [w_t_old, w_t_new],
        "other_parts_changed": other,
    }

    if not args.apply:
        tmp_docx.unlink(missing_ok=True)
        print("[dry-run] all invariants hold; nothing written")
        print("RESULT: DRY-RUN-OK")
        return 0

    out = Path(args.out)
    tmp_docx.replace(out)
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
