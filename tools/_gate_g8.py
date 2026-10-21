#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""_gate_g8.py — WP8 闸门（投稿要件）

6 项检查（定义见 docs/_待决事项.md §C）：

    G8-1  数据可公开性分级清单完整性
    G8-2  DA 段（P253）占位符状态：全消=PASS / 等于待决名单=PENDING / 名单外=FAIL
    G8-3  v11（= v10 + 图注 keepNext 排版修复）未被改动（字节 + SHA + 结构计数 + 提取器/修复报告 verdict）
    G8-4  投稿信 v2（结构 / 6 旧串消失 / 6 新串在 / 不改坏不变量 / 1 页）
    G8-5  review_notes 归档（≥18 篇 + README 覆盖 + 版本行）
    G8-6  待决事项覆盖（A1–A7 + 影响文件 + G8 定义）

纯标准库（与 tools/_gate_g7.py 同口径），可在管道环境运行：

    & ".\\env\\run.ps1" tools\\_gate_g8.py

退出码：0 = 全 PASS / 3 = 有 PENDING（待作者输入）/ 1 = 有 FAIL
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
MANU = ROOT / "manuscript"

# v11 = v10 + 37 个图注短标签段落的 keepNext（纯排版，正文零变化）
# 见 docs/_v11_排版修复报告.md 与 tools/patch_figure_caption_keepnext.py
V11 = MANU / "PAPER_MANUSCRIPT_v11.docx"
V11_BYTES = 28193070
V11_SHA = "7417FDE618D6C5114628B28C76C7E676141415EFA7BF50016BB13C2D472523CC"
KEEP_REPORT = DOCS / "_v11_keepnext_check.json"
EXPECT_OMATH = 131
EXPECT_OMATHPARA = 41
EXPECT_TABLES = 11
EXPECT_DRAWINGS = 37

LETTER = MANU / "Cover_Letter_npjNaturalHazards_v2.docx"
LETTER_PDF = MANU / "Cover_Letter_npjNaturalHazards_v2.pdf"
LETTER_PARAS = 17
LETTER_WORDS = 495
A4_W, A4_H = 11909, 16834          # twips
MARGIN_TWIPS = 1440
LETTER_OLD = ["CNY 33.3 billion", "CNY 40.2 billion", "undefended baseline",
              "0.83‰", "0.68‰", "0.38‰"]
LETTER_NEW = ["CNY 33.4 billion", "CNY 40.3 billion", "defended baseline",
              "0.82‰", "0.67‰", "0.39‰"]

GRADE_DOC = DOCS / "_数据可公开性分级清单.md"
PENDING_DOC = DOCS / "_待决事项.md"
DA_DOC = DOCS / "_DA声明_v10待补.md"
REVIEW_DIR = MANU / "review_notes"

results = []       # [(id, status, detail)]


def add(gid: str, status: str, detail: str = ""):
    results.append({"id": gid, "status": status, "detail": detail})


def txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def docx_xml(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        return z.read("word/document.xml").decode("utf-8", errors="replace")


def unesc(s: str) -> str:
    return (s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
            .replace("&apos;", "'").replace("&amp;", "&"))


def para_texts(xml: str):
    """顶层 <w:p> 的可见文本（只取 w:t，不取 m:t —— 与 python-docx 行为一致）。"""
    out = []
    for pm in re.finditer(r"<w:p[ >].*?</w:p>", xml, re.S):
        seg = pm.group(0)
        ts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", seg, re.S)
        out.append(unesc("".join(ts)))
    return out


# ══════════════════════════════════════════════════════════════ G8-1
def g8_1():
    g = txt(GRADE_DOC)
    if not g:
        return add("G8-1", "FAIL", "缺 %s" % GRADE_DOC.name)
    rows = re.findall(r"\|\s*\*\*D(\d{2})\*\*\s*\|(.+)$", g, re.M)
    ids = {"D%s" % r[0] for r in rows}
    expect = {"D%02d" % i for i in range(1, 17)}
    missing = sorted(expect - ids)
    bad_grade = []
    for num, rest in rows:
        cells = [c.strip() for c in rest.split("|")]
        joined = " | ".join(cells)
        if not re.search(r"\*\*(A|B|C|待定)", joined):
            bad_grade.append("D%s" % num)
    must = ["GS(2024)0650", "不转存", "Zenodo", "GitHub", "D17", "D18", "D19", "D20"]
    lack = [m for m in must if m not in g]
    if missing or bad_grade or lack:
        return add("G8-1", "FAIL",
                   "缺行=%s 无档位=%s 缺标记=%s" % (missing, bad_grade, lack))
    add("G8-1", "PASS", "%d 行 D01–D16 全覆盖，档位齐全，官方层/不转存/Zenodo/GitHub 齐备" % len(rows))


# ══════════════════════════════════════════════════════════════ G8-2
def g8_2():
    if not V11.is_file():
        return add("G8-2", "FAIL", "缺 %s" % V11.name)
    paras = para_texts(docx_xml(V11))
    da = [p for p in paras if p.startswith("Data availability. ")]
    if len(da) != 1:
        return add("G8-2", "FAIL", "DA 段数量 = %d（应为 1）" % len(da))
    da_text = da[0]
    found = set(re.findall(r"\[[^\]\n]{3,80}\]", da_text))
    allowed = set()
    for line in txt(PENDING_DOC).splitlines():
        line = line.strip()
        if line.upper().startswith("DA-PENDING:"):
            allowed.add(line.split(":", 1)[1].strip())
    if not found:
        return add("G8-2", "PASS", "DA 段零占位符")
    extra = found - allowed
    if extra:
        return add("G8-2", "FAIL",
                   "出现待决名单外的占位符：%s（允许=%s）" % (sorted(extra), sorted(allowed)))
    return add("G8-2", "PENDING",
               "%d 个占位符均在待决名单内：%s" % (len(found), "; ".join(sorted(found))))


# ══════════════════════════════════════════════════════════════ G8-3
def g8_3():
    if not V11.is_file():
        return add("G8-3", "FAIL", "缺 %s" % V11.name)
    size = V11.stat().st_size
    sha = hashlib.sha256(V11.read_bytes()).hexdigest().upper()
    xml = docx_xml(V11)
    omath = len(re.findall(r"<m:oMath[ >]", xml))
    omathpara = len(re.findall(r"<m:oMathPara[ >]", xml))
    tables = xml.count("<w:tbl>")
    drawings = xml.count("<w:drawing>")
    verdict = ""
    chk = DOCS / "_v10_check.json"
    if chk.is_file():
        try:
            verdict = json.loads(txt(chk)).get("verdict", "")
        except Exception:
            verdict = "unreadable"
    bad = []
    if size != V11_BYTES:
        bad.append("bytes=%d" % size)
    if sha != V11_SHA:
        bad.append("sha=%s" % sha[:16])
    if omath != EXPECT_OMATH:
        bad.append("oMath=%d" % omath)
    if omathpara != EXPECT_OMATHPARA:
        bad.append("oMathPara=%d" % omathpara)
    if tables != EXPECT_TABLES:
        bad.append("tables=%d" % tables)
    if drawings != EXPECT_DRAWINGS:
        bad.append("drawings=%d" % drawings)
    if verdict != "pass":
        bad.append("v10_check verdict=%r" % verdict)
    keep_v = ""
    if KEEP_REPORT.is_file():
        try:
            keep_v = json.loads(txt(KEEP_REPORT)).get("verdict", "")
        except Exception:
            keep_v = "unreadable"
    if keep_v != "PASS":
        bad.append("keepnext verdict=%r" % keep_v)
    if bad:
        return add("G8-3", "FAIL", "; ".join(bad))
    add("G8-3", "PASS", "%d B / SHA %s… / 131·41·11·37 / verdict pass"
        % (size, sha[:12]))


# ══════════════════════════════════════════════════════════════ G8-4
def g8_4():
    if not LETTER.is_file():
        return add("G8-4", "FAIL", "缺 %s" % LETTER.name)
    xml = docx_xml(LETTER)
    paras = para_texts(xml)
    body = "\n".join(paras)
    words = len(body.split())
    bad = []
    if len(paras) != LETTER_PARAS:
        bad.append("paras=%d" % len(paras))
    if words != LETTER_WORDS:
        bad.append("words=%d" % words)
    for s in LETTER_OLD:
        if s in body:
            bad.append("旧串残留 %r" % s)
    for s in LETTER_NEW:
        if s not in body:
            bad.append("新串缺失 %r" % s)
    # A4 + 1 英寸边距
    m = re.search(r"<w:pgSz[^>]*w:w=\"(\d+)\"[^>]*w:h=\"(\d+)\"", xml)
    if not m:
        bad.append("无 pgSz")
        pg = (0, 0)
    else:
        pg = (int(m.group(1)), int(m.group(2)))
        if pg != (A4_W, A4_H):
            bad.append("page=%dx%d" % pg)
    mm = re.search(r"<w:pgMar[^>]*/>", xml)
    if not mm:
        bad.append("无 pgMar")
    else:
        mg = mm.group(0)
        for side in ("left", "right"):
            v = re.search(r'w:%s="(\d+)"' % side, mg)
            if not v or int(v.group(1)) != MARGIN_TWIPS:
                bad.append("%s_margin=%s" % (side, v.group(1) if v else "?"))
    # 渲染页数
    pages = 0
    if LETTER_PDF.is_file():
        raw = LETTER_PDF.read_bytes().decode("latin-1")
        pages = len(re.findall(r"/Type\s*/Page[^s]", raw))
        if pages != 1:
            bad.append("pdf_pages=%d" % pages)
    else:
        bad.append("缺 PDF 预览件")
    # 生成器自检
    rep = DOCS / "_cover_letter_v2_check.json"
    if rep.is_file():
        try:
            j = json.loads(txt(rep))
            if j.get("checks_fail", 1) != 0:
                bad.append("gen_checks_fail=%s" % j.get("checks_fail"))
        except Exception:
            bad.append("生成器报告不可读")
    else:
        bad.append("缺 _cover_letter_v2_check.json")
    if bad:
        return add("G8-4", "FAIL", "; ".join(bad))
    add("G8-4", "PASS", "17 段 / %d 词 / A4 / 1440 twips / 6 换 6 / %d 页" % (words, pages))


# ══════════════════════════════════════════════════════════════ G8-5
def g8_5():
    if not REVIEW_DIR.is_dir():
        return add("G8-5", "FAIL", "缺 manuscript/review_notes/")
    qa = sorted(p.name for p in REVIEW_DIR.glob("审稿人提问-*.md"))
    readme = REVIEW_DIR / "README.md"
    rm = txt(readme)
    bad = []
    if len(qa) < 18:
        bad.append("问答篇数=%d（<18）" % len(qa))
    if not rm:
        bad.append("缺 README.md")
    else:
        miss = [n for n in qa if n not in rm]
        if miss:
            bad.append("README 未索引 %d 篇（如 %s）" % (len(miss), miss[0]))
        if "v10 配套" not in rm:
            bad.append("README 缺版本行")
    if not (REVIEW_DIR / "_Cover_Letter数字核对表_v10.md").is_file():
        bad.append("缺 _Cover_Letter数字核对表_v10.md")
    if bad:
        return add("G8-5", "FAIL", "; ".join(bad))
    add("G8-5", "PASS", "%d 篇问答 + README 全覆盖 + 核对表 + 版本行" % len(qa))


# ══════════════════════════════════════════════════════════════ G8-6
def g8_6():
    d = txt(PENDING_DOC)
    if not d:
        return add("G8-6", "FAIL", "缺 %s" % PENDING_DOC.name)
    bad = []
    for i in range(1, 8):
        if not re.search(r"^### A%d · " % i, d, re.M):
            bad.append("缺 A%d" % i)
    n_impact = d.count("**影响文件**")
    if n_impact < 6:
        bad.append("「影响文件」仅 %d 处（<6）" % n_impact)
    for i in range(1, 7):
        if "G8-%d" % i not in d:
            bad.append("缺 G8-%d 定义" % i)
    if "已裁定" not in d:
        bad.append("缺已裁定清单")
    if "patch_da_statement.py" not in d:
        bad.append("缺收尾命令")
    if bad:
        return add("G8-6", "FAIL", "; ".join(bad))
    add("G8-6", "PASS", "A1–A7 齐备 / 影响文件 %d 处 / G8-1..6 定义 / 已裁定清单 / 收尾命令"
        % n_impact)


def main() -> int:
    for fn in (g8_1, g8_2, g8_3, g8_4, g8_5, g8_6):
        try:
            fn()
        except Exception as exc:                     # noqa: BLE001
            add(fn.__name__.replace("g8_", "G8-").replace("_", "-"), "FAIL",
                "执行异常: %r" % (exc,))

    print("=" * 78)
    print("G8 闸门 · 投稿要件（WP8）")
    print("=" * 78)
    n_pass = n_pend = n_fail = 0
    for r in results:
        icon = {"PASS": "PASS", "PENDING": "PEND", "FAIL": "FAIL"}[r["status"]]
        print("  [%s] %-6s %s" % (icon, r["id"], r["detail"]))
        n_pass += r["status"] == "PASS"
        n_pend += r["status"] == "PENDING"
        n_fail += r["status"] == "FAIL"
    print("-" * 78)
    verdict = "PASS" if n_fail == 0 and n_pend == 0 else (
        "PENDING" if n_fail == 0 else "FAIL")
    print("RESULT: G8-%s   %d PASS / %d PENDING / %d FAIL" % (verdict, n_pass, n_pend, n_fail))
    if n_pend:
        print("  PENDING 原因：DA 段仍有作者未提供的占位符 → 见 docs/_待决事项.md §A2–A4")

    out = DOCS / "_gate_g8_result.json"
    payload = {
        "gate": "G8",
        "verdict": verdict,
        "pass": n_pass, "pending": n_pend, "fail": n_fail,
        "checks": results,
        "v11": {"bytes": V11_BYTES, "sha256": V11_SHA},
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("结果文件: %s" % out)
    return 0 if verdict == "PASS" else (3 if verdict == "PENDING" else 1)


if __name__ == "__main__":
    sys.exit(main())
