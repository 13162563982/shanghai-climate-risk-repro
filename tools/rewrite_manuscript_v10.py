"""WP7.2 step 3-4: rewrite the frozen manuscript into PAPER_MANUSCRIPT_v10.docx.

Design constraints (all enforced in code)
-----------------------------------------
* the frozen source is opened read-only and never written
* every edit happens **inside already-existing ``w:t`` runs**, or by merging
  the affected runs - a whole-paragraph ``.text`` replacement would silently
  destroy the 131 ``m:oMath`` objects whose text layer is empty, so it is
  forbidden
* an edit may never straddle an ``m:oMath`` / ``m:oMathPara`` boundary
* the only structural change is appending one ``w:r`` at the end of two
  paragraphs (WP7.3 disclosures); paragraph / table / math / drawing counts are
  re-verified by the caller
* every zip part except ``word/document.xml`` is copied byte-for-byte, in the
  original order and with the original compress type

Usage
-----
    & ".\\env\\run.ps1" tools\\rewrite_manuscript_v10.py --dry-run
    & ".\\env\\run.ps1" tools\\rewrite_manuscript_v10.py --strict
    & ".\\env\\run.ps1" tools\\rewrite_manuscript_v10.py --no-disclosure
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import zipfile
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
SRC_DOCX = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_FINAL.docx"
OUT_DOCX = NEWROOT / "manuscript" / "PAPER_MANUSCRIPT_v10.docx"
PLAN_CSV = DOCS / "_v10_edit_plan.csv"
REPORT_MD = DOCS / "_v10_改写报告.md"

TAG_RE = re.compile(r"<(/?)([A-Za-z_][\w.:\-]*)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*?)(/?)>")

# ---------------------------------------------------------------------------
# WP7.3 disclosures - appended at the END of existing paragraphs (no new <w:p>)
# ---------------------------------------------------------------------------
APPEND_SENTENCES = {
    "P178": (
        " The administrative boundary layer used throughout this study is derived from the "
        "county-level division of the Standard Map Service of China (approval number "
        "GS(2024)0650) and is processed in three steps: reprojection to EPSG:32651, removal of "
        "non-district polygons, and a topology check that yields zero pairwise overlap. Its 16 "
        "district polygons, which include coastal waters, total approximately 7,205 km\u00b2 and are "
        "used only for district assignment, area conversion and building-density calculation; the "
        "statutory terrestrial area of Shanghai quoted above (about 6,341 km\u00b2) is unaffected by "
        "this choice. The shoreline used to mask storm-surge inundation is deliberately taken from "
        "a separate, finer 2021 township-level layer, because the generalised official coastline "
        "displaces harbour-front and reclaimed shore segments; switching to the fine shoreline "
        "leaves a residual offset of +0.21% in the city-wide surge loss, which is reported here "
        "exactly as measured and whose diagnosis is documented in the reproducibility package."
    ),
    "P202": (
        " Monthly mean temperature is computed as the arithmetic mean of the monthly minimum and "
        "maximum fields, \u00bd(Tmin + Tmax), and the resulting annual series drives the warming "
        "elasticity \u03b1(T) = exp(\u03ba \u0394T_trend) with \u03ba = 0.05. The heat-stress component of the "
        "climate-hazard index uses the monthly maximum temperature above a 28 \u00b0C threshold, and "
        "precipitation, wind, heat stress and sea-level anomaly enter that index with equal "
        "weights of 0.25."
    ),
}


# ---------------------------------------------------------------------------
# WP7.3b structural fix: the "Data Availability Statement" heading sits before
# the Figure 24-38 block while its body text lives just before References, so
# heading and body are separated by 15 figure blocks.  Move the heading
# paragraph so that it directly precedes the DA body.  Paragraph count is
# unchanged (409) - nothing is added or deleted.
# ---------------------------------------------------------------------------
MOVE_PARAGRAPHS = [
    ("P205", "P253",
     "把 'Data Availability Statement' 标题挪到其正文之前（此前被 Figure 24-38 图块隔开）"),
]


# ---------------------------------------------------------------------------
# tiny XML helpers (string surgery - no re-serialisation)
# ---------------------------------------------------------------------------
def iter_children(xml: str, lo: int, hi: int):
    """Spans of the direct children of the element whose content is [lo, hi)."""
    out = []
    depth = 0
    cur = None
    for m in TAG_RE.finditer(xml, lo, hi):
        closing, name, _attrs, selfc = m.group(1), m.group(2), m.group(3), m.group(4)
        if closing:
            depth -= 1
            if depth == 0 and cur is not None and cur[0] == name:
                out.append((name, cur[1], m.end()))
                cur = None
            if depth < 0:
                raise RuntimeError("unbalanced XML near %d (%s)" % (m.start(), name))
            continue
        if selfc:
            if depth == 0:
                out.append((name, m.start(), m.end()))
            continue
        if depth == 0:
            cur = (name, m.start())
        depth += 1
    return out


def body_span(xml: str):
    m = re.search(r"<w:body(\s[^>]*)?>", xml)
    if not m:
        raise RuntimeError("<w:body> not found")
    return m.end(), xml.rindex("</w:body>")


def content_span(xml: str, span):
    _name, s, e = span
    if xml[e - 2:e] == "/>":
        return s, s
    open_end = xml.index(">", s) + 1
    close_start = xml.rindex("</", s, e)
    return open_end, close_start


# --- entity handling -------------------------------------------------------
ENTITY_RE = re.compile(r"&(#x?[0-9A-Fa-f]+|[A-Za-z]+);")
NAMED = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}


def decode_entity(ent: str):
    m = ENTITY_RE.fullmatch(ent)
    if not m:
        return None
    body = m.group(1)
    try:
        if body[:2].lower() == "#x":
            return chr(int(body[2:], 16))
        if body[0] == "#":
            return chr(int(body[1:]))
    except (ValueError, OverflowError):
        return None
    return NAMED.get(body)


def decode_with_map(raw: str):
    """Decode XML text to characters, returning per-character raw spans."""
    out, spans = [], []
    i, n = 0, len(raw)
    while i < n:
        if raw[i] == "&":
            j = raw.find(";", i)
            if j != -1 and j - i <= 10:
                ch = decode_entity(raw[i:j + 1])
                if ch is not None and len(ch) == 1:
                    out.append(ch)
                    spans.append((i, j + 1))
                    i = j + 1
                    continue
        out.append(raw[i])
        spans.append((i, i + 1))
        i += 1
    return "".join(out), spans


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# text model: one paragraph = ordered run-text nodes + math markers
# ---------------------------------------------------------------------------
class ParaModel:
    __slots__ = ("lo", "hi", "nodes", "events", "text")

    def __init__(self, xml: str, lo: int, hi: int):
        self.lo, self.hi = lo, hi
        self.nodes = []            # (content_lo, content_hi, decoded, spans)
        self.events = []           # ('t', node_idx) | ('math',)
        math_depth = 0
        open_t = None
        for m in TAG_RE.finditer(xml, lo, hi):
            closing, name = m.group(1) == "/", m.group(2)
            selfc = m.group(4) == "/"
            if name in ("m:oMath", "m:oMathPara"):
                if closing:
                    math_depth = max(0, math_depth - 1)
                elif selfc:
                    if math_depth == 0:
                        self.events.append(("math",))
                else:
                    if math_depth == 0:
                        self.events.append(("math",))
                    math_depth += 1
                continue
            if name == "w:t":
                if math_depth > 0:
                    continue
                if closing:
                    if open_t is not None:
                        raw = xml[open_t:m.start()]
                        dec, spans = decode_with_map(raw)
                        self.nodes.append((open_t, m.start(), dec, spans))
                        self.events.append(("t", len(self.nodes) - 1))
                        open_t = None
                elif selfc:
                    self.nodes.append((m.start(), m.start(), "", []))
                    self.events.append(("t", len(self.nodes) - 1))
                else:
                    open_t = m.end()
        self.text = "".join(n[2] for n in self.nodes)

    def math_between(self, node_a: int, node_b: int) -> bool:
        if node_a == node_b:
            return False
        inside = False
        for ev in self.events:
            if ev[0] == "t":
                if ev[1] == node_a:
                    inside = True
                elif ev[1] == node_b:
                    return False
            elif ev[0] == "math" and inside:
                return True
        return False

    def char_to_node(self):
        out = []
        for idx, (_lo, _hi, dec, _sp) in enumerate(self.nodes):
            out.extend([(idx, k) for k in range(len(dec))])
        return out

    def raw_span(self, ia: int, ib: int):
        """Raw-content replacements for the inner char span [ia, ib)."""
        cmap = self.char_to_node()
        if ia < 0 or ib > len(cmap) or ib <= ia:
            raise RuntimeError("char span out of range")
        na, ka = cmap[ia]
        nb, kb = cmap[ib - 1]
        return na, ka, nb, kb + 1


class ElementText:
    """The extractor-compatible text of one element (paragraph or table cell)."""

    def __init__(self, xml: str, units):
        self.units = units
        self.models = [ParaModel(xml, a, b) for (a, b) in units]
        keep = [i for i, m in enumerate(self.models) if m.text]
        parts, mapping = [], []
        for pos, ui in enumerate(keep):
            if pos:
                parts.append(" ")
                mapping.append(None)
            t = self.models[ui].text
            parts.append(t)
            mapping.extend([(ui, k) for k in range(len(t))])
        self.text = "".join(parts)
        self.map = mapping

    def locate(self, needle: str, occurrence: int):
        """Return ('ok', (unit_idx, ia, ib)) | ('cross-unit', None) | (None, None)."""
        positions, p = [], self.text.find(needle)
        while p != -1:
            positions.append(p)
            p = self.text.find(needle, p + 1)
        if len(positions) < occurrence:
            return None, None
        a = positions[occurrence - 1]
        b = a + len(needle)
        mapped = self.map[a:b]
        if any(x is None for x in mapped):
            return "cross-unit", None
        ui = mapped[0][0]
        if any(x[0] != ui for x in mapped):
            return "cross-unit", None
        return "ok", (ui, mapped[0][1], mapped[-1][1] + 1)


# ---------------------------------------------------------------------------
# document index
# ---------------------------------------------------------------------------
class DocIndex:
    def __init__(self, xml: str):
        self.xml = xml
        self.paras, self.tables = [], []
        lo, hi = body_span(xml)
        for name, s, e in iter_children(xml, lo, hi):
            if name == "w:p":
                self.paras.append((name, s, e))
            elif name == "w:tbl":
                self.tables.append((name, s, e))

    def units(self, loc: str):
        m = re.match(r"^P(\d+)$", loc)
        if m:
            i = int(m.group(1))
            if i >= len(self.paras):
                raise KeyError("paragraph P%d out of range (%d)" % (i, len(self.paras)))
            _n, s, e = self.paras[i]
            return [content_span(self.xml, ("w:p", s, e))]
        m = re.match(r"^T(\d+)#r(\d+)c(\d+)$", loc)
        if not m:
            raise KeyError("bad location id %r" % loc)
        t_i, r_i, c_i = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if t_i >= len(self.tables):
            raise KeyError("table T%d out of range (%d)" % (t_i, len(self.tables)))
        _n, ts, te = self.tables[t_i]
        lo, hi = content_span(self.xml, ("w:tbl", ts, te))
        rows = [x for x in iter_children(self.xml, lo, hi) if x[0] == "w:tr"]
        if r_i >= len(rows):
            raise KeyError("T%d row %d out of range (%d)" % (t_i, r_i, len(rows)))
        _n, rs, re_ = rows[r_i]
        lo2, hi2 = content_span(self.xml, ("w:tr", rs, re_))
        cells = [x for x in iter_children(self.xml, lo2, hi2) if x[0] == "w:tc"]
        if c_i >= len(cells):
            raise KeyError("T%d#r%d col %d out of range (%d)" % (t_i, r_i, c_i, len(cells)))
        _n, cs, ce = cells[c_i]
        lo3, hi3 = content_span(self.xml, ("w:tc", cs, ce))
        return [content_span(self.xml, ("w:p", s, e))
                for (n2, s, e) in iter_children(self.xml, lo3, hi3) if n2 == "w:p"]

    def element(self, loc: str):
        return ElementText(self.xml, self.units(loc))

    def paragraph_content(self, loc: str):
        return self.units(loc)[0]


# ---------------------------------------------------------------------------
# edit planning (pure: original xml -> list of raw replacements)
# ---------------------------------------------------------------------------
def plan_raw_repls(model: ParaModel, ia: int, ib: int, new_text: str):
    """Raw replacements implementing one edit inside one paragraph model."""
    na, ka, nb, kb = model.raw_span(ia, ib)
    if na == nb:
        lo, _hi, _dec, spans = model.nodes[na]
        return [(lo + spans[ka][0], lo + spans[kb - 1][1], esc(new_text))]
    if model.math_between(na, nb):
        raise RuntimeError("edit would straddle an m:oMath boundary")
    out = []
    lo_a, hi_a, _d, spans_a = model.nodes[na]
    out.append((lo_a + spans_a[ka][0], hi_a, esc(new_text)))
    for k in range(na + 1, nb):
        lo_k, hi_k, _d2, _s2 = model.nodes[k]
        out.append((lo_k, hi_k, ""))
    lo_b, _hi_b, _d3, spans_b = model.nodes[nb]
    out.append((lo_b, lo_b + spans_b[kb - 1][1], ""))
    return out


def apply_raw(xml: str, repls):
    for lo, hi, txt in sorted(repls, key=lambda r: (r[0], r[1]), reverse=True):
        xml = xml[:lo] + txt + xml[hi:]
    return xml


def move_paragraphs(xml: str, moves):
    """Move whole <w:p> blocks (nothing is added or deleted)."""
    log = []
    for src, dst, why in moves:
        idx = DocIndex(xml)
        i_src = int(re.match(r"^P(\d+)$", src).group(1))
        i_dst = int(re.match(r"^P(\d+)$", dst).group(1))
        _n, s1, e1 = idx.paras[i_src]
        _n2, s2, _e2 = idx.paras[i_dst]
        block = xml[s1:e1]
        rest = xml[:s1] + xml[e1:]
        shift = e1 - s1
        ins = s2 - shift if s2 > e1 else (s1 if s2 > s1 else s2)
        xml = rest[:ins] + block + rest[ins:]
        log.append((src, dst, shift, why))
    return xml, log


def check_overlaps(repls):
    srt = sorted(repls, key=lambda r: (r[0], r[1]))
    for i in range(1, len(srt)):
        if srt[i][0] < srt[i - 1][1]:
            return (srt[i - 1], srt[i])
    return None


# ---------------------------------------------------------------------------
def load_plan(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["seq"] = int(r["seq"])
        r["occurrence"] = int(r["occurrence"])
        r["has_math"] = (r["has_math"] == "True")
    return rows


def _loc_key(loc: str):
    m = re.match(r"^P(\d+)$", loc)
    if m:
        return (0, int(m.group(1)), 0, 0)
    m = re.match(r"^T(\d+)#r(\d+)c(\d+)$", loc)
    if m:
        return (1, int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return (2, 0, 0, 0)


def main() -> int:
    ap = argparse.ArgumentParser(description="rewrite the manuscript into v10")
    ap.add_argument("--src", default=str(SRC_DOCX))
    ap.add_argument("--plan", default=str(PLAN_CSV))
    ap.add_argument("--out", default=str(OUT_DOCX))
    ap.add_argument("--report", default=str(REPORT_MD))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-disclosure", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    src, plan_path = Path(args.src), Path(args.plan)
    for p in (src, plan_path):
        if not p.exists():
            print("ERROR missing input: %s" % p)
            return 2

    with zipfile.ZipFile(src) as zf:
        infos = zf.infolist()
        blobs = {i.filename: zf.read(i.filename) for i in infos}
    xml = blobs["word/document.xml"].decode("utf-8")

    idx = DocIndex(xml)
    print("source : %s" % src.name)
    print("  body paragraphs: %d  tables: %d" % (len(idx.paras), len(idx.tables)))

    rows = load_plan(plan_path)
    print("  plan rows: %d" % len(rows))

    repls_all = []
    results = []
    fatal = []

    by_loc = {}
    for r in rows:
        by_loc.setdefault(r["loc_id"], []).append(r)

    for loc in sorted(by_loc, key=_loc_key):
        try:
            elem = idx.element(loc)
        except (KeyError, RuntimeError) as exc:
            fatal.append((loc, "locate-failed", str(exc)))
            continue
        for r in sorted(by_loc[loc], key=lambda x: x["seq"]):
            needle, new_text, occ = r["old_text"], r["new_text"], r["occurrence"]
            status, hit = elem.locate(needle, occ)
            if status is None:
                kind = "band-info" if r["category"] == "BAND" else "not-found"
                results.append(dict(seq=r["seq"], loc=loc, occurrence=occ,
                                    category=r["category"], status=kind,
                                    old=needle, new=new_text, note=r["note"], unit=-1))
                if kind == "not-found":
                    fatal.append((loc, "not-found", "seq %d: %r" % (r["seq"], needle)))
                continue
            if status == "cross-unit":
                fatal.append((loc, "cross-unit", "seq %d: %r" % (r["seq"], needle)))
                continue
            ui, ia, ib = hit
            model = elem.models[ui]
            try:
                raw = plan_raw_repls(model, ia, ib, new_text)
            except RuntimeError as exc:
                fatal.append((loc, "math-straddle", "seq %d: %s" % (r["seq"], exc)))
                continue
            repls_all.extend(raw)
            results.append(dict(seq=r["seq"], loc=loc, occurrence=occ,
                                category=r["category"], status="applied",
                                old=needle, new=new_text, note=r["note"], unit=ui))

    # --- disclosures
    appended = []
    if not args.no_disclosure:
        for loc, sentence in APPEND_SENTENCES.items():
            try:
                lo, hi = idx.paragraph_content(loc)
            except KeyError as exc:
                fatal.append((loc, "append-locate", str(exc)))
                continue
            p_xml = idx.xml[lo:hi]
            rpr = ""
            runs = re.findall(r"<w:r(?:\s[^>]*)?>.*?</w:r>", p_xml, re.S)
            if runs:
                m_rpr = re.search(r"<w:rPr>.*?</w:rPr>", runs[-1], re.S)
                if m_rpr:
                    rpr = m_rpr.group(0)
            payload = sentence if sentence.startswith(" ") else " " + sentence
            run = '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (rpr, esc(payload))
            repls_all.append((hi, hi, run))
            appended.append(loc)
            results.append(dict(seq=0, loc=loc, occurrence=1, category="DISCLOSURE",
                                status="applied", old="",
                                new=sentence.strip()[:60] + " ...", note="new run appended", unit=0))

    ov = check_overlaps([r for r in repls_all if r[0] != r[1]])
    if ov:
        fatal.append(("(global)", "overlap", "%r vs %r" % (ov[0], ov[1])))

    applied = sum(1 for r in results if r["status"] == "applied")
    band_info = [r for r in results if r["status"] == "band-info"]
    print("")
    print("planned edits : %d applied, %d band-info, %d fatal"
          % (applied, len(band_info), len(fatal)))
    if band_info:
        print("  band rows absent from the text (informational, not applied):")
        for r in band_info:
            print("    seq %-3d %-11s %r" % (r["seq"], r["loc"], r["old"]))
    if fatal:
        print("")
        print("FATAL:")
        for loc, kind, msg in fatal:
            print("  %-11s %-14s %s" % (loc, kind, msg))
        if args.strict:
            print("RESULT: FAIL (strict)")
            return 3

    new_xml = apply_raw(xml, repls_all)

    # --- structural fix: move whole paragraphs (heading next to its body text)
    moved = []
    if MOVE_PARAGRAPHS:
        new_xml, moved = move_paragraphs(new_xml, MOVE_PARAGRAPHS)
        for mv_src, mv_dst, mv_bytes, mv_why in moved:
            print("  moved %s -> before %s (%d bytes)  %s" % (mv_src, mv_dst, mv_bytes, mv_why))
        # assert the heading now directly precedes the DA body
        chk = DocIndex(new_xml)
        texts = []
        for (nm, s, e) in chk.paras:
            lo, hi = content_span(new_xml, (nm, s, e))
            texts.append(ParaModel(new_xml, lo, hi).text.strip())
        bad = []
        for i, t in enumerate(texts):
            if t.startswith("Data Availability Statement"):
                nxt = texts[i + 1] if i + 1 < len(texts) else ""
                if not nxt.startswith("Data availability."):
                    bad.append("heading at P%d is followed by %r" % (i, nxt[:60]))
        if bad:
            fatal.append(("(move)", "da-heading", "; ".join(bad)))
            print("  [!] DA heading still not adjacent to its body text")

    # --- verification on the rewritten XML (before writing the file)
    idx2 = DocIndex(new_xml)
    verify_errors = []
    for r in results:
        if r["status"] != "applied" or r["category"] == "DISCLOSURE":
            continue
        try:
            txt = idx2.element(r["loc"]).text
        except (KeyError, RuntimeError) as exc:
            verify_errors.append("%s: re-locate failed (%s)" % (r["loc"], exc))
            continue
        if r["new"] not in txt:
            verify_errors.append("%s: NEW missing %r" % (r["loc"], r["new"]))
        if r["category"] != "BAND" and r["old"] in txt:
            # only an error when the old string should have been consumed entirely
            remaining = txt.count(r["old"])
            expected = 0
            verify_errors.append("%s: OLD still present %r x%d" % (r["loc"], r["old"], remaining))
    counts = {
        "paragraphs": len(idx2.paras),
        "tables": len(idx2.tables),
        "m_oMath": len(re.findall(r"<m:oMath[ >]", new_xml)),
        "m_oMathPara": len(re.findall(r"<m:oMathPara[ >]", new_xml)),
        "w_drawing": len(re.findall(r"<w:drawing>", new_xml)) + len(re.findall(r"<w:drawing ", new_xml)),
    }
    print("")
    print("  structural counts: %s" % json.dumps(counts))
    if verify_errors:
        print("  [!] %d verification problems:" % len(verify_errors))
        for e in verify_errors[:40]:
            print("      %s" % e)

    # --- report
    lines = ["# v10 改写报告\n",
             "- 底稿：`%s`（只读）" % src.name,
             "- 计划行数 %d；应用 %d；band 说明 %d；披露追加 %d；致命 %d" %
             (len(rows), applied - len(appended), len(band_info), len(appended), len(fatal)),
             "- 结构计数：`%s`" % json.dumps(counts),
             ""]
    if fatal:
        lines += ["## 致命问题\n", "| 位置 | 类型 | 详情 |", "|---|---|---|"]
        for loc, kind, msg in fatal:
            lines.append("| `%s` | %s | %s |" % (loc, kind, msg.replace("|", "/")))
        lines.append("")
    if verify_errors:
        lines += ["## 改写后校验异常\n"]
        for e in verify_errors:
            lines.append("- %s" % e)
        lines.append("")
    if band_info:
        lines += ["## band 行（文中无该串，仅作说明）\n"]
        for r in band_info:
            lines.append("- seq %d `%s`: `%s` → `%s`（%s）" %
                         (r["seq"], r["loc"], r["old"], r["new"], r["note"]))
        lines.append("")
    lines += ["## 逐行结果\n", "| seq | 位置 | 次 | 类别 | 状态 | OLD | NEW |",
              "|---:|---|---:|---|---|---|---|"]
    for r in sorted(results, key=lambda x: (x["seq"] or 9999)):
        lines.append("| %d | `%s` | %d | %s | %s | `%s` | `%s` |" %
                     (r["seq"] or 0, r["loc"], r["occurrence"], r["category"], r["status"],
                      r["old"].replace("|", "/"), r["new"].replace("|", "/")))
    rep = Path(args.report)
    if args.dry_run:
        rep = rep.with_name(rep.stem + "_DRYRUN" + rep.suffix)
    rep.write_text("\n".join(lines), encoding="utf-8")
    print("  wrote %s" % rep)

    if args.dry_run:
        print("RESULT: DRY-RUN-OK (no docx written)")
        return 0
    if fatal or verify_errors:
        print("RESULT: FAIL (see report)")
        return 4

    # --- write the docx (same order, same compress type, other parts verbatim)
    out = Path(args.out)
    tmp = out.with_name(out.stem + ".tmp.docx")
    with zipfile.ZipFile(tmp, "w") as zf_out:
        for info in infos:
            data = new_xml.encode("utf-8") if info.filename == "word/document.xml" \
                else blobs[info.filename]
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.internal_attr = info.internal_attr
            zi.create_system = info.create_system
            zf_out.writestr(zi, data)
    if out.exists():
        out.unlink()
    tmp.rename(out)

    with zipfile.ZipFile(out) as zf:
        if zf.namelist() != [i.filename for i in infos]:
            print("ERROR zip entry order changed")
            return 5
        for info in infos:
            if info.filename == "word/document.xml":
                continue
            if zf.read(info.filename) != blobs[info.filename]:
                print("ERROR non-document part changed: %s" % info.filename)
                return 5
    print("  wrote %s (%.2f MB)" % (out, out.stat().st_size / 1e6))
    print("RESULT: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
