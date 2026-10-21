# -*- coding: utf-8 -*-
"""WP11.5 gate G12 - the alignment audit as a re-runnable regression gate.

Asserts that the manuscript in the repository is aligned with the frozen model
outputs, that the pre-audit deliverable (v11) is preserved byte-exact, and that
the correction set has not drifted.

  G12-1   FINAL / v10 / v11 hashes unchanged
  G12-2   v12 structure invariants (409 paragraphs / 11 tables / 131 oMath /
          41 oMathPara / 37 drawings / 49 zip parts)
  G12-3   v12 differs from v11 only in word/document.xml
  G12-4   the <w:t> run count is preserved (no text was merged or dropped)
  G12-5   all twelve text corrections are present in v12 (new in, old out)
  G12-6   the v12 full alignment check reports zero findings
  G12-7   the v11 full alignment check reports exactly the 15 known findings
  G12-8   every MODEL / PARAM / DATA token is classified and bound
  G12-9   all 37 embedded figures are byte-identical to their source render
  G12-10  the v12 correction report exists and records 12 text + 6 style edits
  G12-11  no body prose is left carrying a heading style

Exit code 0 only when every assertion passes.

USAGE
-----
  env\\run.ps1 tools\\_gate_g12.py
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
MAN = NEWROOT / "manuscript"

V11 = MAN / "PAPER_MANUSCRIPT_v11.docx"
V12 = MAN / "PAPER_MANUSCRIPT_v12.docx"
V10 = MAN / "PAPER_MANUSCRIPT_v10.docx"
FINAL = MAN / "PAPER_MANUSCRIPT_FINAL.docx"

V11_SHA = "7417FDE618D6C5114628B28C76C7E676141415EFA7BF50016BB13C2D472523CC"
V10_SHA = "40E306B03E2E54913CACF37CF62007226487BC3F879CE5ECADC186075BD1AD91"
FINAL_SHA = "39240D38FCF71ADB72BEA285249AFE5757E0327F26253D48BE45FA899C772F14"
STRUCT = dict(paragraphs=409, tables=11, m_oMath=131, m_oMathPara=41, w_drawing=37)
N_PARTS = 49
W_T_RUNS = 1273
V11_KNOWN_FINDINGS = 15

MINUS = "\u2212"
MUST_APPLY = [
    ("P42", "491\u2013692, 565\u2013770 and 643\u2013840",
     "490\u2013689, 564\u2013768 and 641\u2013837"),
    ("P93", "1.0324", "1.05 (SSP2-4.5)"),
    ("P93", "1.0442", "1.10 (SSP5-8.5)"),
    ("T9#r15c2", "1.0324", "1.05"),
    ("T9#r16c2", "1.0442", "1.10"),
    ("T8#r20c6", MINUS + "0.4% to +0.2%", MINUS + "0.2% to +0.6%"),
    ("P66", MINUS + "0.4% to +0.2%", MINUS + "0.2% to +0.6%"),
    ("T8#r9c6", MINUS + "8% to +17%", MINUS + "8% to +18%"),
    ("P75", "over the 2011\u20132023 historical period", "across scenarios"),
    ("P49", "the calibrated dependence target used in the paired projection",
     "an empirical rank correlation of"),
    ("P9", "approximately unity", "ratio of 0.9999"),
    ("P17", "calibration fit ratio of approximately unity",
     "calibration fit ratio of 0.9999"),
    ("P251", "pred/obs \u2248 1.00 for 1995", "pred/obs = 0.9999 for 1995"),
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
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))
        print("  [%s] %-46s %s" % ("PASS" if ok else "FAIL", name, detail))

    print("=== G12 alignment gate ===")

    # G12-1 baselines
    check("G12-1a FINAL untouched", sha256(FINAL) == FINAL_SHA,
          sha256(FINAL)[:16])
    check("G12-1b v10 untouched", sha256(V10) == V10_SHA, sha256(V10)[:16])
    check("G12-1c v11 untouched", sha256(V11) == V11_SHA, sha256(V11)[:16])
    check("G12-1d v12 exists", V12.is_file(),
          "%d B %s" % (V12.stat().st_size, sha256(V12)[:16]) if V12.is_file()
          else "missing")

    ext = load("ext", r"tools\extract_manuscript_numbers.py")

    # G12-2 structure
    e12, c12 = ext.read_docx_stdlib(V12)
    bad = {k: (c12.get(k), v) for k, v in STRUCT.items() if c12.get(k) != v}
    with zipfile.ZipFile(V12) as zf:
        n_parts = len(zf.namelist())
    check("G12-2 structure invariants", not bad and n_parts == N_PARTS,
          "%s, %d parts" % (json.dumps(c12), n_parts))

    # G12-3 only document.xml differs
    with zipfile.ZipFile(V11) as zf:
        p11 = {n: hashlib.sha256(zf.read(n)).hexdigest() for n in zf.namelist()}
    with zipfile.ZipFile(V12) as zf:
        p12 = {n: hashlib.sha256(zf.read(n)).hexdigest() for n in zf.namelist()}
    other = [n for n in p11 if n != "word/document.xml" and p11[n] != p12.get(n)]
    check("G12-3 only document.xml differs", not other, other or "48 parts equal")

    # G12-4 run count
    with zipfile.ZipFile(V12) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    runs = xml.count("<w:t>") + xml.count("<w:t ")
    check("G12-4 <w:t> run count preserved", runs == W_T_RUNS, str(runs))

    # G12-5 corrections present
    ent = {e.ident: e.text for e in e12}
    misses = []
    for loc, new, old in MUST_APPLY:
        txt = ent.get(loc, "")
        if new not in txt or old in txt:
            misses.append("%s(new=%s,old_gone=%s)"
                          % (loc, new in txt, old not in txt))
    check("G12-5 all corrections present", not misses,
          "%d/%d sites" % (len(MUST_APPLY) - len(misses), len(MUST_APPLY))
          if not misses else "; ".join(misses))

    # G12-6 / G12-7 full alignment on v12 and v11
    chk = load("chk", r"tools\_wp11_check.py")
    truth = {r["metric_id"]: r for r in chk.load_csv(DOCS / "_wp11_真值表.csv")}

    def findings(map_csv: Path, docx: Path, figs: Path):
        chk.DOCX_PATH = docx
        chk.FIGCSV = figs
        mapping = chk.load_csv(map_csv)
        rows = (chk.check_numeric(truth, mapping) + chk.check_tables(truth)
                + chk.check_table_b1() + chk.check_figures()
                + chk.check_assertions(truth)
                + chk.check_consistency(truth, mapping))
        bad = [r for r in rows if r["status"] in
               ("MISMATCH", "NO-METRIC", "NO-SOURCE", "MISSING", "NO-NUMBER")]
        return len(rows), bad

    n12, bad12 = findings(DOCS / "_wp11_v12映射表.csv", V12,
                          DOCS / "_wp11_v12_图件清单.csv")
    check("G12-6 v12 alignment clean", not bad12,
          "%d checks, %d findings" % (n12, len(bad12)))
    for r in bad12[:6]:
        print("        %s %s %r %s" % (r["status"], r["row_id"], r["token"],
                                       r["detail"][:70]))

    n11, bad11 = findings(DOCS / "_wp11映射表.csv", V11,
                          DOCS / "_wp11_图件清单.csv")
    check("G12-7 v11 baseline findings intact",
          len(bad11) == V11_KNOWN_FINDINGS,
          "%d checks, %d findings (expected %d)"
          % (n11, len(bad11), V11_KNOWN_FINDINGS))

    # G12-8 classification completeness
    with io.open(DOCS / "_wp11_v12映射表.csv", encoding="utf-8", newline="") as fh:
        mapped = list(csv.DictReader(fh))
    unclass = [r for r in mapped if r["class"] == "UNCLASSIFIED"]
    verified = [r for r in mapped if r["class"] in ("MODEL", "PARAM", "DATA")]
    check("G12-8 every token classified and bound",
          not unclass and len(verified) >= 580,
          "%d tokens, %d verified, %d unclassified"
          % (len(mapped), len(verified), len(unclass)))

    # G12-9 figures
    figdir = NEWROOT / "manuscript" / "figures"
    figs = chk.load_csv(DOCS / "_wp11_v12_图件清单.csv")
    badfig = [f["fig_no"] for f in figs
              if sha256(figdir / f["t10_file"]) != f["media_sha"]]
    check("G12-9 figures byte-identical to renders", not badfig,
          "%d/37 ok" % (37 - len(badfig)))

    # G12-10 correction report
    rep_path = DOCS / "_v12_改写报告.json"
    ok_rep = False
    detail = "missing"
    if rep_path.is_file():
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
        applied = [e for e in rep.get("edits", []) if e.get("status") == "planned"]
        ok_rep = (len(applied) == 12
                   and len(rep.get("style_edits", [])) == 6
                   and rep.get("other_parts_changed") == [])
        detail = "%d text + %d style edits, output %s" % (
            len(applied), len(rep.get("style_edits", [])),
            (rep.get("output") or {}).get("sha256", "-")[:16])
    check("G12-10 correction report", ok_rep, detail)

    # G12-11 heading-styled prose (A3)
    heading_styles = {"1", "2", "3", "4", "5"}
    styled = [e.ident for e in e12
              if e.kind == "paragraph" and e.style in heading_styles
              and len(e.text.strip()) > 120]
    check("G12-11 no heading-styled body prose", not styled,
          styled or "0 long paragraphs carry a heading style")

    n_fail = sum(1 for _, ok, _ in checks if not ok)
    print("")
    print("PASS %d / FAIL %d" % (len(checks) - n_fail, n_fail))
    result = {"generated": __import__("datetime").datetime.now().isoformat(
        timespec="seconds"),
        "checks": [{"name": n, "pass": ok, "detail": d} for n, ok, d in checks],
        "verdict": "PASS" if n_fail == 0 else "FAIL"}
    (DOCS / "_gate_g12_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print("RESULT: %s" % ("G12-PASS" if n_fail == 0 else "G12-FAIL"))
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
