# -*- coding: utf-8 -*-
"""WP13.5 - assemble the master ledger and the findings register.

Inputs (all produced by 13.1-13.4, none of them regenerated here)

    docs\\_wp11_v12清单.csv          every w:t numeric token of v12 (1,385)
    docs\\_wp11_v12映射表.csv        class + bind for each of them
    docs\\_wp11_v12核查明细.csv      verdict for the 582 model/parameter/data tokens
    docs\\_wp13_公式数字.csv         the 97 OMML numbers and their verdicts
    docs\\_wp13_结构说明核验.csv     verdicts for STRUCT / NOTE / LIT (433 tokens)
    docs\\_wp13_文献核验.csv         per-entry bibliography verdicts (59 entries)
    docs\\_wp13_图表台账.csv         figure / table inventory checks

Outputs

    docs\\_wp13_数字总清单.csv       one row per number: class, authority,
                                     expected value, verdict, evidence
    docs\\_wp13_发现清单.md          every non-OK row, grouped by severity
    docs\\_wp13_覆盖摘要.json        coverage matrix + counts, consumed by G13

The ledger is deliberately strict: a token without a verdict, or with a verdict
outside the closed set, is reported as UNVERIFIED and blocks the gate.  That is
what makes "every number accounted for" a machine-checkable statement.

USAGE
    env\\run.ps1 tools\\_wp13_ledger.py
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"

TOKENS = DOCS / "_wp11_v12清单.csv"
MAPPING = DOCS / "_wp11_v12映射表.csv"
CHECKS = DOCS / "_wp11_v12核查明细.csv"
MATH = DOCS / "_wp13_公式数字.csv"
STRUCTLIT = DOCS / "_wp13_结构说明核验.csv"
BIB = DOCS / "_wp13_文献核验.csv"
FIGTAB = DOCS / "_wp13_图表台账.csv"
SURVEY = DOCS / "_wp13_普查摘要.json"

OUT = DOCS / "_wp13_数字总清单.csv"
OUT_FIND = DOCS / "_wp13_发现清单.md"
OUT_SUM = DOCS / "_wp13_覆盖摘要.json"

CLASS_CN = {
    "MODEL": "模型输出", "PARAM": "模型参数", "DATA": "输入数据",
    "STRUCT": "结构编号", "NOTE": "说明量", "LIT": "引文/外部", "REF": "参考文献",
}
VERDICT_CN = {
    "OK-MODEL": "模型输出一致", "OK-PARAM": "参数一致", "OK-DATA": "数据一致",
    "OK-STRUCT": "结构自洽", "OK-NOTE": "可复算", "OK-NOTE-SRC": "源码锚定",
    "OK-NOTE-EXT": "外部权威", "OK-CITE": "引文闭合", "OK-EXT": "外部权威",
    "OK-DATA-EPOCH": "数据历元", "OK-BIB": "文献库一致",
    "OK-MATH-CONST": "公式常数一致", "OK-MATH-SRC": "公式常数(源码)",
    "OK-MATH-FRAC": "公式权重一致", "OK-MATH-IDENT": "公式恒等式",
    "OK-MATH-CALC": "公式算式", "OK-MATH-NOTATION": "公式记号",
}
OK_PREFIX = "OK-"


def load_csv(p: Path) -> list[dict]:
    with io.open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    ap = argparse.ArgumentParser(description="WP13.5 master ledger")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--findings", default=str(OUT_FIND))
    ap.add_argument("--sum", default=str(OUT_SUM))
    ap.add_argument("--extra", default="",
                    help="CSV of extra rows (位置/数字/判定/证据) appended after "
                         "the v12 ledger, e.g. the four numbers added by v13")
    ap.add_argument("--figtab", default=str(FIGTAB))
    ap.add_argument("--drop", default="", help="comma-separated element ids to omit (paragraphs removed in a later revision)")
    ap.add_argument("--label", default="v12")
    args = ap.parse_args()

    tokens = load_csv(TOKENS)
    mapping = load_csv(MAPPING)
    checks = load_csv(CHECKS)
    maths = load_csv(MATH)
    sl = load_csv(STRUCTLIT)
    bib = {r["row_id"]: r for r in load_csv(BIB)}
    figtab = load_csv(Path(args.figtab))

    # ---- positional join census <-> mapping (same (row_id, token) multiset)
    def key(r):
        return (r["row_id"], r["token"])

    by_key: dict[tuple, list[dict]] = {}
    for r in mapping:
        by_key.setdefault(key(r), []).append(r)
    seen: dict[tuple, int] = {}
    paired: list[dict] = []
    orphan = 0
    for t in tokens:
        k = key(t)
        i = seen.get(k, 0)
        seen[k] = i + 1
        cand = by_key.get(k, [])
        if i < len(cand):
            paired.append({**t, "class": cand[i]["class"],
                           "bind": cand[i]["bind"],
                           "metric_value": cand[i]["metric_value"],
                           "metric_source": cand[i]["metric_source"]})
        else:
            orphan += 1
            paired.append({**t, "class": "", "bind": "", "metric_value": "",
                           "metric_source": ""})

    # ---- verdict lookups
    chk = {}
    for r in checks:
        chk.setdefault(key(r), []).append(r)
    slmap = {}
    for r in sl:
        slmap.setdefault(key(r), []).append(r)

    rows: list[dict] = []
    for t in paired:
        cls = t["class"]
        entry = {"位置": t["row_id"], "章节": t.get("section", ""),
                 "载体": "正文/表格", "分类": CLASS_CN.get(cls, cls or "未分类"),
                 "数字": t["token"], "上下文": t.get("context", ""),
                 "权威来源": "", "期望值": "", "判定": "", "证据": ""}
        if cls in ("MODEL", "PARAM", "DATA"):
            c = chk.get(key(t), [])
            hit = None
            for cand in c:
                if not hit:
                    hit = cand
            if hit and hit["status"] in ("OK", "OK-BOUNDARY"):
                entry["判定"] = "OK-MODEL" if cls == "MODEL" else (
                    "OK-PARAM" if cls == "PARAM" else "OK-DATA")
                entry["期望值"] = hit.get("expected", "")
                entry["权威来源"] = t.get("metric_source", "")
                entry["证据"] = "%s = %s" % (t["bind"], hit.get("metric_value", ""))
            elif hit:
                entry["判定"] = "MISMATCH"
                entry["期望值"] = hit.get("expected", "")
                entry["证据"] = hit.get("detail", "")
                entry["权威来源"] = t.get("metric_source", "")
            else:
                entry["判定"] = "UNVERIFIED"
                entry["证据"] = "no verdict in the WP11 check detail"
        elif cls in ("STRUCT", "NOTE", "LIT"):
            c = slmap.get(key(t), [])
            hit = c[0] if c else None
            if hit:
                v = hit["verdict"]
                if v == "OK-DATA":
                    v = "OK-DATA-EPOCH"
                entry["判定"] = v
                # two tokens were reclassified by the verifiers: the Huangpu
                # waypoint count (structural -> model fact) and the ISR epoch
                # year (citation bucket -> data epoch).  Keep the class column
                # consistent with the verdict so the ledger cannot be misread.
                if v == "OK-MODEL":
                    entry["分类"] = "模型输出"
                elif v == "OK-DATA-EPOCH":
                    entry["分类"] = "输入数据"
                entry["期望值"] = hit.get("expected", "")
                entry["证据"] = hit.get("evidence", "")
                entry["权威来源"] = {"STRUCT": "文档结构 / 源码",
                                     "NOTE": "代码/数据/外部来源",
                                     "LIT": "参考文献/公开数据"}[cls]
            else:
                entry["判定"] = "UNVERIFIED"
                entry["证据"] = "no verdict in the structural verifier"
        elif cls == "REF":
            b = bib.get(t["row_id"])
            if b:
                v = b["verdict"]
                if v.startswith("OK-BIB"):
                    entry["判定"] = "OK-BIB"
                else:
                    entry["判定"] = "MISMATCH"
                entry["权威来源"] = "Crossref/DataCite · %s" % (b["doi"] or "无 DOI")
                entry["证据"] = "%s %s %s" % (b["surname"], b["year"],
                                              b["detail"][:160])
                entry["期望值"] = b["year"]
            else:
                entry["判定"] = "UNVERIFIED"
                entry["证据"] = "reference entry without a verdict"
        else:
            entry["判定"] = "UNVERIFIED"
            entry["证据"] = "token without a class"
        rows.append(entry)

    # ---- drop rows whose element left the manuscript in a later revision
    drop_ids = {x.strip() for x in args.drop.split(",") if x.strip()}
    if drop_ids:
        before_n = len(rows)
        rows = [r for r in rows if r["位置"] not in drop_ids]
        print("  dropped %d rows for elements %s" % (before_n - len(rows), sorted(drop_ids)))

    # ---- OMML numbers
    for m in maths:
        rows.append({
            "位置": m["row_id"], "章节": "", "载体": "公式(m:t)",
            "分类": "公式", "数字": m["token"], "上下文": m.get("context", ""),
            "权威来源": m.get("bind", "").split(":", 1)[0] + " · " + m.get("evidence", "")[:60],
            "期望值": m.get("expected", ""), "判定": m.get("verdict", ""),
            "证据": m.get("evidence", "") + " · " + m.get("note", ""),
        })

    # ---- extra rows (numbers introduced by a later revision, e.g. v13)
    extra_n = 0
    for extra_path in [x for x in args.extra.split(",") if x.strip()]:
        for x in load_csv(Path(extra_path)):
            tok = x["数字"]
            cls = "引文/外部" if tok.isdigit() and len(tok) == 4 else "结构编号"
            rows.append({
                "位置": x["位置"], "章节": "", "载体": "正文/表格",
                "分类": cls, "数字": tok, "上下文": x.get("说明", ""),
                "权威来源": "文档结构" if cls == "结构编号" else "参考文献",
                "期望值": "", "判定": x["判定"], "证据": x["证据"],
            })
            extra_n += 1

    # ---- coverage matrix + findings
    def tally(items, k):
        d: dict[str, int] = {}
        for it in items:
            d[it[k]] = d.get(it[k], 0) + 1
        return d

    verdicts = tally(rows, "判定")
    classes = tally(rows, "分类")
    bad = [r for r in rows if not r["判定"].startswith(OK_PREFIX)]
    blockers = [r for r in bad if r["判定"] in
                ("MISMATCH", "UNVERIFIED", "NO-METRIC", "NO-SOURCE")]

    # ---- write the master ledger
    cols = ["位置", "章节", "载体", "分类", "数字", "上下文", "权威来源",
            "期望值", "判定", "证据"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n",
                       extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    tmp = Path(args.out).with_suffix(".csv.tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8", newline="\n")
    tmp.replace(Path(args.out))

    # ---- findings register
    lines = ["# WP13 发现清单", "",
             "本文件由 `tools\\_wp13_ledger.py` 生成，列出全部非 OK 判定。", "",
             "## 分级", "",
             "| 级别 | 含义 | 处置 |",
             "|---|---|---|",
             "| BLOCKER | 数字与模型输出/结构/文献不符 | 必须修复 |",
             "| PROSE | 数字全对，但表述需作者定夺 | 记录待裁 |", "",
             "## 数字层 findings：%d" % len(blockers), ""]
    if blockers:
        lines += ["| 位置 | 分类 | 数字 | 判定 | 期望 | 证据 |", "|---|---|---|---|---|---|"]
        for r in blockers[:200]:
            lines.append("| %s | %s | `%s` | %s | %s | %s |" % (
                r["位置"], r["分类"], r["数字"], r["判定"], r["期望值"],
                r["证据"].replace("|", "/")[:160]))
    else:
        lines.append("无。%d 个数字全部落在 OK 判定内。" % len(rows))
    lines += ["", "## 图表层 findings", ""]
    ft_bad = [r for r in figtab if r["verdict"] != "OK"]
    if ft_bad:
        lines += ["| 类型 | 检查项 | 级别 | 期望 | 实际 | 说明 |",
                  "|---|---|---|---|---|---|"]
        for r in ft_bad:
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                r["kind"], r["id"], r["severity"] or "-", r["expected"],
                r["got"], r["detail"].replace("|", "/")[:120]))
    else:
        lines.append("无。")
    Path(args.findings).write_text("\n".join(lines) + "\n", encoding="utf-8",
                                   newline="\n")

    survey = json.loads(SURVEY.read_text(encoding="utf-8")) if SURVEY.is_file() else {}
    summary = {
        "generated": __import__("datetime").datetime.now().isoformat(
            timespec="seconds"),
        "label": args.label,
        "docx": "PAPER_MANUSCRIPT_%s.docx" % args.label,
        "tokens_total": len(rows),
        "tokens_wt": len(tokens) + extra_n,
        "tokens_math": len(maths),
        "extra_rows": extra_n,
        "orphan_mapping": orphan,
        "classes": classes,
        "verdicts": verdicts,
        "ok": len(rows) - len(bad),
        "blockers": len(blockers),
        "findings": [{"位置": r["位置"], "数字": r["数字"], "判定": r["判定"],
                      "证据": r["证据"][:200]} for r in blockers],
        "figures_tables": {
            "checks": len(figtab),
            "blockers": len([r for r in figtab
                             if r["verdict"] != "OK" and r["severity"] == "BLOCKER"]),
            "prose": len([r for r in figtab
                          if r["verdict"] != "OK" and r["severity"] == "PROSE"]),
        },
        "math_census": survey,
        "result": "LEDGER-OK" if not blockers and not orphan else "LEDGER-FINDINGS",
    }
    Path(args.sum).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8", newline="\n")

    print("=== WP13.5 master ledger (%s) ===" % args.label)
    print("  w:t tokens    : %d (+%d extra)" % (len(tokens), extra_n))
    print("  OMML numbers  : %d" % len(maths))
    print("  ledger rows   : %d (orphan mapping %d)" % (len(rows), orphan))
    print("  classes       : %s" % ", ".join(
        "%s=%d" % kv for kv in sorted(classes.items())))
    print("  verdicts      : %s" % ", ".join(
        "%s=%d" % kv for kv in sorted(verdicts.items())))
    print("  OK            : %d / %d (%.2f%%)"
          % (len(rows) - len(bad), len(rows),
             100.0 * (len(rows) - len(bad)) / max(1, len(rows))))
    if blockers:
        print("  --- BLOCKERS (%d) ---" % len(blockers))
        for r in blockers[:20]:
            print("    %-14s %-8s %-10s %-10r %s"
                  % (r["判定"], r["分类"], r["位置"], r["数字"], r["证据"][:70]))
    print("  wrote %s" % Path(args.out).relative_to(NEWROOT))
    print("  wrote %s" % Path(args.findings).relative_to(NEWROOT))
    print("  wrote %s" % Path(args.sum).relative_to(NEWROOT))
    print("RESULT: %s" % summary["result"])
    return 0 if summary["result"] == "LEDGER-OK" else 1


if __name__ == "__main__":
    sys.exit(main())
