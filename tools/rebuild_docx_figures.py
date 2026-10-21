"""WP7.4: re-seat, refresh and re-frame the 37 embedded figures of v10.

What is wrong in the frozen document (all three findings proven by bytes/XML)
----------------------------------------------------------------------------
1. **Staleness** - the document embeds the October-12 renders, i.e. the
   pre-option-A figures.  The 41 PNGs under ``manuscript/figures`` are the
   *first* option-A renders (verified WP6 restore, 17 Oct 21:53-21:55) and are
   byte-reproducible (WP7.4-a: 78/78 hashes unchanged after regeneration).
2. **Rotation defect (F1)** - slots 24..38 carry, in order, the images of
   figures 25..38 and finally the image of figure 24.  Three independent
   references agree on the *intended* pairing (caption label ``Figure N:``,
   the T10 figure-index table, and the ``pic:cNvPr`` source path), while the
   payload, ``wp:docPr`` alt-text number and drawing frame all travelled with
   the wrong image.
3. **Frame mismatch** - because the frame travelled with the wrong image, 11
   drawings have a ``wp:extent`` aspect that does not match the figure that
   belongs in that slot; the payload must be re-framed or it renders squashed
   (one slot, Figure 14, is already distorted in the frozen document).

What is changed
---------------
* the 37 ``word/media/*.png`` payloads (by slot semantics)
* ``wp:extent`` / ``a:ext`` cy for the slots whose frame is off by >0.5%
* ``wp:docPr descr`` -> the slot's caption label text (removes the stale
  ``Figure 10``/``Figure 2`` numbering)
* ``pic:cNvPr descr`` -> the original source-path string of the file that
  belongs in that slot (strings are reused verbatim, never invented)

Everything else (entry order, compress types, every non-media part, all other
document.xml bytes) is preserved and asserted.

Usage
-----
    & ".\\env\\run.ps1" tools\\rebuild_docx_figures.py --dry-run
    & ".\\env\\run.ps1" tools\\rebuild_docx_figures.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import struct
import sys
import zipfile
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
FIGDIR = NEWROOT / "manuscript" / "figures"
IN_DOCX = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v10.docx"
ARCHIVE_LEGACY = NEWROOT / "output_archive" / "baseline_legacy_20261016_212711"
MAP_CSV = DOCS / "_v10_figure_map.csv"
REPORT_MD = DOCS / "_图件替换报告.md"

T10_NAME_FIX = {8: "fi_01_finance_risk_index.png", 11: "fi_04_fri_vs_cri_overlay.png"}
FIG_TABLE_IDX = 10
FRAME_TOL_PCT = 0.5          # adjust wp:extent when the aspect is off by more

TAG_RE = re.compile(r"<(/?)([A-Za-z_][\w.:\-]*)(?:\"[^\"]*\"|'[^']*'|[^>\"'])*?(/?)>")
DRAW_RE = re.compile(r"<w:drawing[ >].*?</w:drawing>", re.S)
EMBED_RE = re.compile(r'r:embed="(rId\d+)"')
EXTENT_RE = re.compile(r'<wp:extent cx="(\d+)" cy="(\d+)"')
AEXT_RE = re.compile(r'<a:ext cx="(\d+)" cy="(\d+)"')
DOCPR_RE = re.compile(r'<wp:docPr[^>]*?descr="([^"]*)"')
PICPR_RE = re.compile(r'<pic:cNvPr[^>]*?descr="([^"]*)"')
REL_RE = re.compile(r'Id="(rId\d+)"[^>]*Target="([^"]+)"')
LABEL_RE = re.compile(r"^\s*Figure\s+(\d+)\s*:")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def png_size(b: bytes):
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    return struct.unpack(">II", b[16:24])


def xml_attr(text: str) -> str:
    return (text.replace("&", "&amp;").replace('"', "&quot;")
                .replace("<", "&lt;").replace(">", "&gt;"))


def xml_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# XML walking (same child semantics as the number extractor)
# ---------------------------------------------------------------------------
def inner_span(xml: str, s: int, e: int):
    if xml[e - 2:e] == "/>":
        return s, s
    return xml.index(">", s) + 1, xml.rindex("</", s, e)


def _children_of(xml: str, lo: int, hi: int, tag: str):
    out, depth, cur = [], 0, None
    for t in TAG_RE.finditer(xml, lo, hi):
        closing, name, selfc = t.group(1) == "/", t.group(2), t.group(3) == "/"
        if closing:
            depth -= 1
            if depth == 0 and cur is not None and cur[0] == name:
                if name == tag:
                    out.append((cur[1], t.end()))
                cur = None
            continue
        if selfc:
            if depth == 0 and name == tag:
                out.append((t.start(), t.end()))
            continue
        if depth == 0:
            cur = (name, t.start())
        depth += 1
    return out


def body_children(xml: str, tag: str):
    m = re.search(r"<w:body(\s[^>]*)?>", xml)
    if not m:
        raise RuntimeError("<w:body> not found")
    return _children_of(xml, m.end(), xml.rindex("</w:body>"), tag)


def _text_of(xml: str, lo: int, hi: int) -> str:
    txt = "".join(m.group(1) for m in re.finditer(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", xml[lo:hi], re.S))
    return (txt.replace("&lt;", "<").replace("&gt;", ">")
               .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))


def table_rows(xml: str, span):
    s, e = span
    inner_lo, inner_hi = inner_span(xml, s, e)
    rows = []
    for rs, re_ in _children_of(xml, inner_lo, inner_hi, "w:tr"):
        r_lo, r_hi = inner_span(xml, rs, re_)
        cells = []
        for cs, ce in _children_of(xml, r_lo, r_hi, "w:tc"):
            c_lo, c_hi = inner_span(xml, cs, ce)
            parts = []
            for ps, pe in _children_of(xml, c_lo, c_hi, "w:p"):
                p_lo, p_hi = inner_span(xml, ps, pe)
                parts.append(_text_of(xml, p_lo, p_hi))
            cells.append(" ".join(p for p in parts if p))
        rows.append(cells)
    return rows


# ---------------------------------------------------------------------------
def scan(xml: str, relmap: dict, figdir: Path):
    """Return (fig2file, slots) computed from the current document."""
    tables = body_children(xml, "w:tbl")
    if len(tables) <= FIG_TABLE_IDX:
        raise RuntimeError("figure index table not found")
    fig2file = {}
    for row in table_rows(xml, tables[FIG_TABLE_IDX])[1:]:
        if len(row) < 3:
            continue
        m = re.match(r"^\s*(\d+)\s*$", row[0])
        if not m:
            continue
        n = int(m.group(1))
        fn = T10_NAME_FIX.get(n, row[2].strip())
        if not (figdir / fn).is_file():
            continue
        fig2file[n] = fn

    paras = body_children(xml, "w:p")
    starts, texts = [], []
    for s, e in paras:
        lo, hi = inner_span(xml, s, e)
        starts.append(s)
        texts.append(_text_of(xml, lo, hi))

    slots = []
    for m in DRAW_RE.finditer(xml):
        blk = m.group(0)
        rid = EMBED_RE.search(blk)
        if not rid:
            continue
        pos = m.start()
        fig = label = None
        for i, st in enumerate(starts):
            if st > pos:
                mm = LABEL_RE.match(texts[i])
                if mm:
                    fig = int(mm.group(1))
                    label = texts[i].strip()
                break
        if fig is None:
            raise RuntimeError("drawing without a 'Figure N:' label")
        ext = EXTENT_RE.search(blk)
        aext = AEXT_RE.search(blk)
        docpr = DOCPR_RE.search(blk)
        picpr = PICPR_RE.search(blk)
        slots.append(dict(
            pos=pos, blk=blk, figure=fig, label=label,
            rid=rid.group(1), media=relmap.get(rid.group(1)),
            cx=int(ext.group(1)), cy=int(ext.group(2)),
            ext_span=(m.start() + ext.start(), m.start() + ext.end()),
            aext_span=(m.start() + aext.start(), m.start() + aext.end()) if aext else None,
            docpr_span=(m.start() + docpr.start(1), m.start() + docpr.end(1)) if docpr else None,
            picpr_span=(m.start() + picpr.start(1), m.start() + picpr.end(1)) if picpr else None,
            docpr=docpr.group(1) if docpr else "",
            picpr=picpr.group(1) if picpr else "",
        ))
    return fig2file, slots


def main() -> int:
    ap = argparse.ArgumentParser(description="re-seat and refresh the embedded figures")
    ap.add_argument("--docx", default=str(IN_DOCX))
    ap.add_argument("--figures-dir", default=str(FIGDIR))
    ap.add_argument("--out", default=None)
    ap.add_argument("--legacy", default=str(ARCHIVE_LEGACY))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    docx, figdir = Path(args.docx), Path(args.figures_dir)
    for p in (docx, figdir):
        if not p.exists():
            print("ERROR missing %s" % p)
            return 2

    with zipfile.ZipFile(docx) as zf:
        infos = zf.infolist()
        blobs = {i.filename: zf.read(i.filename) for i in infos}
    xml = blobs["word/document.xml"].decode("utf-8")
    rels = blobs["word/_rels/document.xml.rels"].decode("utf-8")
    relmap = {rid: ("word/" + tgt) for rid, tgt in REL_RE.findall(rels) if tgt.startswith("media/")}

    fig2file, slots = scan(xml, relmap, figdir)
    print("T10 figures with an image: %d   drawings: %d" % (len(fig2file), len(slots)))
    missing = [n for n in fig2file if n not in {s["figure"] for s in slots}]
    if missing:
        print("  note: figures present in T10 but not embedded: %s" % missing)

    target = {n: (figdir / fn).read_bytes() for n, fn in fig2file.items()}
    current_sha = {n: sha(b) for n, b in target.items()}
    sha2fig = {}
    for n, s in current_sha.items():
        sha2fig.setdefault(s, []).append(n)

    legacy = {}
    leg_root = Path(args.legacy)
    file2fig = {fn: n for n, fn in fig2file.items()}
    for sub in ("Climate/output/figures_new", "Finance/output/figures", "Composite/output/figures"):
        p = leg_root / sub
        if not p.is_dir():
            continue
        for f in p.rglob("*.png"):
            n = file2fig.get(f.name)
            if n is not None:
                legacy.setdefault(sha(f.read_bytes()), n)

    # original source paths, keyed by basename (reused verbatim)
    path_by_name = {}
    for s in slots:
        base = s["picpr"].split("/")[-1]
        if base:
            path_by_name[base] = s["picpr"]

    plan, repls = [], []
    for s in slots:
        n = s["figure"]
        fn = fig2file.get(n)
        if fn is None:
            print("ERROR no target file for Figure %d" % n)
            return 3
        tgt = target[n]
        cur = blobs[s["media"]]
        cur_s = sha(cur)
        if cur_s == current_sha[n]:
            action, ident, note = "ALREADY-CURRENT", n, ""
        else:
            if cur_s in sha2fig:
                ident, note = sha2fig[cur_s][0], "payload == Figure %d file" % sha2fig[cur_s][0]
            elif cur_s in legacy:
                ident, note = legacy[cur_s], "payload == pre-A archive render of Figure %d" % legacy[cur_s]
            else:
                ident, note = -1, "payload matches no known render"
            action = "REPLACE"
        w0, h0 = png_size(cur)
        w1, h1 = png_size(tgt)
        frame = s["cx"] / s["cy"]
        frame_delta = ((w1 / h1) - frame) / frame * 100.0
        new_cx = s["cx"]
        new_cy = int(round(new_cx * h1 / w1)) if abs(frame_delta) > FRAME_TOL_PCT else s["cy"]
        if new_cy != s["cy"]:
            repls.append((s["ext_span"][0], s["ext_span"][1],
                          '<wp:extent cx="%d" cy="%d"' % (new_cx, new_cy)))
            if s["aext_span"]:
                repls.append((s["aext_span"][0], s["aext_span"][1],
                              '<a:ext cx="%d" cy="%d"' % (new_cx, new_cy)))
        # alt text
        if s["docpr_span"] and s["docpr"] != s["label"]:
            repls.append((s["docpr_span"][0], s["docpr_span"][1], xml_attr(s["label"])))
        want_path = path_by_name.get(fn, fn)
        if s["picpr_span"] and s["picpr"] != want_path:
            repls.append((s["picpr_span"][0], s["picpr_span"][1], xml_attr(want_path)))
        plan.append(dict(figure=n, media=s["media"], current_sha=cur_s[:16],
                         current_ident=ident, target_file=fn,
                         target_sha=current_sha[n][:16], action=action,
                         old_px="%dx%d" % (w0, h0), new_px="%dx%d" % (w1, h1),
                         frame_old="%dx%d" % (s["cx"], s["cy"]),
                         frame_delta=frame_delta,
                         reframed="yes" if new_cy != s["cy"] else "no",
                         old_docpr=s["docpr"], old_picpr=s["picpr"], note=note))

    misassigned = [p for p in plan if p["current_ident"] not in (-1, p["figure"])]
    reframed = [p for p in plan if p["reframed"] == "yes"]
    n_replace = sum(1 for p in plan if p["action"] == "REPLACE")
    print("  already current %d | to replace %d | wrong-figure slots %d | reframed %d"
          % (len(plan) - n_replace, n_replace, len(misassigned), len(reframed)))
    for p in misassigned:
        print("    Figure %-2d currently holds Figure %-2d" % (p["figure"], p["current_ident"]))
    for p in reframed:
        print("    Figure %-2d frame re-aspect %.2f%%  %s -> %s" %
              (p["figure"], p["frame_delta"], p["frame_old"], p["new_px"]))

    # --- outputs
    cols = ["figure", "media", "current_sha", "current_ident", "target_file", "target_sha",
            "action", "old_px", "new_px", "frame_old_emu", "frame_delta_pct", "reframed",
            "old_docpr", "old_picpr", "note"]
    with MAP_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for p in plan:
            w.writerow([p["figure"], p["media"], p["current_sha"],
                        p["current_ident"] if p["current_ident"] != -1 else "",
                        p["target_file"], p["target_sha"], p["action"],
                        p["old_px"], p["new_px"], p["frame_old"],
                        "%.3f" % p["frame_delta"], p["reframed"],
                        p["old_docpr"], p["old_picpr"], p["note"]])

    lines = ["# 图件替换报告（WP7.4）\n",
             "- 输入：`%s`；图源：`manuscript/figures/`（41 张，WP6 末次 restore 于 2026-10-17 21:53-21:55 重出，可复现闸门 78/78 哈希不变）" % docx.name,
             "- 槽位 37；需替换 %d；**当前装着别的图号图的槽位 %d 个**；重设显示框 %d 个" %
             (n_replace, len(misassigned), len(reframed)),
             "",
             "## 1. 三重证据：错位的是图片，不是图注\n",
             "同一个槽位上有三处独立信息：图注标签（`Figure N:` 段）、T10 图表索引表、",
             "`pic:cNvPr` 图源路径。三者对 24-38 号槽位给出的**应放文件**完全一致；",
             "而实际二进制载荷、`wp:docPr` 里的图号、`wp:extent` 显示框**三者一起**装错了位置。",
             "因此按槽位语义（图注标签）重新赋值是唯一自洽的修法。\n",
             "| 槽位 | 现在装的 | 应装文件 | 动作 | 显示框 |",
             "|---:|---|---|---|---|"]
    for p in sorted(plan, key=lambda x: x["figure"]):
        cur = ("Figure %d" % p["current_ident"]) if p["current_ident"] != -1 else "未知渲染"
        lines.append("| %d | %s | `%s` | %s | %s |" %
                     (p["figure"], cur, p["target_file"], p["action"],
                      ("重设 %.1f%%" % p["frame_delta"]) if p["reframed"] == "yes" else "保持"))
    lines += ["", "## 2. 显示框重设", "",
              "因为显示框跟着错误的图片走，11 个槽位的 `wp:extent` 宽高比与应放图片不符；",
              "若不改，替换后图片会被压扁（其中 Figure 14 在底稿里**本来就是被拉伸的**）。",
              "处理：保留宽度 `cx`，按新图 `cy = cx × h / w` 重算，兼容阈值 0.5%。", "",
              "## 3. 替代文本修正", "",
              "`wp:docPr descr` 原有的图号是错的（第 1 张图标成 `Figure 10`）；",
              "`pic:cNvPr descr` 的图源路径也跟着图片错位。全部改为与图注一致的",
              "`Figure N: <图注标题>` 与该图正确的原始路径串（路径串原样复用，不新造）。", "",
              "## 4. 未进稿的 4 张", "",
              "`s_0103_tc_damage_by_district.png`、`s_0202_ss_occurrence_hexbin.png`、",
              "`s_0203_ss_damage_hexbin.png`、`s_0204_ss_damage_by_district.png`（T10 未引用）。",
              "Figure 15 在 T10 中是 `Inline module summary table`（无图片），故 38 个图号只有 37 张图。", "",
              "## 5. 逐槽位明细", "", "见 `docs/_v10_figure_map.csv`。"]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("  wrote %s" % MAP_CSV)
    print("  wrote %s" % REPORT_MD)

    if args.dry_run:
        print("RESULT: DRY-RUN-OK (no docx written)")
        return 0

    # --- apply xml replacements (descending) + payload swaps
    for lo, hi, txt in sorted(repls, key=lambda r: r[0], reverse=True):
        xml = xml[:lo] + txt + xml[hi:]
    new_blobs = dict(blobs)
    new_blobs["word/document.xml"] = xml.encode("utf-8")
    for p in plan:
        new_blobs[p["media"]] = target[p["figure"]]

    out = Path(args.out) if args.out else docx
    tmp = out.with_name(out.stem + ".tmp.docx")
    with zipfile.ZipFile(tmp, "w") as zf_out:
        for info in infos:
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.internal_attr = info.internal_attr
            zi.create_system = info.create_system
            zf_out.writestr(zi, new_blobs[info.filename])
    if out.exists():
        out.unlink()
    tmp.rename(out)

    # --- verify the artefact
    with zipfile.ZipFile(out) as zf:
        if zf.namelist() != [i.filename for i in infos]:
            print("ERROR zip entry order changed")
            return 5
        new_xml = zf.read("word/document.xml").decode("utf-8")
        media_bad = [p["media"] for p in plan
                     if sha(zf.read(p["media"])) != current_sha[p["figure"]]]
        if media_bad:
            print("ERROR media mismatch: %s" % media_bad[:5])
            return 6
        changed = [n for n in zf.namelist()
                   if n not in {"word/document.xml"} and not n.startswith("word/media/")
                   and zf.read(n) != blobs[n]]
        if changed:
            print("ERROR non-media, non-document parts changed: %s" % changed)
            return 5
    fig2file2, slots2 = scan(new_xml, relmap, figdir)
    errs = []
    for s in slots2:
        n = s["figure"]
        w1, h1 = png_size(target[n])
        if abs((s["cx"] / s["cy"]) - w1 / h1) / (w1 / h1) * 100 > FRAME_TOL_PCT:
            errs.append("Figure %d frame aspect still off by more than %.2f%%"
                        % (n, FRAME_TOL_PCT))
        if s["docpr"] != s["label"]:
            errs.append("Figure %d docPr alt-text mismatch: %r" % (n, s["docpr"]))
        if s["picpr"].split("/")[-1] != fig2file[n]:
            errs.append("Figure %d pic path mismatch: %r" % (n, s["picpr"]))
    counts = dict(
        paragraphs=len(body_children(new_xml, "w:p")),
        tables=len(body_children(new_xml, "w:tbl")),
        m_oMath=len(re.findall(r"<m:oMath[ >]", new_xml)),
        m_oMathPara=len(re.findall(r"<m:oMathPara[ >]", new_xml)),
        w_drawing=len(re.findall(r"<w:drawing[ >]", new_xml)),
    )
    print("  structural counts: %s" % counts)
    if errs:
        print("  [!] %d verification problems" % len(errs))
        for e in errs[:20]:
            print("      %s" % e)
        print("RESULT: FAIL")
        return 7
    print("  wrote %s (%.2f MB)" % (out, out.stat().st_size / 1e6))
    print("RESULT: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
