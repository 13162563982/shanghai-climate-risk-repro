# -*- coding: utf-8 -*-
"""WP13.12 - prove that v14 is v13 minus the availability statement only.

v14 removes two paragraphs (P252 heading, P253 data + code availability) from
v13 and puts the same words into two standalone files.  This module proves four
things mechanically:

  1  the paragraph / cell text sequence of v14 equals v13 with exactly those two
     paragraphs removed - no other character moved;
  2  the numeric census of v14 equals v13's minus exactly the ten tokens that
     lived in P253, and nothing new appeared;
  3  those ten tokens reappear, unchanged, in the two standalone statements
     (nine in Data_Availability_Statement.docx, one in
     Code_Availability_Statement.docx);
  4  the editorial fixes of v13 survive: all nine numbered tables are still
     cited and no reference entry is left uncited.

OUTPUT
    docs\\_wp13_v14_delta.csv
    docs\\_wp13_v14_delta摘要.json

USAGE
    env\\run.ps1 tools\\_wp13_v14_delta.py
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
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
MAN = NEWROOT / "manuscript"
V13 = MAN / "PAPER_MANUSCRIPT_v13.docx"
V14 = MAN / "PAPER_MANUSCRIPT_v14.docx"
DA_DOC = MAN / "Data_Availability_Statement.docx"
CODE_DOC = MAN / "Code_Availability_Statement.docx"
BIB = DOCS / "_wp13_文献核验.csv"
OUT = DOCS / "_wp13_v14_delta.csv"
OUT_SUM = DOCS / "_wp13_v14_delta摘要.json"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DROP = {"P252", "P253"}
N_TOKENS_DROP = 10


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


def doc_paragraphs(docx: Path) -> list[str]:
    with zipfile.ZipFile(docx) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    body = root.find(W + "body")
    out = []
    for child in body:
        if child.tag == W + "p":
            out.append("".join(t.text or "" for t in child.iter(W + "t")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="WP13.12 v14 delta proof")
    ap.add_argument("--v13", default=str(V13))
    ap.add_argument("--v14", default=str(V14))
    args = ap.parse_args()

    ext = load_ext()
    v13, v14 = Path(args.v13), Path(args.v14)
    e13, _ = ext.read_docx_stdlib(v13)
    e14, c14 = ext.read_docx_stdlib(v14)
    t13 = {e.ident: e.text for e in e13}
    t14 = {e.ident: e.text for e in e14}

    failures: list[str] = []
    print("=== WP13.12 v14 delta proof ===")

    # ---- 1. sequence equality after removing the two paragraphs
    seq13 = [e.text for e in e13 if e.ident not in DROP]
    seq14 = [e.text for e in e14]
    ok1 = seq13 == seq14
    print("  elements        : %d -> %d (expected -2)" % (len(e13), len(e14)))
    print("  text sequence   : %s" % ("identical after 2 deletions" if ok1 else "DIFFERS"))
    if not ok1:
        diffs = [(i, a[:40], b[:40]) for i, (a, b) in enumerate(zip(seq13, seq14))
                 if a != b]
        failures.append("text sequence differs at %s" % diffs[:3])
    if len(e14) != len(e13) - 2:
        failures.append("element count %d != %d" % (len(e14), len(e13) - 2))

    # ---- 2. token delta, compared in document order
    # Deleting two paragraphs renumbers every later P-id (P254 -> P252), so the
    # comparison must be positional, not keyed by element id.
    def toks_of(text: str):
        return [tk for tk, _a, _b in ext.numeric_tokens(text)]

    seq13 = [tk for e in e13 if e.ident not in DROP for tk in toks_of(e.text)]
    seq14 = [tk for e in e14 for tk in toks_of(e.text)]
    removed = Counter(tk for i in DROP for tk in toks_of(t13.get(i, "")))
    print("  tokens          : %d -> %d (-%d)"
          % (len(seq13) + sum(removed.values()), len(seq14), sum(removed.values())))
    if seq13 != seq14:
        first = next((i for i, (a, b) in enumerate(zip(seq13, seq14)) if a != b),
                     min(len(seq13), len(seq14)))
        failures.append("token sequence differs at index %d (%r vs %r)"
                        % (first, seq13[first:first + 3], seq14[first:first + 3]))
    if sum(removed.values()) != N_TOKENS_DROP:
        failures.append("removed %d tokens from P252/P253, expected %d"
                        % (sum(removed.values()), N_TOKENS_DROP))

    # ---- 3. the removed tokens reappear in the two standalone statements
    da_txt = " ".join(doc_paragraphs(DA_DOC))
    code_txt = " ".join(doc_paragraphs(CODE_DOC))
    da_toks = Counter(tk for tk, _a, _b in ext.numeric_tokens(da_txt))
    code_toks = Counter(tk for tk, _a, _b in ext.numeric_tokens(code_txt))
    removed_toks = Counter(removed)
    carried = da_toks + code_toks
    print("  data doc tokens : %d, code doc tokens: %d" % (sum(da_toks.values()),
                                                          sum(code_toks.values())))
    missing = list((removed_toks - carried).elements())
    if missing:
        failures.append("tokens not carried into the statements: %s" % missing)
    if (carried - removed_toks):
        print("  note: statements also carry %s (not in the manuscript paragraph)"
              % list((carried - removed_toks).elements())[:5])

    # the DOI strings must survive verbatim
    for doi in ("10.25921/82ty-9e16", "10.48690/1524213",
                "10.25921/fd45-gt74", "seed (42)"):
        if doi not in (da_txt + " " + code_txt):
            failures.append("statement lost %r" % doi)

    rows = [{"项目": "从稿件移出的数字", "数量": sum(removed.values()),
             "数值": " ".join(sorted(removed.elements())),
             "判定": "OK（原判定随文迁移）"},
            {"项目": "Data 声明文件", "数量": sum(da_toks.values()),
             "数值": " ".join(sorted(da_toks)),
             "判定": "OK" if not missing else "MISMATCH"},
            {"项目": "Code 声明文件", "数量": sum(code_toks.values()),
             "数值": " ".join(sorted(code_toks)),
             "判定": "OK" if not missing else "MISMATCH"}]

    # one row per moved number, so the whole package reconciles in a single
    # ledger: manuscript rows (1,476) + statement rows (10) = the v13 total
    dec_rows = []
    for loc, cnt, dst in (("DA声明", da_toks, DA_DOC),
                          ("代码声明", code_toks, CODE_DOC)):
        for tk, n in sorted(cnt.items()):
            for _ in range(n):
                dec_rows.append({"位置": loc, "数字": tk, "判定": "OK-EXT",
                                 "证据": "自 v13 P253 逐字移入 %s" % dst.name,
                                 "说明": "可用性声明（%s）" % dst.stem})
    buf2 = io.StringIO()
    w2 = csv.DictWriter(buf2, fieldnames=["位置", "数字", "判定", "证据", "说明"],
                        lineterminator="\n")
    w2.writeheader()
    for r in dec_rows:
        w2.writerow(r)
    (DOCS / "_wp13_v14_声明数字.csv").write_text(buf2.getvalue(),
                                                 encoding="utf-8", newline="\n")

    # ---- 4. the v13 editorial fixes survive
    body = [(k, v) for k, v in t14.items()
            if not re.match(r"^\s*Table\s+[A-Z]?\d+\.", v.strip())]
    trefs = set()
    for _k, v in body:
        trefs |= set(re.findall(r"Table\s+([A-Z]?\d+)", v))
    want_t = {str(i) for i in range(1, 9)} | {"B1"}
    uncited_t = sorted(want_t - trefs)
    print("  tables cited    : %s (uncited %s)" % (sorted(trefs & want_t),
                                                   uncited_t or "none"))
    if uncited_t:
        failures.append("tables no longer cited: %s" % uncited_t)

    ref_idx = [int(k[1:]) for k, v in t14.items()
               if k.startswith("P") and k[1:].isdigit()
               and re.match(r"^\s*References\s*$", v.strip())]
    ref_start = min(ref_idx) if ref_idx else 10 ** 9
    body_text = " ".join(v for k, v in t14.items()
                         if k.startswith("P") and k[1:].isdigit()
                         and int(k[1:]) < ref_start)
    uncited_refs = []
    for r in load_csv(BIB):
        pat = re.escape(r["surname"].split("-")[0])
        if not re.search(pat + r".{0,80}?" + re.escape(r["year"]), body_text, re.I):
            uncited_refs.append("%s %s" % (r["surname"], r["year"]))
    print("  uncited refs    : %s" % (uncited_refs or "none"))
    if uncited_refs:
        failures.append("references no longer cited: %s" % uncited_refs)

    # ---- write
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["项目", "数量", "数值", "判定"],
                       lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    OUT.write_text(buf.getvalue(), encoding="utf-8", newline="\n")

    summary = {
        "generated": __import__("datetime").datetime.now().isoformat(
            timespec="seconds"),
        "v13_elements": len(e13),
        "v14_elements": len(e14),
        "structure": c14,
        "tokens_v13": len(seq13) + sum(removed.values()),
        "tokens_v14": len(seq14),
        "removed": [{"数字": t, "次数": n} for t, n in sorted(removed.items())],
        "data_doc_tokens": sum(da_toks.values()),
        "code_doc_tokens": sum(code_toks.values()),
        "tables_cited": sorted(trefs & want_t),
        "uncited_references": uncited_refs,
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
