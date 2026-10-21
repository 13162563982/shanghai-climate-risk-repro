"""WP7.5 gate G7: nine machine-checkable assertions on PAPER_MANUSCRIPT_v10.docx.

Run:
    & ".\\env\\run.ps1" tools\\_gate_g7.py

Prints one line per assertion and a final RESULT.  Read-only.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
import sys
import zipfile
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
FROZEN = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_FINAL.docx"
V10 = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v10.docx"
PLAN = DOCS / "_v10_edit_plan.csv"
FIGDIR = NEWROOT / "manuscript" / "figures"

FROZEN_SHA = "39240D38FCF71ADB72BEA285249AFE5757E0327F26253D48BE45FA899C772F14"
STRUCT = dict(paragraphs=409, tables=11, m_oMath=131, m_oMathPara=41, w_drawing=37)

# exact expected grids (stripped cell text)
EXPECT_T1 = {  # Table 1
    1: ["Historical", "24.2", "19.0", "21.5%"],
    2: ["SSP2-4.5 (+0.3 m SLR)", "33.4", "23.9", "28%"],
    3: ["SSP5-8.5 (+0.5 m SLR)", "40.3", "26.5", "34%"],
}
EXPECT_T2 = {  # Table 2
    1: ["Pudong", "6.0", "14.8", "0.40"],
    2: ["Yangpu", "2.6", "3.4", "0.77"],
    3: ["Minhang", "2.3", "8.0", "0.28"],
    4: ["Xuhui", "2.2", "4.0", "0.56"],
    5: ["Hongkou", "1.7", "2.0", "0.82"],
}
EXPECT_T3 = {  # Table 3 (columns 1..3; column 0 is the scenario label)
    1: ["491", "601", "692"],
    2: ["565", "675", "770"],
    3: ["643", "745", "840"],
}
EXPECT_T5 = {  # Table 5 (columns 1..3)
    1: ["354", "399", "457"],
    2: ["394", "441", "499"],
    3: ["435", "479", "534"],
}
EXPECT_T8 = {
    (3, 5): "21.1\u201328.2B", (4, 5): "18.7\u201331.7B", (5, 5): "22.6\u201325.8B",
    (6, 5): "22.7\u201327.6B", (7, 5): "23.1\u201326.5B", (8, 5): "22.1\u201328.7B",
    (13, 5): "596\u2013612", (14, 5): "590\u2013607", (17, 5): "576\u2013633",
    (20, 5): "397\u2013400",
    (13, 4): "601", (14, 4): "601", (17, 4): "601",
    (5, 6): "\u22126% to +6%", (15, 6): "\u22122% to +4%",
    (16, 6): "\u22120.1% to +2.6%", (20, 6): "\u22120.2% to +0.6%",
}
EXPECT_T8_KEEP = {  # cells that must NOT change
    (10, 6): "0%",
    (14, 6): "\u22121.8% to +1.1%",
    (2, 5): "21.5\u201328.6B",
    (9, 5): "22.2\u201328.4B",
    (18, 5): "225\u2013311",
}


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def load_extractor():
    spec = importlib.util.spec_from_file_location(
        "ext", NEWROOT / "tools" / "extract_manuscript_numbers.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ext"] = mod
    spec.loader.exec_module(mod)
    return mod


def load_disclosure_locs():
    """Paragraphs that receive a WP7.3 disclosure run (read from the rewriter)."""
    spec = importlib.util.spec_from_file_location(
        "rwmod", NEWROOT / "tools" / "rewrite_manuscript_v10.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rwmod"] = mod
    spec.loader.exec_module(mod)
    return set(mod.APPEND_SENTENCES.keys()), list(getattr(mod, "MOVE_PARAGRAPHS", []))


DISCLOSURE_LOCS, PARAGRAPH_MOVES = load_disclosure_locs()


def main() -> int:
    ext = load_extractor()
    fails, passes = [], []

    def check(name, ok, detail=""):
        (passes if ok else fails).append((name, detail))
        print("  [%s] %-52s %s" % ("PASS" if ok else "FAIL", name, detail))

    print("=== G7 gate on %s ===" % V10.name)
    check("G7-1a frozen document untouched", sha_file(FROZEN) == FROZEN_SHA,
          sha_file(FROZEN)[:16])
    check("G7-1b v10 exists", V10.is_file(),
          "%.2f MB" % (V10.stat().st_size / 1e6) if V10.is_file() else "missing")

    # --- structure
    _, c10 = ext.read_docx_stdlib(V10)
    ok = all(c10.get(k) == v for k, v in STRUCT.items())
    check("G7-2 structure invariants", ok, json.dumps({k: c10.get(k) for k in STRUCT}))

    # --- edit plan: NEW present, OLD absent
    with PLAN.open("r", encoding="utf-8-sig", newline="") as fh:
        plan = list(csv.DictReader(fh))
    e10, _ = ext.read_docx_stdlib(V10)
    ent10 = {e.ident: e.text for e in e10}
    eold, _ = ext.read_docx_stdlib(FROZEN)
    entold = {e.ident: e.text for e in eold}
    bad3 = []
    band = 0
    for r in plan:
        loc, old, new = r["loc_id"], r["old_text"], r["new_text"]
        if r["category"] == "BAND":
            band += 1
            continue
        t = ent10.get(loc)
        if t is None:
            bad3.append("%s missing" % loc)
            continue
        if new not in t:
            bad3.append("%s NEW %r absent" % (loc, new))
        if old in t:
            bad3.append("%s OLD %r still present" % (loc, old))
    check("G7-3 plan rows applied (NEW in / OLD out)", not bad3,
          "%d rows checked, %d band skipped%s" %
          (len(plan) - band, band, ("; " + "; ".join(bad3[:4])) if bad3 else ""))

    # --- explicit grids (columns 1..3 for Tables 3 and 5: column 0 is the label)
    bad4 = []
    for tid, table, expect, off in (("T0", "Table 1", EXPECT_T1, 0),
                                    ("T1", "Table 2", EXPECT_T2, 0),
                                    ("T2", "Table 3", EXPECT_T3, 1),
                                    ("T4", "Table 5", EXPECT_T5, 1)):
        for row, vals in expect.items():
            for i, want in enumerate(vals):
                col = i + off
                got = ent10.get("%s#r%dc%d" % (tid, row, col), "").strip()
                if got != want.strip():
                    bad4.append("%s r%dc%d got %r want %r" % (table, row, col, got, want.strip()))
    for (row, col), want in EXPECT_T8.items():
        got = ent10.get("T8#r%dc%d" % (row, col), "").strip()
        if got != want:
            bad4.append("Table 8 r%dc%d got %r want %r" % (row, col, got, want))
    for (row, col), want in EXPECT_T8_KEEP.items():
        got = ent10.get("T8#r%dc%d" % (row, col), "").strip()
        if got != want:
            bad4.append("Table 8 KEEP r%dc%d got %r want %r" % (row, col, got, want))
    check("G7-4 table grids exact", not bad4,
          "%d problems%s" % (len(bad4), (": " + "; ".join(bad4[:4])) if bad4 else ""))

    # --- figures
    bad5 = []
    with zipfile.ZipFile(V10) as zf:
        media = {n: hashlib.sha256(zf.read(n)).hexdigest()
                 for n in zf.namelist() if n.startswith("word/media/")}
        v10_parts = {n: hashlib.sha256(zf.read(n)).hexdigest() for n in zf.namelist()}
    with zipfile.ZipFile(FROZEN) as zf:
        frozen_parts = {n: hashlib.sha256(zf.read(n)).hexdigest() for n in zf.namelist()}
    with (DOCS / "_v10_figure_map.csv").open("r", encoding="utf-8-sig", newline="") as fh:
        fmap = list(csv.DictReader(fh))
    check("G7-5a media slot count 37 + map rows 37", len(media) == 37 and len(fmap) == 37,
          "media=%d map=%d" % (len(media), len(fmap)))
    for r in fmap:
        want = hashlib.sha256((FIGDIR / r["target_file"]).read_bytes()).hexdigest()
        got = media.get(r["media"])
        if got != want:
            bad5.append("%s(%s)" % (r["media"], r["target_file"]))
    check("G7-5b every media slot equals its target figure", not bad5,
          "%d/37 ok%s" % (37 - len(bad5), ("; bad " + ", ".join(bad5[:5])) if bad5 else ""))
    other = [n for n in frozen_parts
             if n not in media and n != "word/document.xml"
             and frozen_parts[n] != v10_parts.get(n)]
    check("G7-5c all non-media parts byte-identical", not other,
          ("changed: " + ", ".join(other[:5])) if other else "%d parts" % (len(frozen_parts) - 38))

    # --- token audit
    def tokens(text):
        return sorted(ext.norm_token(t) for t, _a, _b in ext.numeric_tokens(text))

    plan_locs = {r["loc_id"] for r in plan}
    plan_locs |= set(DISCLOSURE_LOCS)

    # paragraphs are compared as ORDERED LISTS after applying the same whole-
    # paragraph move that the rewriter performs (WP7.3b DA-heading move), so a
    # deliberate reordering is not mistaken for an unplanned edit.
    paras_old = [e.text for e in eold if e.kind == "paragraph"]
    paras_new = [e.text for e in e10 if e.kind == "paragraph"]
    moved_old = list(paras_old)
    for mv_src, mv_dst, _why in PARAGRAPH_MOVES:
        i = int(mv_src[1:])
        j = int(mv_dst[1:])
        blk = moved_old.pop(i)
        moved_old.insert(j - 1 if j > i else j, blk)
    head_idx = [i for i, t in enumerate(paras_new) if t.strip() == "Data Availability Statement"]
    ok6c = (len(head_idx) == 1 and head_idx[0] + 1 < len(paras_new)
            and paras_new[head_idx[0] + 1].strip().startswith("Data availability.")
            and len(PARAGRAPH_MOVES) >= 1)
    check("G7-6c DA heading directly precedes its body text", ok6c,
          ("heading at P%d, body follows" % head_idx[0]) if ok6c
          else ("headings=%s" % head_idx))

    extra_changed = []
    for i, (a, b) in enumerate(zip(moved_old, paras_new)):
        ident = "P%d" % i
        if a == b or ident in plan_locs:
            continue
        extra_changed.append(ident)
    if len(moved_old) != len(paras_new):
        extra_changed.append("paragraph-count-mismatch")
    cells_old = {k: v for k, v in entold.items() if not k.startswith("P")}
    cells_new = {k: v for k, v in ent10.items() if not k.startswith("P")}
    missing_idents = [k for k in cells_old if k not in cells_new]
    for ident, told in cells_old.items():
        if ident in plan_locs or ident not in cells_new:
            continue
        if told != cells_new[ident]:
            extra_changed.append(ident)
    extra_tok = []
    for i, (a, b) in enumerate(zip(moved_old, paras_new)):
        ident = "P%d" % i
        if ident in plan_locs or a == b:
            continue
        if tokens(a) != tokens(b):
            extra_tok.append(ident)
    for ident in cells_old:
        if ident in plan_locs or ident not in cells_new:
            continue
        if tokens(cells_old[ident]) != tokens(cells_new[ident]):
            extra_tok.append(ident)
    check("G7-6 no unplanned element changed",
          not extra_changed and not missing_idents,
          "%d element texts changed outside the plan%s" %
          (len(extra_changed), (": " + ", ".join(extra_changed[:6])) if extra_changed else ""))
    check("G7-6b no unplanned token change", not extra_tok,
          (", ".join(extra_tok[:6])) if extra_tok else "token multisets stable")

    # --- G7-7: independent re-run of the WP7.1 extractor on v10
    v10tab = DOCS / "_v10断言" / "_数字变更对照表.md"
    if not v10tab.exists():
        check("G7-7 extractor re-run present", False, "docs/_v10断言 missing")
    else:
        txt = v10tab.read_text(encoding="utf-8")
        sec = re.compile(r"^### (?:段落 )?(P\d+|T\d+#r\d+c\d+)\s*$")
        plan_pairs = {(r["loc_id"], r["old_text"]) for r in plan}
        plan_locs_all = {r["loc_id"] for r in plan} | DISCLOSURE_LOCS
        loc, bad7, n_change = None, [], 0
        for line in txt.splitlines():
            m = sec.match(line)
            if m:
                loc = m.group(1)
                continue
            if loc and line.startswith("| `"):
                parts = [p.strip() for p in line.strip().strip("|").split("|")]
                if len(parts) < 6:
                    continue
                tok, status = parts[0].strip("`"), parts[3]
                if status == "CHANGE":
                    n_change += 1
                    if (loc, tok) in plan_pairs:
                        continue
                    # a residual CHANGE row is legitimate only when the printed
                    # token is still in the text (precision NO-OP or band row)
                    if tok not in ent10.get(loc, ""):
                        bad7.append("%s/%s vanished but not planned" % (loc, tok))
        check("G7-7a structure line in v10 extraction present",
              "| 409 |" in txt and "131 / 41 / 37" in txt,
              "段 409 / m:oMath 131 / oMathPara 41 / drawing 37")
        check("G7-7b unmapped tokens == 0 in v10", "| 0 |" in txt)
        check("G7-7c every residual CHANGE is a planned edit", not bad7,
              "%d residual CHANGE rows, all planned%s" %
              (n_change, ("; " + "; ".join(bad7[:5])) if bad7 else ""))

    print("")
    print("PASS %d / FAIL %d" % (len(passes), len(fails)))
    if fails:
        print("RESULT: G7-FAIL")
        return 1
    print("RESULT: G7-PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
