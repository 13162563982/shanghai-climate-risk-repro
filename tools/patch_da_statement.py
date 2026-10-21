#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""patch_da_statement.py — WP8-2 · 把 Data Availability 段（P253）换成定稿模板。

目标稿件
--------
默认目标为 ``manuscript/PAPER_MANUSCRIPT_v11.docx``
（= v10 + 37 个图注短标签段落的 keepNext 排版修复；正文/文字与 v10 逐字节相同，
 见 docs/_v11_排版修复报告.md）。v10 原样保留作证据基线。

设计要点
--------
1. **纯标准库**：与 ``tools/rewrite_manuscript_v10.py`` 同口径，可在管道环境（climada_env）运行。
2. **只改一个 `<w:t>` 的文本**：``P253`` 是单 run、832 字符、内部无 ``m:oMath``（已实测），
   故直接替换该 ``<w:t>`` 的内容，``<w:r>``/``rPr`` 原样保留 → 字体字号不变。
3. **默认 dry-run**：输出到 ``output_archive/_wp8_da_dryrun_<ts>/``，正文零改动。
4. **槽位未传则逐字保留原占位符**：绝不猜 DOI / 仓库 URL / 提供方措辞。
5. **不变量断言**：段数 409、m:oMath 131、m:oMathPara 41、表 11、drawing 37、zip 条目顺序、
   非 document.xml 部件字节不变。

用法
----
    python tools/patch_da_statement.py                      # dry-run，全部槽位保持占位
    python tools/patch_da_statement.py --zenodo-doi 10.5281/zenodo.123
    python tools/patch_da_statement.py --apply --zenodo-doi ... --repo-url ... --repo-tag ... \
        --provider "..." --buildings restricted

退出码
------
    0  成功（dry-run 或已落笔）
    2  前置/断言失败
    3  拒绝执行（该 docx 已是新文，防止二次套模板）
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOCX = PROJECT_ROOT / "manuscript" / "PAPER_MANUSCRIPT_v11.docx"
FROZEN_DIR = PROJECT_ROOT / "manuscript" / "_frozen"
ARCHIVE_DIR = PROJECT_ROOT / "output_archive"

# ── 期望结构（v10/v11 实测值，两者完全相同） ──────────────────────────────
EXPECT_PARAS = 409
EXPECT_OMATH = 131
EXPECT_OMATHPARA = 41
EXPECT_TABLES = 11
EXPECT_DRAWINGS = 37

# ── 模板 ────────────────────────────────────────────────────────────────
BUILDINGS_UNSPECIFIED = (
    "The processed building exposure inventory (585,033 records), district-level loss panels and "
    "index series generated in this study are available at {ZENODO_DOI}."
)
BUILDINGS_PUBLIC = BUILDINGS_UNSPECIFIED
BUILDINGS_RESTRICTED = (
    "The district-level loss panels and index series generated in this study are available at "
    "{ZENODO_DOI}; the full building-level inventory (585,033 records) cannot be redistributed "
    "because it derives from licensed commercial footprint and listing data."
)
BUILDINGS_SENTENCES = {
    "unspecified": BUILDINGS_UNSPECIFIED,
    "public": BUILDINGS_PUBLIC,
    "restricted": BUILDINGS_RESTRICTED,
}

DA_TEMPLATE = (
    "Data availability. {BUILDINGS_SENTENCE} District boundaries follow the official 2024 "
    "county-level division product (Tianditu, map review no. GS(2024)0650); the boundary layer is "
    "not redistributed. The gridded meteorological, sea-level and impervious-surface source rasters "
    "described in Methods are third-party products and are not redistributed here. Source data: "
    "IBTrACS v4r01 from NOAA NCEI (https://doi.org/10.25921/82ty-9e16); FABDEM V1-2 from the "
    "University of Bristol data repository; LandScan population grids from Oak Ridge National "
    "Laboratory (https://doi.org/10.48690/1524213); ETOPO 2022 from NOAA NCEI "
    "(https://doi.org/10.25921/fd45-gt74); housing price data from {PRICE_PROVIDER}. "
    "Code availability. All model code is implemented in Python using the CLIMADA platform "
    "(https://github.com/CLIMADA-project/climada_python) and is available at {REPO_URL}"
    "{REPO_TAG}, including the fixed random seed (42) configuration for full reproducibility."
)

# ── 槽位未提供时的原占位符（= v10 现状逐字） ──────────────────────────────
SLOT_ZENODO = "[Zenodo DOI to be assigned]"
SLOT_REPO = "[GitHub repository, release version]"
SLOT_PROVIDER = "[data provider, with access conditions]"

# ── 定位锚点 ────────────────────────────────────────────────────────────
ANCHOR_HEAD = "Data availability. The processed building exposure inventory (585,033 records)"
ANCHOR_TAIL = "configuration for full reproducibility."

DOCX_PART = "word/document.xml"


def die(msg: str, code: int = 2) -> "NoReturn":  # noqa: F821
    print("ERROR: " + msg, file=sys.stderr)
    raise SystemExit(code)


def read_docx(path: Path):
    """返回 (zip, 有序条目名, {name: bytes})。"""
    zf = zipfile.ZipFile(path, "r")
    names = zf.namelist()
    blobs = {n: zf.read(n) for n in names}
    zf.close()
    return names, blobs


def write_docx(dst: Path, names, blobs):
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in names:
            zi = zipfile.ZipInfo(n)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, blobs[n])


def unescape_xml(s: str) -> str:
    return (
        s.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&amp;", "&")
    )


def escape_xml(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def count_omath(xml: str) -> int:
    """开标签 <m:oMath> 的个数（不含 <m:oMathPara>、不含闭标签）。"""
    return len(re.findall(r"<m:oMath[ >]", xml))


def count_paragraphs(xml: str) -> int:
    """body 内的顶层 <w:p> 个数（近似：<= python-docx 的 409）。"""
    return len(re.findall(r"<w:p[ >]", xml))


def find_da_t_span(xml: str):
    """定位 DA 段那一个 <w:t>，返回 (t_start, t_end, inner_start, inner_end, inner_text)。"""
    hits = [m.start() for m in re.finditer(re.escape(ANCHOR_HEAD), xml)]
    if len(hits) != 1:
        die("DA 锚点出现 %d 次（应为 1 次）：%r" % (len(hits), ANCHOR_HEAD))
    pos = hits[0]

    t_open = xml.rfind("<w:t", 0, pos)
    if t_open < 0:
        die("DA 锚点前找不到 <w:t>")
    t_open_end = xml.find(">", t_open)
    if t_open_end < 0:
        die("<w:t> 标签未闭合")
    t_close = xml.find("</w:t>", t_open_end)
    if t_close < 0:
        die("</w:t> 未找到")
    # 锚点必须完整落在同一个 <w:t> 内
    if not (t_open_end < pos < t_close):
        die("DA 锚点不在这一个 <w:t> 内（疑似跨 run）")
    if "</w:t>" in xml[t_open_end:pos]:
        die("DA 段被拆成多个 <w:t>，本脚本按单 run 设计，拒绝执行")

    inner_start = t_open_end + 1
    inner_text = unescape_xml(xml[inner_start:t_close])
    return t_open, t_close + len("</w:t>"), inner_start, t_close, inner_text


def render(buildings: str, zenodo: str, repo_url: str, repo_tag: str, provider: str) -> str:
    """两段替换：先填首句，再填其余槽位。全程用 str.replace（不用 .format，
    以免被替换进来的值本身含花括号时二次解析）。"""
    tag = (" " + repo_tag) if (repo_url != SLOT_REPO and repo_tag) else ""
    sentence = BUILDINGS_SENTENCES[buildings].replace("{ZENODO_DOI}", zenodo)
    out = DA_TEMPLATE
    for key, val in (
        ("{BUILDINGS_SENTENCE}", sentence),
        ("{ZENODO_DOI}", zenodo),
        ("{PRICE_PROVIDER}", provider),
        ("{REPO_URL}", repo_url),
        ("{REPO_TAG}", tag),
    ):
        out = out.replace(key, val)
    return out


def verify_invariants(before: dict, after_xml: str, names, blobs_before, blobs_after):
    checks = []

    def chk(name, ok, detail=""):
        checks.append((name, bool(ok), detail))
        return bool(ok)

    chk("段落标签数不变", count_paragraphs(after_xml) == before["paras"],
        "%d -> %d" % (before["paras"], count_paragraphs(after_xml)))
    chk("m:oMath 数不变", count_omath(after_xml) == before["omath"],
        "%d -> %d" % (before["omath"], count_omath(after_xml)))
    chk("m:oMathPara 数不变",
        len(re.findall(r"<m:oMathPara[ >]", after_xml)) == before["omathpara"],
        "%d -> %d" % (before["omathpara"], len(re.findall(r"<m:oMathPara[ >]", after_xml))))
    chk("表数不变", after_xml.count("<w:tbl>") == before["tables"],
        "%d -> %d" % (before["tables"], after_xml.count("<w:tbl>")))
    chk("drawing 数不变", after_xml.count("<w:drawing>") == before["drawings"],
        "%d -> %d" % (before["drawings"], after_xml.count("<w:drawing>")))

    # zip 条目顺序与其它部件字节不变
    chk("zip 条目顺序", list(blobs_after) == list(names))
    diff = [n for n in names if n != DOCX_PART and blobs_before[n] != blobs_after[n]]
    chk("非 document.xml 部件字节不变", not diff, ",".join(diff[:3]))
    chk("document.xml 字节确有变化", blobs_before[DOCX_PART] != blobs_after[DOCX_PART])
    return checks


def main() -> int:
    ap = argparse.ArgumentParser(description="WP8-2 patch the Data Availability paragraph (P253) of v11")
    ap.add_argument("--docx", type=Path, default=DEFAULT_DOCX)
    ap.add_argument("--buildings", choices=sorted(BUILDINGS_SENTENCES), default="unspecified")
    ap.add_argument("--zenodo-doi", default=SLOT_ZENODO)
    ap.add_argument("--repo-url", default=SLOT_REPO)
    ap.add_argument("--repo-tag", default="")
    ap.add_argument("--provider", default=SLOT_PROVIDER)
    ap.add_argument("--apply", action="store_true", help="真正写回 docx（默认 dry-run）")
    ap.add_argument("--out-dir", type=Path, default=None, help="dry-run 输出目录")
    args = ap.parse_args()

    src = Path(args.docx)
    if not src.is_file():
        die("找不到 docx：%s" % src)

    names, blobs = read_docx(src)
    if DOCX_PART not in blobs:
        die("docx 内缺 %s" % DOCX_PART)
    xml = blobs[DOCX_PART].decode("utf-8")

    before = {
        "_names": names,
        "paras": count_paragraphs(xml),
        "omath": count_omath(xml),
        "omathpara": len(re.findall(r"<m:oMathPara[ >]", xml)),
        "tables": xml.count("<w:tbl>"),
        "drawings": xml.count("<w:drawing>"),
    }
    print("== 现状 ==")
    print("  paras=%d oMath=%d oMathPara=%d tables=%d drawings=%d"
          % (before["paras"], before["omath"], before["omathpara"], before["tables"], before["drawings"]))

    # 已打过的文件拒绝二次套模板
    if "GS(2024)0650" in xml and ANCHOR_HEAD not in xml:
        die("该 docx 的 DA 段已含 GS(2024)0650，疑似已落笔；拒绝二次套模板", 3)
    if ANCHOR_HEAD not in xml:
        die("找不到 DA 锚点，docx 可能不是 v10/v11")

    t_open, t_end, inner_start, inner_end, old_text = find_da_t_span(xml)
    if not old_text.startswith("Data availability. "):
        die("DA 段不是以 'Data availability. ' 开头：%r" % old_text[:60])
    if not old_text.endswith(ANCHOR_TAIL):
        die("DA 段不是以 %r 结尾：%r" % (ANCHOR_TAIL, old_text[-80:]))

    new_text = render(
        args.buildings,
        args.zenodo_doi.strip() or SLOT_ZENODO,
        args.repo_url.strip() or SLOT_REPO,
        args.repo_tag.strip(),
        args.provider.strip() or SLOT_PROVIDER,
    )
    if not new_text.startswith("Data availability. "):
        die("模板首句异常")

    # 逐字 diff
    print("\n== 逐槽位变化 ==")
    pairs = [
        (SLOT_ZENODO, args.zenodo_doi.strip() or SLOT_ZENODO),
        (SLOT_REPO, args.repo_url.strip() or SLOT_REPO),
        (SLOT_PROVIDER, args.provider.strip() or SLOT_PROVIDER),
    ]
    for old, new in pairs:
        flag = "保留" if old == new else "替换"
        print("  [%s] %s -> %s" % (flag, old, new))
    print("  [新增] 官方边界层句：%s" % ("是" if "GS(2024)0650" in new_text else "否"))
    print("  [新增] 第三方栅格不转存句：%s"
          % ("是" if "are third-party products" in new_text else "否"))
    print("  [首句] buildings=%s" % args.buildings)

    # 替换这一个 <w:t> 的内容
    t_tag = xml[t_open:inner_start]
    if 'xml:space="preserve"' not in t_tag:
        t_tag = t_tag[:-1] + ' xml:space="preserve">'
    new_xml = xml[:t_open] + t_tag + escape_xml(new_text) + "</w:t>" + xml[t_end:]
    blobs_after = dict(blobs)
    blobs_after[DOCX_PART] = new_xml.encode("utf-8")

    print("\n== 不变量 ==")
    ok_all = True
    for name, ok, detail in verify_invariants(before, new_xml, names, blobs, blobs_after):
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name, ("  (" + detail + ")") if detail else ""))
        ok_all &= ok
    if not ok_all:
        die("不变量断言失败，未写出任何文件")

    print("\n== 新 DA 段（%d 字符） ==" % len(new_text))
    print(new_text)

    pending = [s for s in (SLOT_ZENODO, SLOT_REPO, SLOT_PROVIDER) if s in new_text]
    print("\n== 槽位状态 ==")
    if pending:
        print("  PENDING: " + "; ".join(pending))
    else:
        print("  全部已填")

    # 落盘
    if args.apply:
        FROZEN_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = FROZEN_DIR / ("%s_preDA_%s.docx" % (src.stem, stamp))
        shutil.copy2(src, bak)
        print("\n备份: %s (%d B)" % (bak, bak.stat().st_size))
        write_docx(src, names, blobs_after)
        print("已落笔: %s (%d B)" % (src, src.stat().st_size))
        print("→ 必须回归: tools\\_gate_g7_v11.py（期望 14/14）、tools\\_gate_g11.py（18/18）"
              "            与 tools\\_gate_g8.py（A2–A5 全部到位后期望 6/6）")
    else:
        out_dir = args.out_dir or (ARCHIVE_DIR / ("_wp8_da_dryrun_" + datetime.now().strftime("%Y%m%d_%H%M%S")))
        out_dir.mkdir(parents=True, exist_ok=True)
        dst = out_dir / (src.stem + ".da-preview.docx")
        write_docx(dst, names, blobs_after)
        print("\nDRY-RUN 输出: %s (%d B)" % (dst, dst.stat().st_size))
        print("正文未改动: %s (%d B)" % (src, src.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
