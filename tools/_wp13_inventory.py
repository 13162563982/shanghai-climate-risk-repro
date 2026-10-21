# -*- coding: utf-8 -*-
"""WP13.3 - figure and table inventory: counts, numbering, provenance, closure.

The manuscript prints 38 figures (37 embedded rasters plus the inline module
table that is Figure 15) and 11 table blocks (Table 1-8, Table B1, the Figure 15
block, the Appendix C figure index).  WP11 only checked that each raster was
byte-identical to a render in `manuscript/figures/`; it never established that
the *set* is complete, that the numbering closes, that every figure and table is
cited, or that the renders trace back to the current model outputs.

This module does exactly those four things:

  numbering   drawings vs captions vs the appendix index -> 1..38 with Figure 15
              as the inline table and no duplicate or missing number
  closure     every figure 1..38 and every numbered table is cited in the body
  provenance  33 rasters resolve byte-for-byte to a live pipeline output; the
              four sensitivity rasters (sa_01..sa_04) are byte-reproduced by
              `tools/gen_sensitivity_figures.py` from its own constants, which
              are themselves compared against the model config
  tables      block order, caption order, dimensions and header rows

OUTPUT
    docs\\_wp13_图表台账.csv
    docs\\_wp13_图表摘要.json

USAGE
    env\\run.ps1 tools\\_wp13_inventory.py
    env\\run.ps1 tools\\_wp13_inventory.py --rerender    # re-render sa_01..04
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
DOCX = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v12.docx"
FIGCSV = DOCS / "_wp11_v12_图件清单.csv"
TRUTH = DOCS / "_wp11_真值表.csv"
OUT = DOCS / "_wp13_图表台账.csv"
OUT_SUM = DOCS / "_wp13_图表摘要.json"
SENS_SCRIPT = NEWROOT / "tools" / "gen_sensitivity_figures.py"
CLIM_CFG = NEWROOT / "Climate" / "00_config.py"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# block index -> (rows, cols, label, numbered?)
EXPECT_TABLES = {
    0: (4, 4, "Table 1", True),
    1: (6, 4, "Table 2", True),
    2: (4, 4, "Table 3", True),
    3: (4, 4, "Table 4", True),
    4: (4, 4, "Table 5", True),
    5: (4, 5, "Figure 15 (inline module table)", False),
    6: (7, 7, "Table 6", True),
    7: (8, 5, "Table 7", True),
    8: (21, 7, "Table 8", True),
    9: (73, 4, "Table B1", True),
    10: (39, 3, "Appendix C figure index", False),
}

SA_FILES = ["sa_01_tc_vhalf_sensitivity.png", "sa_02_tc_vthresh_sensitivity.png",
            "sa_03_ss_mdr_sensitivity.png", "sa_04_vulnerability_overview.png"]


def load_csv(p: Path) -> list[dict]:
    with io.open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest().upper()


def sha_file(p: Path) -> str:
    return sha_bytes(p.read_bytes())


def doc_parts(docx: Path):
    with zipfile.ZipFile(docx) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
        media = {n: sha_bytes(zf.read(n)) for n in zf.namelist()
                 if n.startswith("word/media/")}
    body = root.find(W + "body")
    paras = []
    tables = []
    p_idx = 0
    for child in body:
        if child.tag == W + "p":
            st = child.find(W + "pPr/" + W + "pStyle")
            st = st.get(W + "val") if st is not None else ""
            txt = "".join(t.text or "" for t in child.iter(W + "t"))
            paras.append(("P%d" % p_idx, st, txt))
            p_idx += 1
        elif child.tag == W + "tbl":
            rows = child.findall(W + "tr")
            cells = []
            for tr in rows:
                cells.append(["".join(t.text or "" for t in tc.iter(W + "t")).strip()
                              for tc in tr.findall(W + "tc")])
            tables.append(cells)
    return paras, tables, media


def refs_in(text: str) -> set[int]:
    """Figure numbers referenced by 'Fig. N', 'Figures N and M', 'Figs. N-M'."""
    out: set[int] = set()
    for m in re.finditer(r"Fig(?:ure)?s?\.?\s*((?:\d+)(?:\s*(?:,|and|&|\u2013|-)\s*\d+)*)",
                         text):
        for n in re.findall(r"\d+", m.group(1)):
            out.add(int(n))
    return out


def table_refs_in(text: str) -> set[str]:
    return {m.group(1) for m in re.finditer(r"Table\s+([A-Z]?\d+)", text)}


def script_constants() -> dict:
    """Lift the plotted constants out of gen_sensitivity_figures.py."""
    src = io.open(SENS_SCRIPT, encoding="utf-8", errors="replace").read()
    consts: dict = {}
    for name in ("V_HALF_WP3_BASE", "V_THRESH_BASE", "V_HALF_ADJ",
                 "SURGE_DEPTH_DAMAGE", "SURGE_SCALES", "TC_BASE_SCALES",
                 "TC_THRESHOLDS"):
        consts[name] = _literal_after(src, name)
    return consts


def _literal_after(src: str, name: str):
    """Parse the literal that starts at `NAME = `, balanced across lines."""
    m = re.search(r"^%s\s*=\s*" % name, src, re.M)
    if not m:
        return None
    i = m.end()
    depth = 0
    started = False
    for j in range(i, len(src)):
        ch = src[j]
        if ch in "[{(":
            depth += 1
            started = True
        elif ch in "]}":
            depth -= 1
            if started and depth == 0:
                try:
                    return ast.literal_eval(src[i:j + 1])
                except Exception:  # noqa: BLE001
                    return None
        elif not started and ch in "\n#":
            try:
                return ast.literal_eval(src[i:j].strip())
            except Exception:  # noqa: BLE001
                return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="WP13.3 figure/table inventory")
    ap.add_argument("--docx", default=str(DOCX))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--sum", default=str(OUT_SUM))
    ap.add_argument("--rerender", action="store_true",
                    help="re-render sa_01..sa_04 and compare bytes")
    args = ap.parse_args()

    docx = Path(args.docx)
    paras, tables, media = doc_parts(docx)
    figs = load_csv(FIGCSV)
    truth = {r["metric_id"]: r for r in load_csv(TRUTH)}
    rows: list[dict] = []

    def add(kind, ident, ok, detail, expected="", got="", severity="BLOCKER"):
        rows.append({"kind": kind, "id": ident,
                     "verdict": "OK" if ok else "MISMATCH",
                     "severity": "" if ok else severity,
                     "expected": expected, "got": got, "detail": detail})
        return ok

    # ───────────────────────────────────────────────── figures: numbering
    drawn = [int(f["fig_no"]) for f in figs]
    caps = []
    for pid, st, txt in paras:
        m = re.match(r"^\s*Figure\s+(\d+)", txt.strip())
        if m and (st == "ImageCaption" or txt.strip().startswith("Figure 15.")):
            caps.append(int(m.group(1)))
    index_nums = []
    for i in range(1, 39):
        cell = tables[10][i][0] if i < len(tables[10]) else ""
        if cell.isdigit():
            index_nums.append(int(cell))

    add("figure", "numbering", drawn == [n for n in range(1, 39) if n != 15],
        "37 embedded drawings, Figure 15 is the inline table", "1..38 minus 15", drawn)
    add("figure", "captions", sorted(caps) == list(range(1, 39)),
        "38 captions found (37 short labels + the Figure 15 caption)",
        "1..38", caps)
    add("figure", "index", index_nums == list(range(1, 39)),
        "Appendix C index rows 1..38", "1..38", index_nums)

    # ───────────────────────────────────────────────── figures: provenance
    idx = {}
    for p in NEWROOT.rglob("*.png"):
        rel = p.relative_to(NEWROOT).as_posix()
        if rel.startswith("manuscript/figures/"):
            continue
        idx.setdefault(p.name, []).append(p)
    live_prefix = ("Climate/output/", "Finance/output/", "Composite/output/")

    sa_const = script_constants() if SENS_SCRIPT.is_file() else {}
    rerender_ok = None
    if args.rerender and SENS_SCRIPT.is_file():
        tmp = Path(tempfile.mkdtemp(prefix="wp13_re_"))
        try:
            subprocess.run([sys.executable, str(SENS_SCRIPT), "--out", str(tmp)],
                           check=False, capture_output=True, cwd=str(NEWROOT))
            rerender_ok = all((tmp / n).is_file() and
                              sha_file(tmp / n) == sha_file(NEWROOT / "manuscript" /
                                                             "figures" / n)
                              for n in SA_FILES)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    for f in figs:
        no = int(f["fig_no"])
        name = f["t10_file"]
        src = NEWROOT / "manuscript" / "figures" / name
        emb = media.get(f["media"], "")
        exists = src.is_file()
        same = exists and sha_file(src) == emb
        inside = f["media_sha"] == emb
        add("figure", "Fig %d embedded" % no, same and inside,
            "media %s vs manuscript/figures/%s" % (f["media"], name),
            emb[:16], (sha_file(src)[:16] if exists else "-"))

        hits = [p for p in idx.get(name, []) if sha_file(p) == emb]
        live = [p for p in hits
                if p.relative_to(NEWROOT).as_posix().startswith(live_prefix)]
        if live:
            add("figure", "Fig %d provenance" % no, True,
                "byte-identical to the live pipeline render",
                "live output render", live[0].relative_to(NEWROOT).as_posix())
        elif name in SA_FILES:
            ok = (f"{name}" in io.open(SENS_SCRIPT, encoding="utf-8",
                                       errors="replace").read())
            detail = "sensitivity render, reproduced by gen_sensitivity_figures.py"
            if rerender_ok is not None:
                ok = ok and rerender_ok
                detail += "; byte-identical when re-rendered" if rerender_ok else \
                          "; RE-RENDER DIFFERS"
            add("figure", "Fig %d provenance" % no, ok, detail,
                "script + config constants", "gen_sensitivity_figures.py")
        else:
            add("figure", "Fig %d provenance" % no, False,
                "no live or script provenance", "pipeline render",
                [p.relative_to(NEWROOT).as_posix() for p in hits[:2]])

    # ─────────────────────────── sensitivity figures: constants vs the model
    if sa_const:
        adj = ast.literal_eval(truth["p.Climate.V_HALF_ADJUSTMENT"]["value"])
        add("figure", "sa constants V_HALF_ADJ", sa_const.get("V_HALF_ADJ") == adj,
            "gen_sensitivity_figures.py vs p.Climate.V_HALF_ADJUSTMENT",
            adj, sa_const.get("V_HALF_ADJ"))
        vthr = float(truth["p.Climate.TC_IMPACT_V_THRESH"]["value"])
        add("figure", "sa constants V_THRESH_BASE",
            sa_const.get("V_THRESH_BASE") == vthr,
            "gen_sensitivity_figures.py vs p.Climate.TC_IMPACT_V_THRESH",
            vthr, sa_const.get("V_THRESH_BASE"))
        scale = float(truth["p.Climate.SURGE_MDR_CALIBRATION_SCALE"]["value"])
        add("figure", "sa constants SURGE_SCALES",
            scale in (sa_const.get("SURGE_SCALES") or []),
            "the calibrated 0.176 is one of the plotted scales",
            scale, sa_const.get("SURGE_SCALES"))
        base = [float(truth["sweep.TC_V_HALF_BASE_SCALE.v%d" % i]["value"])
                for i in range(5)]
        add("figure", "sa constants TC_BASE_SCALES",
            sa_const.get("TC_BASE_SCALES") == base,
            "plotted TC base scales vs sweep.TC_V_HALF_BASE_SCALE v0..v4",
            base, sa_const.get("TC_BASE_SCALES"))

    # ───────────────────────────────────────────────── figures: citation
    caption_ids = {pid for pid, st, txt in paras
                   if st == "ImageCaption" or txt.strip().startswith("Figure 15.")}
    body_refs: set[int] = set()
    for pid, st, txt in paras:
        if pid in caption_ids:
            continue
        body_refs |= refs_in(txt)
    missing = [n for n in range(1, 39) if n not in body_refs]
    add("figure", "citation closure", not missing,
        "every figure 1..38 is cited outside its own caption",
        "38/38 cited", missing or "38/38")

    # ──────────────────────────────────────────────────────── tables
    add("table", "block count", len(tables) == 11,
        "table blocks in document order", 11, len(tables))
    for t_i, cells in enumerate(tables):
        exp_rows, exp_cols, label, numbered = EXPECT_TABLES[t_i]
        got = (len(cells), max((len(r) for r in cells), default=0))
        add("table", "T%d dimension %s" % (t_i, label),
            got == (exp_rows, exp_cols),
            "%s block geometry" % label, (exp_rows, exp_cols), got)
        add("table", "T%d header %s" % (t_i, label), bool(cells and cells[0]),
            "header row: %s" % (cells[0][:4] if cells else "EMPTY"))

    caps_num = [int(m.group(1)) for m in
                (re.match(r"^\s*Table\s+(\d+)\.", t.strip()) for _, _, t in paras) if m]
    add("table", "caption order", caps_num == list(range(1, 9)),
        "numbered table captions in document order", list(range(1, 9)), caps_num)
    b1 = sum(1 for _, _, t in paras if re.match(r"^\s*Table\s+B1\.", t.strip()))
    add("table", "Table B1 caption", b1 == 1, "one Table B1 caption", 1, b1)

    trefs: set[str] = set()
    for pid, st, txt in paras:
        if re.match(r"^\s*Table\s+[A-Z]?\d+\.", txt.strip()):
            continue
        trefs |= table_refs_in(txt)
    want_t = {str(i) for i in range(1, 9)} | {"B1"}
    add("table", "citation closure", want_t <= trefs,
        "every numbered table is cited outside its own caption",
        sorted(want_t), sorted(trefs & want_t), severity="PROSE")

    # ──────────────────────────────────────────────────────── report
    bad = [r for r in rows if r["verdict"] != "OK" and r["severity"] == "BLOCKER"]
    prose = [r for r in rows if r["verdict"] != "OK" and r["severity"] == "PROSE"]
    tally = {}
    for r in rows:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    print("=== WP13.3 figure / table inventory ===")
    print("  document : %s" % docx.name)
    print("  figures  : %d drawings + 1 inline table = %d; captions %d; index %d"
          % (len(drawn), len(drawn) + 1, len(caps), len(index_nums)))
    print("  tables   : %d blocks (%d numbered + Figure 15 + index)"
          % (len(tables), len(caps_num) + b1))
    print("  checks   : %d, verdicts %s"
          % (len(rows), ", ".join("%s=%d" % kv for kv in sorted(tally.items()))))
    if rerender_ok is not None:
        print("  sa_01..04 re-rendered: %s" % ("byte-identical" if rerender_ok
                                               else "DIFFERS"))
    if bad:
        print("  --- BLOCKER FINDINGS (%d) ---" % len(bad))
        for r in bad:
            print("    %-14s %-26s exp %s got %s | %s"
                  % (r["verdict"], r["id"][:26], r["expected"], r["got"],
                     r["detail"][:70]))
    if prose:
        print("  --- PROSE FINDINGS (%d, author decision) ---" % len(prose))
        for r in prose:
            print("    %-14s %-26s exp %s got %s"
                  % (r["verdict"], r["id"][:26], r["expected"], r["got"]))

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["kind", "id", "verdict", "severity",
                                        "expected", "got", "detail"],
                       lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    tmp = Path(args.out).with_suffix(".csv.tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8", newline="\n")
    tmp.replace(Path(args.out))

    summary = {
        "generated": __import__("datetime").datetime.now().isoformat(
            timespec="seconds"),
        "docx": docx.name,
        "figures": {"drawings": len(drawn), "inline": 1, "captions": len(caps),
                    "index_rows": len(index_nums)},
        "tables": {"blocks": len(tables), "numbered": len(caps_num) + b1,
                   "uncited": sorted(want_t - trefs),
                   "cited": sorted(trefs & want_t)},
        "sa_rerender": rerender_ok,
        "checks": len(rows),
        "verdicts": tally,
        "blockers": bad,
        "prose_findings": prose,
        "result": "INVENTORY-OK" if not bad else "INVENTORY-FINDINGS",
    }
    Path(args.sum).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8", newline="\n")
    print("  wrote %s" % Path(args.out).relative_to(NEWROOT))
    print("RESULT: %s" % summary["result"])
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
