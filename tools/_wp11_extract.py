# -*- coding: utf-8 -*-
"""WP11.2 - extract the auditable surface of PAPER_MANUSCRIPT_v11.docx.

WHAT IT DOES
------------
Reads the v11 deliverable with the *same* stdlib reader the WP7 tooling used
(`tools/extract_manuscript_numbers.py`, imported rather than copied, so the
stable ids P{n} / T{t}#r{r}c{c} stay identical across the whole project) and
emits two inventories:

    docs\\_wp11_v11清单.csv     one row per numeric token, with the ±60-char
                                context, the owning section (nearest heading 2 /
                                heading 4) and whether the paragraph carries
                                OMML maths (the "never replace a whole paragraph"
                                trap of the WP7 rewriter)
    docs\\_wp11_图件清单.csv    one row per embedded figure: the drawing
                                paragraph, r:embed id -> word/media/... target,
                                PNG pixel size, EMU extent, the short
                                "Figure N: ..." label, the long "Figure N. ..."
                                caption, and the file name given by the figure
                                index table (T10)

It also prints structural facts the audit report quotes (paragraph / table /
drawing / maths counts, heading inventory, paragraphs that carry a heading
style but read like prose).

Read-only.  No document is modified.

USAGE
-----
  env\\run.ps1 tools\\_wp11_extract.py
  env\\run.ps1 tools\\_wp11_extract.py --docx <path> --out-prefix <dir>\\
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
DOCX = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v11.docx"
OUT_TOKENS = DOCS / "_wp11_v11清单.csv"
OUT_FIGS = DOCS / "_wp11_图件清单.csv"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

HEADING_STYLES = {"1", "2", "3", "4", "5"}
FIG_RE = re.compile(r"^\s*Figure\s+(\d+)\s*[:.]")


def load_extractor():
    spec = importlib.util.spec_from_file_location(
        "ext", NEWROOT / "tools" / "extract_manuscript_numbers.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ext"] = mod
    spec.loader.exec_module(mod)
    return mod


def png_size(blob: bytes) -> tuple[int, int]:
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        return (-1, -1)
    w, h = struct.unpack(">II", blob[16:24])
    return (w, h)


def read_rels(zf: zipfile.ZipFile) -> dict:
    root = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
    return {rel.get("Id"): rel.get("Target")
            for rel in root.findall(PKG_REL + "Relationship")}


def figure_inventory(docx: Path) -> list[dict]:
    with zipfile.ZipFile(docx) as zf:
        rels = read_rels(zf)
        media_sha: dict[str, str] = {}
        root = ET.fromstring(zf.read("word/document.xml"))
        body = root.find(W + "body")
        kids = list(body)
        out: list[dict] = []
        p_idx = 0
        for i, child in enumerate(kids):
            if child.tag != W + "p":
                continue
            drawing = child.find(".//" + W + "drawing")
            if drawing is not None:
                blip = drawing.find(".//" + A + "blip")
                rid = blip.get(R + "embed") if blip is not None else ""
                target = rels.get(rid, "")
                name = "word/" + target if target and not target.startswith("/") else target
                if name not in media_sha:
                    try:
                        media_sha[name] = hashlib.sha256(zf.read(name)).hexdigest().upper()
                    except KeyError:
                        media_sha[name] = ""
                try:
                    px = png_size(zf.read(name))
                except KeyError:
                    px = (-1, -1)
                ext = drawing.find(".//" + WP + "extent")
                cx = int(ext.get("cx")) if ext is not None else -1
                cy = int(ext.get("cy")) if ext is not None else -1
                # forward scan: short label, then the long caption
                short = long_ = ""
                short_p = long_p = -1
                q = i + 1
                p_off = 0
                while q < len(kids) and q <= i + 4:
                    sib = kids[q]
                    if sib.tag == W + "p":
                        txt = "".join(t.text or "" for t in sib.iter(W + "t")).strip()
                        st = sib.find(W + "pPr/" + W + "pStyle")
                        st = st.get(W + "val") if st is not None else ""
                        if not short and st == "ImageCaption":
                            short, short_p = txt, p_idx + 1 + p_off
                        elif short and not long_ and txt:
                            long_, long_p = txt, p_idx + 1 + p_off
                            break
                    q += 1
                    p_off += 1
                m = FIG_RE.match(short) or FIG_RE.match(long_)
                out.append({
                    "fig_no": int(m.group(1)) if m else -1,
                    "drawing_para": "P%d" % p_idx,
                    "rId": rid,
                    "media": name,
                    "media_sha": media_sha[name],
                    "px_w": px[0], "px_h": px[1],
                    "extent_cx": cx, "extent_cy": cy,
                    "short_label": short,
                    "long_caption": long_,
                    "long_caption_para": "P%d" % long_p if long_p >= 0 else "",
                })
            p_idx += 1

    # figure index table (T10) -> file per figure number
    with zipfile.ZipFile(docx) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
        body = root.find(W + "body")
        t_idx = 0
        for child in body:
            if child.tag != W + "tbl":
                continue
            if t_idx == 10:
                idx = {}
                for tr in child.findall(W + "tr"):
                    tcs = tr.findall(W + "tc")
                    cells = ["".join(t.text or "" for t in tc.iter(W + "t")).strip()
                             for tc in tcs]
                    if cells and cells[0].isdigit():
                        idx[int(cells[0])] = cells[2] if len(cells) > 2 else ""
                for row in out:
                    row["t10_file"] = idx.get(row["fig_no"], "")
                break
            t_idx += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="WP11.2 v11 inventory")
    ap.add_argument("--docx", default=str(DOCX))
    ap.add_argument("--out-tokens", default=str(OUT_TOKENS))
    ap.add_argument("--out-figures", default=str(OUT_FIGS))
    args = ap.parse_args()

    docx = Path(args.docx)
    ext = load_extractor()
    entries, counts = ext.read_docx_stdlib(docx)

    print("=== WP11.2 v11 inventory ===")
    print("  document : %s (%d B)" % (docx.name, docx.stat().st_size))
    print("  structure: %d paragraphs, %d tables, %d m:oMath, %d m:oMathPara, "
          "%d w:drawing" % (counts["paragraphs"], counts["tables"],
                            counts["m_oMath"], counts["m_oMathPara"],
                            counts["w_drawing"]))

    sec1 = sec2 = sec3 = ""
    headings: list[tuple[str, str, int]] = []
    misstyled: list[tuple[str, str, int]] = []
    rows: list[dict] = []
    for e in entries:
        if e.kind == "paragraph":
            style = e.style
            if style in HEADING_STYLES:
                txt = e.text.strip()
                headings.append((e.ident, style, len(txt)))
                is_real_heading = len(txt) <= 120
                if is_real_heading and style == "2":
                    sec1, sec2, sec3 = txt, "", ""
                elif is_real_heading and style == "3":
                    sec2, sec3 = txt, ""
                elif is_real_heading and style == "4":
                    sec3 = txt
                if len(txt) > 120 and style != "1":
                    misstyled.append((e.ident, txt[:80], len(txt)))
            section = " / ".join(x for x in (sec1, sec2, sec3) if x)
            for tok, a, b in ext.numeric_tokens(e.text):
                rows.append({
                    "row_id": e.ident, "kind": e.kind, "style": style,
                    "has_math": e.has_math, "section": section,
                    "token": tok, "token_norm": ext.norm_token(tok),
                    "value": ext.as_number(tok),
                    "context": re.sub(r"\s+", " ", e.text[max(0, a - 60):b + 60]).strip(),
                })
        else:
            section = " / ".join(x for x in (sec1, sec2, sec3) if x)
            for tok, a, b in ext.numeric_tokens(e.text):
                rows.append({
                    "row_id": e.ident, "kind": e.kind, "style": e.style,
                    "has_math": e.has_math, "section": section,
                    "token": tok, "token_norm": ext.norm_token(tok),
                    "value": ext.as_number(tok),
                    "context": re.sub(r"\s+", " ", e.text[max(0, a - 60):b + 60]).strip(),
                })

    figs = figure_inventory(docx)

    print("  tokens   : %d numeric tokens over %d elements"
          % (len(rows), len({r["row_id"] for r in rows})))
    print("  headings : %d (%s)"
          % (len(headings), ", ".join("h%s=%d" % (s, sum(1 for _, x, _ in headings if x == s))
                                      for s in sorted({x for _, x, _ in headings}))))
    if misstyled:
        print("  heading-styled prose (%d):" % len(misstyled))
        for ident, txt, n in misstyled:
            print("    %-5s (%d chars) %r" % (ident, n, txt))
    print("  figures  : %d drawings" % len(figs))
    missing_no = [f["drawing_para"] for f in figs if f["fig_no"] < 0]
    if missing_no:
        print("    ! drawings without a Figure N label: %s" % missing_no)
    dup = {}
    for f in figs:
        dup.setdefault(f["fig_no"], []).append(f["drawing_para"])
    for k, v in sorted(dup.items()):
        if len(v) > 1:
            print("    ! duplicate Figure %s: %s" % (k, v))
    nofile = [f["fig_no"] for f in figs if not f.get("t10_file")]
    if nofile:
        print("    ! not listed in the figure index: %s" % nofile)
    indexed = set()  # filled below from the figure index table
    t10_nums = set()
    with zipfile.ZipFile(docx) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
        body = root.find(W + "body")
        t_i = 0
        for child in body:
            if child.tag == W + "tbl":
                if t_i == 10:
                    for tr in child.findall(W + "tr"):
                        first = tr.find(W + "tc")
                        if first is not None:
                            txt = "".join(t.text or "" for t in first.iter(W + "t")).strip()
                            if txt.isdigit():
                                t10_nums.add(int(txt))
                    break
                t_i += 1
    drawn = {f["fig_no"] for f in figs}
    only_index = sorted(t10_nums - drawn)
    if only_index:
        print("    note: listed in the index but not an image: %s "
              "(expected for the inline summary table)" % only_index)
    not_index = sorted(drawn - t10_nums)
    if not_index:
        print("    ! drawn but missing from the index: %s" % not_index)

    # ---- write
    tok_out = Path(args.out_tokens)
    tok_out.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["row_id", "kind", "style", "has_math",
                                        "section", "token", "token_norm",
                                        "value", "context"], lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    tmp = tok_out.with_suffix(".csv.tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8", newline="\n")
    tmp.replace(tok_out)

    fig_out = Path(args.out_figures)
    cols = ["fig_no", "drawing_para", "rId", "media", "media_sha", "px_w", "px_h",
            "extent_cx", "extent_cy", "short_label", "long_caption",
            "long_caption_para", "t10_file"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in figs:
        w.writerow({k: r.get(k, "") for k in cols})
    tmp = fig_out.with_suffix(".csv.tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8", newline="\n")
    tmp.replace(fig_out)

    print("  wrote %s (%d rows)" % (tok_out.relative_to(NEWROOT), len(rows)))
    print("  wrote %s (%d rows)" % (fig_out.relative_to(NEWROOT), len(figs)))
    print("RESULT: INVENTORY-OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
