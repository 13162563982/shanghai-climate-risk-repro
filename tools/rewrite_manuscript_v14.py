# -*- coding: utf-8 -*-
"""WP13.10 - v13 -> v14: move the availability statements out of the manuscript.

The author wants the manuscript to contain paper content only, with the data and
code availability statements supplied as separate files.  This module therefore
deletes exactly two body paragraphs from v13:

    P252  the heading "Data Availability Statement"
    P253  the paragraph "Data availability. ... Code availability. ..."

and changes nothing else.  The text of those two paragraphs is reproduced
verbatim in

    manuscript\\Data_Availability_Statement.docx
    manuscript\\Code_Availability_Statement.docx

built by tools/make_declaration_docs.py from the same source strings, so the
statement cannot drift between the manuscript and the standalone files.

Invariants asserted before the file is written
  * v14 has 407 body paragraphs (was 409), the other structure counts unchanged
    (11 tables / 131 m:oMath / 41 m:oMathPara / 37 drawings / 49 package parts);
  * the <w:t> run count drops by exactly the 2 runs of the deleted paragraphs
    (1,273 -> 1,271);
  * the paragraph/cell text sequence of v14 equals v13 with those two removed -
    i.e. no other character moved;
  * only word/document.xml differs from v13.

USAGE
    env\\run.ps1 tools\\rewrite_manuscript_v14.py              # dry run
    env\\run.ps1 tools\\rewrite_manuscript_v14.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
MAN = NEWROOT / "manuscript"
SRC = MAN / "PAPER_MANUSCRIPT_v13.docx"
OUT = MAN / "PAPER_MANUSCRIPT_v14.docx"
REPORT = DOCS / "_v14_改写报告.json"

SRC_BYTES = 28193192
SRC_SHA = "380DE7EB7C6418319C2E20D82C8F09F55BB2E881BA2ABDBDC3808FFE84E9FB0A"
V12_SHA = "F86428EDBF44C5465A880AFD"
V11_SHA = "7417FDE618D6C5114628B28C76C7E676141415EFA7BF50016BB13C2D472523CC"
V10_SHA = "40E306B03E2E54913CACF37CF62007226487BC3F879CE5ECADC186075BD1AD91"
FINAL_SHA = "39240D38FCF71ADB72BEA285249AFE5757E0327F26253D48BE45FA899C772F14"

DROP = ["P252", "P253"]
STRUCT_AFTER = dict(paragraphs=407, tables=11, m_oMath=131, m_oMathPara=41,
                    w_drawing=37)
W_T_AFTER = 1271
N_PARTS = 49


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
    ap = argparse.ArgumentParser(description="WP13.10 v13 -> v14")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    src = Path(args.src)
    print("=== WP13.10 v14 rewrite (availability statements moved out) ===")
    print("  source : %s (%d B)" % (src.name, src.stat().st_size))

    ok = True
    for name, p, want in (("v13", src, SRC_SHA),
                          ("v12", MAN / "PAPER_MANUSCRIPT_v12.docx", V12_SHA),
                          ("v11", MAN / "PAPER_MANUSCRIPT_v11.docx", V11_SHA),
                          ("v10", MAN / "PAPER_MANUSCRIPT_v10.docx", V10_SHA),
                          ("FINAL", MAN / "PAPER_MANUSCRIPT_FINAL.docx", FINAL_SHA)):
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
    before = [(e.ident, e.text) for e in ext.read_docx_stdlib(src)[0]]
    before_map = dict(before)
    spans = []
    removed_text = {}
    for loc in DROP:
        i = int(loc[1:])
        _n, s, e = idx.paras[i]
        spans.append((s, e))
        removed_text[loc] = xml[s:e]
        print("  [DROP] %-5s %d chars, %d run(s), text starts %r"
              % (loc, e - s,
                 xml[s:e].count("<w:t>") + xml[s:e].count("<w:t "),
                 before_map.get(loc, "")[:60]))
    spans.sort()
    if spans[0][1] != spans[1][0]:
        print("  ! the two paragraphs are not adjacent; refusing to splice")
        print("RESULT: ABORT")
        return 1
    new_xml = xml[:spans[0][0]] + xml[spans[1][1]:]

    tmp = DOCS / "_v14_tmp.docx"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
            tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = new_xml.encode("utf-8")
            zout.writestr(item, data)

    _e, c14 = ext.read_docx_stdlib(tmp)
    bad = {k: (c14.get(k), v) for k, v in STRUCT_AFTER.items() if c14.get(k) != v}
    w_old = xml.count("<w:t>") + xml.count("<w:t ")
    w_new = new_xml.count("<w:t>") + new_xml.count("<w:t ")
    with zipfile.ZipFile(tmp) as zf:
        parts2 = {n: hashlib.sha256(zf.read(n)).hexdigest() for n in zf.namelist()}
    other = [n for n in parts if n != "word/document.xml" and parts[n] != parts2.get(n)]

    after = [(e.ident, e.text) for e in _e]
    expect = [x for x in before if x[0] not in DROP]
    seq_ok = [t for _i, t in after] == [t for _i, t in expect]
    diff_n = sum(1 for a, b in zip(after, expect) if a[1] != b[1])

    print("  structure : %s" % ("ok" if not bad else bad))
    print("  <w:t> runs: %d -> %d (expected %d)" % (w_old, w_new, W_T_AFTER))
    print("  elements  : %d -> %d" % (len(before), len(after)))
    print("  text sequence identical apart from the two deletions: %s (%d diffs)"
          % (seq_ok, diff_n))
    print("  other parts changed: %s" % (other or "none"))
    print("  package parts: %d (expected %d)" % (len(parts2), N_PARTS))

    good = (not bad and not other and w_new == W_T_AFTER
            and len(parts2) == N_PARTS and seq_ok)
    if not good:
        print("RESULT: ABORT (invariant failure)")
        tmp.unlink(missing_ok=True)
        return 1

    rep = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "source": {"name": src.name, "bytes": src.stat().st_size, "sha256": SRC_SHA},
        "dropped": DROP,
        "removed_text": {k: "".join(
            __import__("re").findall(r"<w:t[^>]*>([^<]*)</w:t>", v))
            for k, v in removed_text.items()},
        "structure": c14,
        "w_t_runs": [w_old, w_new],
        "elements": [len(before), len(after)],
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
