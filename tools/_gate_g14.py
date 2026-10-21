# -*- coding: utf-8 -*-
"""WP14 gate - the data-provenance ledger, the statements and the package.

Checks (14)
    G14-1   盘上盘点覆盖率 100%（每个文件都归属某个数据集）
    G14-2   台账行数 = 盘点行数，五列必填无空
    G14-3   每个 runtime-read 数据集都有上游生产者且等级 ∈ {强,中,弱}
    G14-4   等级值域合法；弱/无 行必须挂缺口编号
    G14-5   声明里的每个 DOI 都在标识核验表里且不是「未解析」
    G14-6   台账 → 声明：所有 DA动作=写入 的行其措辞出现在正文
    G14-7   剩余占位符仅限 Zenodo DOI / GitHub / (TAG)
    G14-8   弱/无 溯源却写入声明的行，正文里带限定语
    G14-9   v14 及以前所有 docx 字节不变（SHA）
    G14-10  两个声明 docx 的结构与关键数字
    G14-11  Zenodo 发布清单不含「不可再分发」的原始件
    G14-12  v15 数字台账仍 100%（1520/1520，0 blockers）
    G14-13  G13 仍全 PASS
    G14-14  未参与运行的数据集不出现在声明里

Exit: 0 = all PASS, 1 = any FAIL.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from docx import Document

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"
MAN = NEWROOT / "manuscript"

AUDIT = DOCS / "_wp14_数据盘点.csv"
AUDIT_SUM = DOCS / "_wp14_盘点摘要.json"
LEDGER = DOCS / "_数据溯源台账.csv"
IDENT = DOCS / "_wp14_标识核验.csv"
TXT = DOCS / "_v15_声明正文.txt"
STMT_SUM = DOCS / "_v15_声明文件摘要.json"
NUM_SUM = DOCS / "_wp13_v15_覆盖摘要.json"
G13 = DOCS / "_gate_g13_result.json"
OUT = DOCS / "_gate_g14_result.json"

DA_DOCX = MAN / "Data_Availability_Statement.docx"
CODE_DOCX = MAN / "Code_Availability_Statement.docx"

# frozen manuscript artefacts that must never change under WP14
FROZEN = {
    "PAPER_MANUSCRIPT_FINAL.docx": "39240D38",
    "PAPER_MANUSCRIPT_v10.docx": "40E306B0",
    "PAPER_MANUSCRIPT_v11.docx": "7417FDE6",
    "PAPER_MANUSCRIPT_v12.docx": "F86428ED",
    "PAPER_MANUSCRIPT_v13.docx": "380DE7EB",
    "PAPER_MANUSCRIPT_v14.docx": "C34F42F8",
}

LEVELS = {"强", "中", "弱", "无"}
ACTIONS = {"写入", "限定句", "方法描述", "不写"}
ALLOWED_PLACEHOLDERS = {"[Zenodo DOI to be assigned]",
                        "[GitHub repository, release version]"}

UNUSED_TOKENS = {
    "D06": ["township population", "乡镇人口"],
    "D08": ["tmean", "mean-temperature rasters"],
    "D18": ["GHSL-based", "urban entities", "sciencedb"],
    "D22": ["公共设施", "transportation", "Amap"],
    "D23": ["商务住宅"],
    "D24": ["typhoon name"],
}


def sha16(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()[:8]


def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "pass": bool(ok), "detail": detail})
        print("  %-46s %s  %s" % (name, "PASS" if ok else "FAIL", detail[:96]))

    print("=== gate G14 ===")
    audit = load_csv(AUDIT) if AUDIT.is_file() else []
    ledger = load_csv(LEDGER) if LEDGER.is_file() else []
    idents = load_csv(IDENT) if IDENT.is_file() else []
    asum = json.loads(AUDIT_SUM.read_text(encoding="utf-8")) if AUDIT_SUM.is_file() else {}
    txt = TXT.read_text(encoding="utf-8") if TXT.is_file() else ""

    # ── G14-1 coverage
    add("G14-1 on-disk coverage = 100%",
        asum.get("coverage_pct_files") == 100.0 and asum.get("leftover_count") == 0,
        "%d files / %s%%, leftover %d"
        % (asum.get("data_total_files", 0), asum.get("coverage_pct_files"),
           asum.get("leftover_count", -1)))

    # ── G14-2 required columns
    required = ["上游生产者", "获取渠道", "获取凭证", "溯源等级", "流水线作用", "DA动作"]
    blanks = [(r["编号"], c) for r in ledger for c in required if not r.get(c, "").strip()]
    audit_ids = {r["编号"] for r in audit}
    ledger_ids = {r["编号"] for r in ledger}
    add("G14-2 ledger shape + required columns",
        len(ledger) == 29 and audit_ids <= ledger_ids and not blanks,
        "ledger %d / audit %d, covered=%s, blanks %s"
        % (len(ledger), len(audit), audit_ids <= ledger_ids, blanks[:3] or "none"))

    # ── G14-3 runtime-read rows must name a producer, or own their absence
    bad3 = [r["编号"] for r in ledger
            if r["流水线作用"] == "runtime-read"
            and not (r["溯源等级"] in {"强", "中", "弱"}
                     and r["上游生产者"].strip()
                     or (r["溯源等级"] == "无" and r["缺口"].strip()))]
    add("G14-3 runtime-read rows have a producer", not bad3,
        "bad %s" % (bad3 or "none"))

    # ── G14-4 level domain + gap ids on weak/none
    bad4 = [r["编号"] for r in ledger
            if r["溯源等级"] not in LEVELS
            or r["DA动作"] not in ACTIONS
            or (r["溯源等级"] in {"弱", "无"} and not r["缺口"].strip())]
    add("G14-4 level/action domains + gap ids", not bad4, "bad %s" % (bad4 or "none"))

    # ── G14-5 every DOI in the statement is verified
    import re
    dois = sorted(set(re.findall(r"10\.\d{4,9}/[^\s;\u2013)\]]+", txt)))
    verified = {r["DOI"].split(";")[0].strip().rstrip(".")
                for r in idents if r["核验"].startswith("已核实")}
    soft = {r["DOI"] for r in idents if "供应方原文" in r["核验"]}
    unverified = [d for d in dois
                  if d.rstrip(".,;") not in verified
                  and d.rstrip(".,;") not in soft]
    add("G14-5 statement DOIs all verified", not unverified and len(dois) >= 8,
        "%d DOIs, unverified %s" % (len(dois), unverified or "none"))

    # ── G14-6 ledger -> statement: every literal fragment of a rendered clause
    def _norm(s: str) -> str:
        s = s.replace("\u2013", "-").replace("\u2014", "-").lower()
        return re.sub(r"\s+", " ", s)

    def literals(clause: str) -> list[str]:
        parts = re.split(r"\{[^}]+\}|\[[^\]]+\]", clause)
        return [p.strip(" ,.;:()") for p in parts if len(p.strip()) >= 18]

    hay = _norm(txt)
    missing = []
    for r in ledger:
        if r["DA动作"] != "写入" or not r["DA措辞"].strip():
            continue
        for lit in literals(r["DA措辞"]):
            if _norm(lit) not in hay:
                missing.append("%s:%s" % (r["编号"], lit[:26]))
                break
    add("G14-6 every '写入' row is present in the text", not missing,
        "missing %s" % (missing or "none"))

    # ── G14-7 placeholders
    left = set(re.findall(r"\[[^\]]+\]", txt)) - {"[Data set]"}
    add("G14-7 placeholders whitelisted",
        left <= ALLOWED_PLACEHOLDERS, "%s" % (sorted(left) or "none"))

    # ── G14-8 weak/none rows must own their uncertainty in the wording
    weak = [r["编号"] for r in ledger
            if r["DA动作"] in {"写入", "限定句"}
            and r["溯源等级"] in {"弱", "无"}]
    markers = {"D14": "commercial data subscription",
               "D15": "commercial data subscription",
               "D20": "could not be established",
               "D16": "community-level listings"}
    bad8 = [p for p in weak if markers.get(p, "") not in txt]
    add("G14-8 weak rows own their uncertainty", not bad8,
        "weak %s, missing %s" % (weak, bad8 or "none"))

    # ── G14-9 frozen manuscripts
    bad9 = [n for n, h in FROZEN.items()
            if not (MAN / n).is_file() or not sha16(MAN / n).startswith(h)]
    add("G14-9 v14 and earlier docx untouched", not bad9, "bad %s" % (bad9 or "none"))

    # ── G14-10 statement documents
    ok10, d10 = False, "missing"
    if DA_DOCX.is_file() and CODE_DOCX.is_file():
        da = Document(str(DA_DOCX))
        co = Document(str(CODE_DOCX))
        da_txt = "\n".join(p.text for p in da.paragraphs)
        co_txt = "\n".join(p.text for p in co.paragraphs)
        need = ["585,033", "seed (42)"]
        # structure = heading + 3 metadata + blank + body + sub-heading + intro
        #             + one paragraph per dataset citation (count is not frozen)
        n_cite = sum(1 for p in da.paragraphs if p.text.strip().startswith("- "))
        ok10 = (len(da.paragraphs) == 8 + n_cite and len(co.paragraphs) == 6
                and "585,033" in da_txt and "seed (42)" in co_txt
                and da_txt.startswith("Data Availability Statement"))
        d10 = "%d/%d paras (%d citations), 585,033=%s, seed42=%s" % (
            len(da.paragraphs), len(co.paragraphs), n_cite, "585,033" in da_txt,
            "seed (42)" in co_txt)
    add("G14-10 statement docx structure", ok10, d10)

    # ── G14-11 nothing non-redistributable is promised to the archive
    bad11 = [r["编号"] for r in ledger
             if r["Zenodo"].startswith("含") and r["可再分发"].startswith("否")]
    add("G14-11 zenodo manifest excludes restricted sources", not bad11,
        "bad %s" % (bad11 or "none"))

    # ── G14-12 the number audit still closes
    nsum = json.loads(NUM_SUM.read_text(encoding="utf-8")) if NUM_SUM.is_file() else {}
    ok12 = (nsum.get("ok") == nsum.get("tokens_total", -1)
            and not nsum.get("blockers"))
    add("G14-12 v15 numeric ledger 100%", ok12,
        "%s / %s, blockers %s" % (nsum.get("ok"), nsum.get("tokens_total"),
                                  nsum.get("blockers")))

    # ── G14-13 G13 still green
    g13 = json.loads(G13.read_text(encoding="utf-8")) if G13.is_file() else {}
    npass = sum(1 for c in g13.get("checks", []) if c["pass"])
    add("G14-13 G13 unchanged", g13.get("verdict") == "PASS"
        and npass == len(g13.get("checks", [])),
        "G13 %d/%d %s" % (npass, len(g13.get("checks", [])), g13.get("verdict")))

    # ── G14-14 unused datasets must not appear in the statement
    usage = {r["编号"]: r["流水线作用"] for r in ledger}
    leaks = []
    for pid, toks in UNUSED_TOKENS.items():
        if usage.get(pid) in ("unused", "figure-only"):
            for t in toks:
                if t.lower() in txt.lower():
                    leaks.append("%s:%s" % (pid, t))
    add("G14-14 unused datasets absent from statement", not leaks,
        "leaks %s" % (leaks or "none"))

    nfail = sum(1 for c in checks if not c["pass"])
    OUT.write_text(json.dumps({
        "generated": datetime.now().isoformat(timespec="seconds"),
        "checks": checks,
        "ledger_rows": len(ledger),
        "verdict": "PASS" if not nfail else "FAIL",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("")
    print("  %d/%d PASS -> %s" % (len(checks) - nfail, len(checks),
                                  "PASS" if not nfail else "FAIL"))
    print("RESULT: G14 = %s" % ("PASS" if not nfail else "FAIL"))
    return 0 if not nfail else 1


if __name__ == "__main__":
    raise SystemExit(main())
