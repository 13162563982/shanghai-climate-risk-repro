# -*- coding: utf-8 -*-
"""WP14 - render the two availability statements from the provenance ledger.

Why generated and not hand-written
----------------------------------
The v14 statements were a verbatim copy of what used to sit inside the
manuscript.  That text named five sources and left three placeholders; it did
not match what is actually on disk (it missed the official boundary layer, the
meteorological grids, the sea-level product, the building-footprint product and
the calibration loss series).  Hand-editing it again would let it drift a second
time, so the statement is now *rendered from* `docs/_数据溯源台账.csv`: a row with
`DA动作 = 写入` contributes its `DA措辞`, and `_gate_g14.py` asserts the rendered
text and the ledger agree in both directions.

Placeholders are never guessed.  They are filled from
`docs/_DA_填写值.json`, which ships with nulls until the author supplies the
values; a null keeps the bracketed placeholder verbatim.

Outputs
    manuscript/Data_Availability_Statement.docx
    manuscript/Code_Availability_Statement.docx
    docs/_v15_声明正文.txt          plain-text mirror (gate + diff friendly)
    docs/_v15_声明文件摘要.json      sizes, sha256, token counts, placeholders
    docs/_wp14_声明数字.csv          --numbers: rows for _wp13_ledger.py --extra

USAGE
    <bundled python> tools\\make_availability_v2.py --dry-run
    <bundled python> tools\\make_availability_v2.py --apply
    <bundled python> tools\\make_availability_v2.py --apply --numbers
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.shared import Pt

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
MAN = NEWROOT / "manuscript"

LEDGER = DOCS / "_数据溯源台账.csv"
VALUES = DOCS / "_DA_填写值.json"

DA_OUT = MAN / "Data_Availability_Statement.docx"
CODE_OUT = MAN / "Code_Availability_Statement.docx"
TXT_OUT = DOCS / "_v15_声明正文.txt"
SUM_OUT = DOCS / "_v15_声明文件摘要.json"
NUM_OUT = DOCS / "_wp14_声明数字.csv"
BACKUP_DIR = MAN / "_frozen"

TITLE = "Wind–surge asymmetry in typhoon risk to Shanghai's housing market"
AUTHOR = "Chen Jian, Fudan University International School of Finance"
JOURNAL = "npj Natural Hazards"

# Sentence templates that are NOT dataset clauses.  Everything else -- the
# deposit sentence, the boundary sentence and the code sentence -- comes from
# the ledger rows D25 / D19 / D27 so wording and evidence cannot diverge.
DATA_RESTRICTED = (
    "Three source groups are not redistributed here: the gridded meteorological, "
    "sea-level, impervious-surface and LandScan population rasters; the monthly "
    "second-hand housing price series, obtained from {PRICE_PROVIDER} under "
    "{PRICE_ACCESS}; and the community-level listings, obtained from "
    "{COMMUNITY_PROVIDER}."
)

# 编号 -> source-data list items, in the order they are presented
LIST_ORDER = ["D01", "D02", "D04", "D03", "D07", "D09", "D12", "D13",
              "D05", "D10", "D21"]
# rows rendered as their own sentence
SENTENCE_ROWS = ["D25", "D19", "D17", "D20"]
CLAUSE_ORDER = SENTENCE_ROWS + LIST_ORDER


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s and s[0].isupper() else s


def _upper_first(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _strip_end(s: str) -> str:
    return s.rstrip().rstrip(".")


def pretty(s: str) -> str:
    """Year ranges read with an en dash, not a hyphen (submission house style)."""
    s = re.sub(r"\b((?:19|20)\d{2})-((?:19|20)\d{2})\b",
               lambda m: m.group(1) + "\u2013" + m.group(2), s)
    return re.sub(r"[ \t]{2,}", " ", s).strip()

CITATIONS = [
    ("He 2024 (CMFD v2.0)",
     "He, J., Yang, K., Li, X., Tang, W., Shao, C., Jiang, Y., & Ding, B. (2024). "
     "China meteorological forcing dataset v2.0 (1951-2024). National Tibetan "
     "Plateau / Third Pole Environment Data Center. "
     "https://doi.org/10.11888/Atmos.tpdc.302088"),
    ("He 2020 (CMFD method)",
     "He, J., Yang, K., Tang, W., Lu, H., Qin, J., Chen, Y. Y., & Li, X. (2020). "
     "The first high-resolution meteorological forcing dataset for land process "
     "studies over China. Scientific Data, 7(1), 25. "
     "https://doi.org/10.1038/s41597-020-0369-y"),
    ("Hu & Miao 2025 (CHM_PRE V2)",
     "Hu, J., & Miao, C. (2025). CHM_PRE V2: An upgraded high-precision gridded "
     "precipitation dataset considering spatiotemporal and physical correlations "
     "for Mainland of China (V2.0.2) [Data set]. Zenodo. "
     "https://doi.org/10.5281/zenodo.14634575"),
    ("Gong 2020 (GAIA)",
     "Gong, P., Li, X., Wang, J., Bai, Y., Chen, B., Hu, T., Liu, X., Xu, B., "
     "Yang, J., Zhang, W., & Zhou, Y. (2020). Annual maps of global artificial "
     "impervious area (GAIA) between 1985 and 2018. Remote Sensing of "
     "Environment, 236, 111510. https://doi.org/10.1016/j.rse.2019.111510"),
    ("Zhang 2025 (CMAB)",
     "Zhang, Y., Zhao, H., & Long, Y. (2025). CMAB: A Multi-Attribute Building "
     "Dataset of China. Scientific Data, 12, 430. "
     "https://doi.org/10.1038/s41597-025-04730-5"),
    ("Copernicus Marine Service (SLA)",
     "Copernicus Marine Service. Global ocean gridded L4 sea surface heights and "
     "derived variables reprocessed, 1993 ongoing [Data set]. "
     "https://doi.org/10.48670/moi-00148"),
    ("NOAA NCEI (GSOD, source of the gridded temperatures)",
     "NOAA National Centers for Environmental Information. (1999). Global Surface "
     "Summary of the Day (GSOD) [Data set]. NOAA NCEI. "
     "https://www.ncei.noaa.gov/data/global-summary-of-the-day/archive/"),
    ("Ministry of Natural Resources (marine disaster bulletins)",
     "Ministry of Natural Resources of China. (1995-2023). China Marine Disaster "
     "Bulletins [Data set]. "
     "https://www.mnr.gov.cn/sj/sjfw/hy/gbgg/zghyzhgb/"),
]

CODE_BODY = ""   # superseded: the code sentence is ledger row D27

DEFAULT_VALUES = {
    "ZENODO_DOI": "[Zenodo DOI to be assigned]",
    "GITHUB_REPO": "[GitHub repository, release version]",
    "TAG": "",
    "PRICE_PROVIDER": "Juhui Data (https://www.gotohui.com)",
    "PRICE_ACCESS": "a commercial data subscription",
    "COMMUNITY_PROVIDER": "Anjuke",
}

# numeric tokens we accept in the rendered statement, with their authority
NUM_OK = {
    "585,033": ("OK-MODEL", "v14 稿件同一数字；WP11 真值表 585033"),
    "550": ("OK-PARAM", "00_config.py L_SHELF_M = 550000 m（约 550 km）"),
    "55": ("OK-PARAM", "00_config.py H_SHELF_M = 55.0 m"),
    "42": ("OK-PARAM", "00_config.py RANDOM_SEED = 42"),
    "0.05": ("OK-DATA", "D10/D11 栅格指纹 0.05°（_wp14_栅格指纹.csv）"),
    "0.125": ("OK-DATA", "D12 栅格指纹 0.125°"),
    "1": ("OK-DATA", "LandScan 1 km（30 arc-s）"),
    "10": ("OK-DATA", "CMAB / GAIA 10 m 级分辨率描述"),
    "30": ("OK-DATA", "FABDEM 30 m（3 arc-s）"),
    "1985": ("OK-EXT", "GAIA 起始年（数据介绍.pdf）"),
    "1993": ("OK-EXT", "CMEMS 产品起始年（DataCite 标题）"),
    "1995": ("OK-EXT", "海洋灾害公报起始年"),
    "1999": ("OK-EXT", "NOAA NCEI GSOD 官方 Cite as 年份（数据集起始年）"),
    "2018": ("OK-EXT", "GAIA 论文标题 「between 1985 and 2018」"),
    "2023": ("OK-EXT", "海洋灾害公报终止年"),
    "2024": ("OK-EXT", "GS(2024)0650 审图号年份"),
    "2022": ("OK-EXT", "Hawker et al. 2022 / NOAA NCEI 2022 出版物年份"),
    "2025": ("OK-EXT", "出版物年份"),
    "2020": ("OK-EXT", "GAIA 序列终止年"),
    "2000": ("OK-EXT", "LandScan 序列起始年"),
    "5": ("OK-EXT", "Chinas 5th census"),
    "6": ("OK-EXT", "6th census"),
    "7": ("OK-EXT", "7th census"),
    "2026": ("OK-EXT", "本文件生成年份"),
}

DOISPAN = re.compile(r"https?://\S+|10\.\d{4,9}/\S+|\{ZENODO_DOI\}|\{GITHUB_REPO\}")
# product/version designators carry digits that are not quantitative claims
VERSION = re.compile(r"\bv\d+(?:\.\d+)*(?:r\d+)?(?:-\d+)?\b"
                     r"|\b(?:GS|no\.)\s*\(?\d{4}\)?\d*", re.I)
TOK = re.compile(r"\d+(?:[.,]\d+)*(?:[eE][+-]?\d+)?")


def load_ledger() -> dict[str, dict]:
    with open(LEDGER, encoding="utf-8-sig", newline="") as fh:
        return {r["编号"]: r for r in csv.DictReader(fh)}


def load_values() -> dict:
    vals = dict(DEFAULT_VALUES)
    if VALUES.is_file():
        raw = json.loads(VALUES.read_text(encoding="utf-8"))
        for k, v in raw.items():
            if v:                       # null keeps the placeholder default
                vals[k] = v
    return vals


def render_data(ledger: dict[str, dict], vals: dict) -> list[tuple[str, str]]:
    """Return [(style, text)] where style in {label, body, cite}."""
    for pid in CLAUSE_ORDER:
        if not ledger[pid]["DA措辞"].strip():
            raise SystemExit("ledger row %s has no DA wording" % pid)

    items = [_strip_end(ledger[p]["DA措辞"]) for p in LIST_ORDER]
    source = "Source data: " + "; ".join(items) + "."

    sentences = []
    for pid in SENTENCE_ROWS:
        s = _strip_end(ledger[pid]["DA措辞"])
        sentences.append(_upper_first(s) + ".")
    deposit, boundary, footprints, shoreline = sentences

    body = " ".join([deposit, boundary, footprints, source,
                     DATA_RESTRICTED, shoreline])
    body = pretty(body.format(**vals))
    blocks = [("label", "Data availability."), ("body", body)]
    cite_lines = ["For the sources introduced by this statement; also suitable "
                  "for the reference list at revision:"]
    for _k, c in CITATIONS:
        cite_lines.append("- " + pretty(c))
    blocks.append(("cite", "\n".join(cite_lines)))
    merged = " ".join(b for _s, b in blocks)
    # sanity: every clause we promised must survive formatting
    for pid in CLAUSE_ORDER:
        frag = _strip_end(ledger[pid]["DA措辞"]).split("(")[0].strip()[-26:]
        if frag and frag not in merged:
            raise SystemExit("clause for %s missing after render: %r" % (pid, frag))
    return blocks


def build(path: Path, heading: str, blocks: list[tuple[str, str]]) -> None:
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(11)
    doc.add_heading(heading, level=1)
    for k, v in (("Manuscript", TITLE), ("Corresponding author", AUTHOR),
                 ("Journal", JOURNAL)):
        p = doc.add_paragraph()
        p.add_run("%s: " % k).bold = True
        p.add_run(v)
        p.paragraph_format.space_after = Pt(4)
    doc.add_paragraph()
    for style, text in blocks:
        if style == "label":
            p = doc.add_paragraph()
            p.add_run(text + " ").bold = True
            # body continues in the next block on its own paragraph
        elif style == "body":
            if p is not None:
                p.add_run(text)
                p = None
            else:                                  # pragma: no cover
                doc.add_paragraph(text)
        else:
            for line in text.split("\n"):
                doc.add_paragraph(line)
    doc.save(str(path))


def build_body_inline(path: Path, heading: str, label: str, text: str,
                      extra: list[tuple[str, str]]) -> None:
    """label + body in ONE paragraph (matches the v14 statement layout)."""
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(11)
    doc.add_heading(heading, level=1)
    for k, v in (("Manuscript", TITLE), ("Corresponding author", AUTHOR),
                 ("Journal", JOURNAL)):
        p = doc.add_paragraph()
        p.add_run("%s: " % k).bold = True
        p.add_run(v)
        p.paragraph_format.space_after = Pt(4)
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.add_run(label + " ").bold = True
    p.add_run(text)
    for sub, body in extra:
        doc.add_heading(sub, level=2)
        for line in body.split("\n"):
            doc.add_paragraph(line)
    doc.save(str(path))


def numbers_rows(data_text: str, code_text: str) -> list[dict]:
    rows = []
    for tag, text in (("DA", data_text), ("CODE", code_text)):
        spans = [(m.start(), m.end()) for m in DOISPAN.finditer(text)]
        spans += [(m.start(), m.end()) for m in VERSION.finditer(text)]
        for m in TOK.finditer(text):
            tok = m.group(0)
            if any(a <= m.start() < b for a, b in spans):
                cls = ("OK-EXT", "DOI/URL 内数字，标识已在 _wp14_标识核验.csv 核实")
            else:
                cls = NUM_OK.get(tok)
            if cls is None:
                rows.append({"位置": tag, "数字": tok, "判定": "UNVERIFIED",
                             "证据": "未在 NUM_OK 表中登记",
                             "说明": text[max(0, m.start() - 42):m.end() + 42]})
            else:
                rows.append({"位置": tag, "数字": tok, "判定": cls[0],
                             "证据": cls[1],
                             "说明": text[max(0, m.start() - 42):m.end() + 42]})
    return rows


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--numbers", action="store_true",
                    help="also emit _wp14_声明数字.csv for _wp13_ledger.py --extra")
    args = ap.parse_args()
    if not (args.apply or args.dry_run):
        args.dry_run = True

    ledger = load_ledger()
    vals = load_values()
    vals["TAG_SUFFIX"] = (" (" + vals["TAG"] + ")") if vals.get("TAG") else ""
    blocks = render_data(ledger, vals)
    data_label = blocks[0][1]
    data_body = blocks[1][1]
    cites = blocks[2][1]
    code_body = pretty(_strip_end(ledger["D27"]["DA措辞"]).format(**vals) + ".")

    joined = data_body + " " + code_body
    print("=== WP14 availability statements (v15) ===")
    print("  ledger rows      : %d" % len(ledger))
    print("  data statement   : %d chars" % len(data_body))
    print("  code statement   : %d chars" % len(code_body))
    left = re.findall(r"\[[^\]]+\]", joined)
    print("  placeholders     : %s" % (left or "none"))
    print("  values in force  : %s" % {k: vals[k] for k in
                                       ("ZENODO_DOI", "GITHUB_REPO", "TAG",
                                        "PRICE_ACCESS", "COMMUNITY_PROVIDER")})

    rows = numbers_rows(data_body, code_body)
    bad = [r for r in rows if not r["判定"].startswith("OK")]
    print("  numeric tokens   : %d (%d unverified)" % (len(rows), len(bad)))
    for r in bad:
        print("     ! %s %s  %s" % (r["位置"], r["数字"], r["说明"]))

    if args.numbers:
        with open(NUM_OUT, "w", encoding="utf-8-sig", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=["位置", "数字", "判定", "证据", "说明"])
            wr.writeheader()
            wr.writerows(rows)
        print("  wrote %s (%d rows)" % (NUM_OUT.name, len(rows)))

    if not args.apply:
        print("DRY-RUN: no file written")
        return 0 if not bad else 3

    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for src in (DA_OUT, CODE_OUT):
        if src.exists():
            dst = BACKUP_DIR / (src.stem + "_pre_v15_" + stamp + src.suffix)
            dst.write_bytes(src.read_bytes())
            print("  backup %s" % dst.name)

    build_body_inline(DA_OUT, "Data Availability Statement", data_label,
                      data_body, [("Dataset citations", cites)])
    build_body_inline(CODE_OUT, "Code Availability Statement",
                      "Code availability.", code_body, [])

    TXT_OUT.write_text(
        "Data availability. " + data_body + "\n\n" + cites + "\n\n"
        "Code availability. " + code_body + "\n",
        encoding="utf-8", newline="\n")

    summary = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "source": LEDGER.name,
        "values": vals,
        "placeholders": left,
        "data": {"name": DA_OUT.name, "bytes": DA_OUT.stat().st_size,
                 "sha256": sha(DA_OUT), "chars": len(data_body),
                 "paragraphs": len(Document(str(DA_OUT)).paragraphs)},
        "code": {"name": CODE_OUT.name, "bytes": CODE_OUT.stat().st_size,
                 "sha256": sha(CODE_OUT), "chars": len(code_body),
                 "paragraphs": len(Document(str(CODE_OUT)).paragraphs)},
        "numeric_tokens": len(rows),
        "unverified": len(bad),
        "clauses": CLAUSE_ORDER,
    }
    SUM_OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")
    for p in (DA_OUT, CODE_OUT):
        print("  wrote %s (%d B, %d paras)" % (
            p.name, p.stat().st_size, len(Document(str(p)).paragraphs)))
    print("RESULT: STATEMENTS-%s" % ("OK" if not bad else "UNVERIFIED"))
    return 0 if not bad else 3


if __name__ == "__main__":
    raise SystemExit(main())
