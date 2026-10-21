"""G11 闸门：v11 = v10 + 「图注短标签 keepNext」排版修复 的逐项证据。

Run:
    & ".\\env\\run.ps1" tools\\_gate_g11.py

断言（全部只读）
----------------
G11-1  冻结版 PAPER_MANUSCRIPT_FINAL.docx 未被动过（SHA/大小）
G11-2  v10 未被动过（SHA/大小）
G11-3  v11 存在、zip 完整、能解出 word/document.xml
G11-4  v11 与 v10 的差异部件**恰好只有** word/document.xml（48 个部件）
G11-5  v11 的 document.xml 撤回 37 个 ``<w:keepNext/>`` 后与 v10 逐字节相同
G11-6  37 个 ImageCaption 段落全部带 keepNext；且「图段 -> 短标签 -> 长图注」
       三段链 37/37 齐全（顺序与图号自洽）
G11-7  内容零变化：<w:t> 文本序列逐条相同、字号/公式/图/表/段落计数相同、
       styles.xml 与 v10 逐字节相同
G11-8  37 个媒体部件逐字节相同
G11-9  docs\\_v11_keepnext_check.json 存在且 verdict=PASS

退出码：0 全过 / 1 有 FAIL / 2 环境缺失。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
MS = NEWROOT / "manuscript"
DOCS = NEWROOT / "docs"
FIN = MS / "PAPER_MANUSCRIPT_FINAL.docx"
V10 = MS / "PAPER_MANUSCRIPT_v10.docx"
V11 = MS / "PAPER_MANUSCRIPT_v11.docx"
REPORT = DOCS / "_gate_g11_result.json"
KEEP_REPORT = DOCS / "_v11_keepnext_check.json"

FIN_SHA = "39240D38FCF71ADB72BEA285249AFE5757E0327F26253D48BE45FA899C772F14"
FIN_SIZE = 28_933_946
V10_SHA = "40E306B03E2E54913CACF37CF62007226487BC3F879CE5ECADC186075BD1AD91"
V10_SIZE = 28_193_015
V11_SHA = "7417FDE618D6C5114628B28C76C7E676141415EFA7BF50016BB13C2D472523CC"

DOC_PART = "word/document.xml"
STYLE_PART = "word/styles.xml"
LABEL_PPR = '<w:pPr><w:pStyle w:val="ImageCaption"/></w:pPr>'
LABEL_PPR_FIXED = '<w:pPr><w:pStyle w:val="ImageCaption"/><w:keepNext/></w:pPr>'
EXPECT_LABEL_PARAS = 37
EXPECT_PARTS = 49  # 48 个非 document.xml 部件 + document.xml
EXPECT_STRUCT = {"w_drawing": 37, "m_oMath": 131, "m_oMathPara": 41,
                 "w_tbl": 11, "top_level_w_p": 1162}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest().upper()


def sha_file(p: Path) -> str:
    return sha(p.read_bytes())


def parts_of(p: Path):
    with zipfile.ZipFile(p) as zf:
        infos = zf.infolist()
        data = {i.filename: zf.read(i.filename) for i in infos}
        bad = zf.testzip()
    return infos, data, bad


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


def main() -> int:
    passes: list[str] = []
    fails: list[tuple[str, str]] = []
    evidence: dict = {}

    def check(name: str, ok: bool, detail: str = ""):
        (passes if ok else fails).append(name)
        print("  [%s] %-52s %s" % ("PASS" if ok else "FAIL", name, detail))

    print("=== G11 gate：v11 排版修复证据 ===")
    for p in (FIN, V10, V11):
        if not p.is_file():
            print("ERROR: 缺少 %s" % p)
            return 2

    check("G11-1a 冻结版未被动过", sha_file(FIN) == FIN_SHA, sha_file(FIN)[:16])
    check("G11-1b 冻结版大小不变", FIN.stat().st_size == FIN_SIZE,
          "%d B" % FIN.stat().st_size)
    check("G11-2a v10 未被动过", sha_file(V10) == V10_SHA, sha_file(V10)[:16])
    check("G11-2b v10 大小不变", V10.stat().st_size == V10_SIZE,
          "%d B" % V10.stat().st_size)
    check("G11-3a v11 SHA 与登记值一致", sha_file(V11) == V11_SHA, sha_file(V11)[:16])
    check("G11-3b v11 大小", True, "%d B" % V11.stat().st_size)

    i10, p10, bad10 = parts_of(V10)
    i11, p11, bad11 = parts_of(V11)
    check("G11-3c 两个 zip 均完整", bad10 is None and bad11 is None,
          "%s / %s" % (bad10, bad11))
    check("G11-3d 部件数 48 且条目顺序一致",
          len(p10) == len(p11) == EXPECT_PARTS
          and [i.filename for i in i10] == [i.filename for i in i11],
          "%d 部件" % len(p11))

    changed = [n for n in p10 if p10[n] != p11[n]]
    check("G11-4 差异部件恰好只有 document.xml",
          changed == [DOC_PART], str(changed))
    evidence["changed_parts"] = changed

    d10 = p10[DOC_PART].decode("utf-8")
    d11 = p11[DOC_PART].decode("utf-8")
    n_fix = d11.count(LABEL_PPR_FIXED)
    reverted = d11.replace(LABEL_PPR_FIXED, LABEL_PPR)
    check("G11-5a 修复段落 37 处", n_fix == EXPECT_LABEL_PARAS, "%d 处" % n_fix)
    check("G11-5b 撤回插入后与 v10 逐字节相同", reverted == d10,
          "len %d == %d" % (len(reverted), len(d10)))
    check("G11-5c v11 比 v10 只多 37x16 字符",
          len(d11) - len(d10) == EXPECT_LABEL_PARAS * len("<w:keepNext/>"),
          "+%d 字符" % (len(d11) - len(d10)))

    # 段落级链条自洽：图段 -> 短标签(带 keepNext) -> 长图注
    body = re.search(r"<w:body>(.*)</w:body>", d11, re.S).group(1)
    paras = [m.group(0) for m in
             re.finditer(r"<w:p\b[^>]*>.*?</w:p>|<w:p\b[^>]*/>", body, re.S)]
    chain, bad_chain = 0, []
    for k, s in enumerate(paras):
        if LABEL_PPR_FIXED not in s:
            continue
        prev_ok = k > 0 and "<w:drawing>" in paras[k - 1]
        nxt_ok = (k + 1 < len(paras)
                  and '<w:pStyle w:val="a0"/>' in paras[k + 1]
                  and "Figure " in "".join(w_texts(paras[k + 1])))
        if prev_ok and nxt_ok:
            chain += 1
        else:
            bad_chain.append(k)
    check("G11-6 三段链 37/37 齐全且前后件正确",
          chain == EXPECT_LABEL_PARAS and not bad_chain,
          "%d/37%s" % (chain, ("; bad " + str(bad_chain[:5])) if bad_chain else ""))

    check("G11-7a <w:t> 文本序列逐条相同", w_texts(d11) == w_texts(d10),
          "%d 段文本" % len(w_texts(d10)))
    check("G11-7b 结构计数不变", struct_counts(d11) == struct_counts(d10) == EXPECT_STRUCT,
          json.dumps(struct_counts(d11), ensure_ascii=False))
    check("G11-7c styles.xml 与 v10 逐字节相同",
          p10[STYLE_PART] == p11[STYLE_PART], sha(p11[STYLE_PART])[:16])
    media10 = {n: sha(p10[n]) for n in p10 if n.startswith("word/media/")}
    media11 = {n: sha(p11[n]) for n in p11 if n.startswith("word/media/")}
    check("G11-8a 媒体 37 个且逐字节相同",
          len(media11) == 37 and media10 == media11, "%d 个" % len(media11))

    okrep = KEEP_REPORT.is_file() and json.loads(
        KEEP_REPORT.read_text(encoding="utf-8")).get("verdict") == "PASS"
    check("G11-9 修复工具报告 verdict=PASS", okrep, KEEP_REPORT.name)

    evidence.update({
        "v11_sha256": sha_file(V11), "v11_size": V11.stat().st_size,
        "inserted_keepnext": n_fix, "diff_chars": len(d11) - len(d10),
        "wf_texts": len(w_texts(d10)), "struct": struct_counts(d11),
    })
    print("")
    print("PASS %d / FAIL %d" % (len(passes), len(fails)))
    verdict = "PASS" if not fails else "FAIL"
    REPORT.write_text(json.dumps({
        "gate": "G11", "target": "manuscript/PAPER_MANUSCRIPT_v11.docx",
        "checks": passes, "failed": fails,
        "evidence": evidence, "verdict": verdict,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("报告：%s" % REPORT)
    print("RESULT: G11-%s" % verdict)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
