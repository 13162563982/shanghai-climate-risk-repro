"""WP8-3 排版修复：给「图注短标签」段落加 keepNext，防止长图注与图分离。

背景（本次发现的具体缺陷）
--------------------------
v10 预览 PDF 第 15 页画出了图 14 的图片 + 短标签 ``Figure 14: CCHI decomposition``，
但下一行长图注 ``Figure 14. CCHI decomposition into CRI and HSI component
contributions across scenarios.`` 被推到了第 16 页，第 16 页几乎整页空白
（随后 ``Discussion`` 因 keepNext 链整体下移到第 17 页）。

根因：每个图块 = 三段
    [图 段落 style=CaptionedFigure（样式定义里已有 keepNext）]
    [短标签 style=ImageCaption（无 keepNext）]
    [长图注 style=a0（无 keepNext）]
链条在短标签处断开，长图注可自由跨页。WP7.2 修正图 14 的纵横比之后
（冻结版把图 14 纵向压扁 15.5%，解压后高度 +0.726 in），该图块正好卡在页底，
于是长图注被甩出。

本脚本的修复
------------
只给 37 个 ``ImageCaption`` 段落的 pPr 各插入一个 ``<w:keepNext/>``：
    <w:pPr><w:pStyle w:val="ImageCaption"/></w:pPr>
 -> <w:pPr><w:pStyle w:val="ImageCaption"/><w:keepNext/></w:pPr>
使「图 + 短标签 + 长图注」成为不可拆分块（Word 与 LibreOffice 都遵守）。

为什么不是改 styles.xml：段落级属性同样生效，且保持 styles.xml 相对冻结版
逐字节不变，从而 G7-5c（非媒体部件逐字节一致）在 v11 上仍然 PASS。

不变量（全部通过才写盘）
------------------------
1. 源文件 v10 的 SHA/大小符合登记值；
2. ``word/document.xml`` 中该标签 pPr 恰好 37 处，替换后仍 37 处、keepNext +37；
3. 把插入片段撤回后，``document.xml`` 与 v10 逐字节相同；
4. 除 ``word/document.xml`` 外，其余部件全部逐字节相同；
5. 全部 ``<w:t>`` 文本序列相同（= 没有改任何文字/数字）；
6. ``w:drawing``/``m:oMath``/``m:oMathPara``/``w:tbl``/顶层 ``w:p`` 计数不变；
7. 输出 zip 条目顺序/元数据与 v10 相同，``testzip()`` 无错。

纯标准库（climada_env 可直接跑）。默认 dry-run，``--apply`` 才写盘。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MS = PROJECT_ROOT / "manuscript"
DOCS = PROJECT_ROOT / "docs"

SRC = MS / "PAPER_MANUSCRIPT_v10.docx"
DST = MS / "PAPER_MANUSCRIPT_v11.docx"
REPORT = DOCS / "_v11_keepnext_check.json"

EXPECT_SRC_SHA = "40E306B03E2E54913CACF37CF62007226487BC3F879CE5ECADC186075BD1AD91"
EXPECT_SRC_SIZE = 28_193_015
EXPECT_LABEL_PARAS = 37

LABEL_PPR = '<w:pPr><w:pStyle w:val="ImageCaption"/></w:pPr>'
LABEL_PPR_FIXED = '<w:pPr><w:pStyle w:val="ImageCaption"/><w:keepNext/></w:pPr>'
INSERT = "<w:keepNext/>"

# 冻结版/`v10` 已登记的结构计数
EXPECT_STRUCT = {
    "w_drawing": 37,
    "m_oMath": 131,
    "m_oMathPara": 41,
    "w_tbl": 11,
    "top_level_w_p": 1162,
}

MEDIA_PREFIX = "word/media/"
DOC_PART = "word/document.xml"


def die(msg: str, code: int = 2):
    print("ERROR: %s" % msg)
    raise SystemExit(code)


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest().upper()


def sha_file(p: Path) -> str:
    return sha_bytes(p.read_bytes())


def read_parts(p: Path):
    with zipfile.ZipFile(p) as zf:
        infos = zf.infolist()
        parts = {i.filename: zf.read(i.filename) for i in infos}
        bad = zf.testzip()
    return infos, parts, bad


def struct_counts(xml: str) -> dict:
    body = re.search(r"<w:body>(.*)</w:body>", xml, re.S)
    body = body.group(1) if body else xml
    return {
        "w_drawing": len(re.findall(r"<w:drawing>", xml)),
        "m_oMath": len(re.findall(r"<m:oMath>", xml)),
        "m_oMathPara": len(re.findall(r"<m:oMathPara[ >]", xml)),
        "w_tbl": len(re.findall(r"<w:tbl>", xml)),
        "top_level_w_p": len(re.findall(r"<w:p\b[^>]*>.*?</w:p>|<w:p\b[^>]*/>", body, re.S)),
    }


def w_texts(xml: str):
    return re.findall(r"<w:t\b[^>]*>(.*?)</w:t>", xml, re.S)


def write_parts(dst: Path, infos, parts: dict):
    tmp = dst.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for info in infos:
            data = parts[info.filename]
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = info.external_attr
            zi.internal_attr = info.internal_attr
            zi.create_system = info.create_system
            zo.writestr(zi, data)
    tmp.replace(dst)


def main() -> int:
    ap = argparse.ArgumentParser(description="给图注短标签段落加 keepNext，v10 -> v11")
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--dst", type=Path, default=DST)
    ap.add_argument("--apply", action="store_true", help="真正写出 docx（默认 dry-run）")
    ap.add_argument("--overwrite", action="store_true", help="允许覆盖已存在的目标文件")
    args = ap.parse_args()

    src, dst = args.src, args.dst
    checks = []

    def check(name: str, ok: bool, detail: str = "") -> bool:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print("  [%s] %-46s %s" % ("PASS" if ok else "FAIL", name, detail))
        return bool(ok)

    print("=== 图注 keepNext 修复：%s -> %s (%s) ==="
          % (src.name, dst.name, "APPLY" if args.apply else "DRY-RUN"))
    if not src.is_file():
        die("源文件不存在：%s" % src)
    if dst.exists() and not args.overwrite:
        die("目标已存在（如确需覆盖请加 --overwrite）：%s" % dst)

    check("源文件 SHA 与登记值一致", sha_file(src) == EXPECT_SRC_SHA, sha_file(src)[:16])
    check("源文件大小与登记值一致", src.stat().st_size == EXPECT_SRC_SIZE,
          "%d B" % src.stat().st_size)
    if any(not c["ok"] for c in checks):
        die("源文件与登记值不符，拒绝继续")

    infos, parts, bad = read_parts(src)
    check("源 zip 完整性 testzip()", bad is None, "ok" if bad is None else str(bad))
    check("含 word/document.xml", DOC_PART in parts)

    doc = parts[DOC_PART].decode("utf-8")
    n_label = doc.count(LABEL_PPR)
    check("短标签段落 pPr 恰好 37 处", n_label == EXPECT_LABEL_PARAS, "%d 处" % n_label)
    if n_label != EXPECT_LABEL_PARAS:
        die("段落结构与预期不符，停止")

    n_keep_before = len(re.findall(r"<w:keepNext/>", doc))
    new_doc = doc.replace(LABEL_PPR, LABEL_PPR_FIXED)
    n_keep_after = len(re.findall(r"<w:keepNext/>", new_doc))
    check("替换后 keepNext +37", n_keep_after == n_keep_before + EXPECT_LABEL_PARAS,
          "%d -> %d" % (n_keep_before, n_keep_after))
    check("替换后短标签仍 37 处", new_doc.count(LABEL_PPR_FIXED) == EXPECT_LABEL_PARAS)

    # 可逆性：撤回插入后与 v10 逐字节相同
    reverted = new_doc.replace(LABEL_PPR_FIXED, LABEL_PPR)
    check("撤回插入后与 v10 document.xml 逐字节相同", reverted == doc,
          "len %d == %d" % (len(reverted), len(doc)))

    # 文本序列：一个字都没改
    check("全部 <w:t> 文本序列相同", w_texts(new_doc) == w_texts(doc),
          "%d 段文本" % len(w_texts(doc)))

    # 结构计数
    c_before, c_after = struct_counts(doc), struct_counts(new_doc)
    ok_struct = c_before == c_after == {k: EXPECT_STRUCT[k] for k in c_before}
    check("结构计数不变（drawing/oMath/oMathPara/tbl/p）", ok_struct,
          json.dumps(c_after, ensure_ascii=False))

    # 图块三段链完整性
    pat = re.compile(
        r'<w:p\b[^>]*>(?:(?!</w:p>).)*?<w:drawing>.*?</w:p>\s*'
        r'<w:p\b[^>]*><w:pPr><w:pStyle w:val="ImageCaption"/>(?:<w:keepNext/>)?</w:pPr>.*?</w:p>\s*'
        r'<w:p\b[^>]*><w:pPr><w:pStyle w:val="a0"/></w:pPr>', re.S)
    n_chain = len(pat.findall(new_doc))
    check("「图段 -> 短标签 -> 长图注」三段链齐全", n_chain == EXPECT_LABEL_PARAS,
          "%d/37 链" % n_chain)

    # 其余部件逐字节相同
    parts_new = dict(parts)
    parts_new[DOC_PART] = new_doc.encode("utf-8")
    changed = [n for n in parts if n != DOC_PART and parts_new[n] != parts[n]]
    check("除 document.xml 外其余部件逐字节相同", not changed,
          "全同（%d 部件）" % (len(parts) - 1) if not changed else str(changed[:5]))
    check("媒体部件仍 37 个",
          len([n for n in parts if n.startswith(MEDIA_PREFIX)]) == 37)

    ok_all = all(c["ok"] for c in checks)

    if args.apply and ok_all:
        write_parts(dst, infos, parts_new)
        # 回读校验
        infos2, parts2, bad2 = read_parts(dst)
        rt = {
            "zip_ok": bad2 is None,
            "entries_identical": [i.filename for i in infos2] == [i.filename for i in infos],
            "document_matches": sha_bytes(parts2[DOC_PART]) == sha_bytes(parts_new[DOC_PART]),
            "others_identical": all(parts2[n] == parts[n] for n in parts if n != DOC_PART),
            "struct_ok": struct_counts(parts2[DOC_PART].decode("utf-8")) == c_after,
        }
        ok_rt = all(rt.values())
        print("  [%s] 回读校验 %s" % ("PASS" if ok_rt else "FAIL", json.dumps(rt, ensure_ascii=False)))
        checks.append({"name": "回读校验", "ok": ok_rt, "detail": json.dumps(rt, ensure_ascii=False)})
        ok_all = ok_all and ok_rt
        dst_sha = sha_file(dst)
        dst_size = dst.stat().st_size
        print("\n写出：%s" % dst)
        print("       %d B  SHA256 %s" % (dst_size, dst_sha))
    else:
        dst_sha, dst_size = "", 0
        if args.apply:
            print("\n有断言未通过，未写盘。")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "tool": "tools/patch_figure_caption_keepnext.py",
        "mode": "apply" if args.apply else "dry-run",
        "src": str(src), "src_sha256": sha_file(src), "src_size": src.stat().st_size,
        "dst": str(dst), "dst_sha256": dst_sha, "dst_size": dst_size,
        "inserted": "<w:keepNext/> x %d on ImageCaption paragraphs" % EXPECT_LABEL_PARAS,
        "checks": checks,
        "verdict": "PASS" if ok_all else "FAIL",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n报告：%s" % REPORT)
    print("RESULT: %s" % ("PASS" if ok_all else "FAIL"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
