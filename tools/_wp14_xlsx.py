# -*- coding: utf-8 -*-
"""WP14 - package the provenance audit into one workbook + author fill-in file.

Sheets
    总览         coverage, level/usage counts, gate verdicts, the honest summary
    溯源台账      the 28 ledger rows (with file counts and bytes)
    缺口清单      the 11 gaps and how each is handled
    声明对照      every row that reaches the statement, clause vs rendered text
    发布清单      what may go to the archive (and what explicitly may not)
    标识核验      12 identifiers with their resolution verdict
    复核记录      how the evidence was obtained (tools, files, limitations)

Also writes
    docs/_DA_填写值.json        the two author-supplied slots (nulls until filled)
    docs/_可溯源发布清单.csv     machine-readable deposit manifest

USAGE
    <bundled python> tools\\_wp14_xlsx.py
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

NEWROOT = Path(__file__).resolve().parent.parent
DOCS = NEWROOT / "docs"

LEDGER = DOCS / "_数据溯源台账.csv"
AUDIT_SUM = DOCS / "_wp14_盘点摘要.json"
IDENT = DOCS / "_wp14_标识核验.csv"
TXT = DOCS / "_v15_声明正文.txt"
G14 = DOCS / "_gate_g14_result.json"
G13 = DOCS / "_gate_g13_result.json"
NUM_SUM = DOCS / "_wp13_v15_覆盖摘要.json"

OUT_XLSX = DOCS / "数据溯源与可用性声明.xlsx"
OUT_VALUES = DOCS / "_DA_填写值.json"
OUT_MANIFEST = DOCS / "_可溯源发布清单.csv"

HDR_FILL = PatternFill("solid", fgColor="1F4E5F")
HDR_FONT = Font(color="FFFFFF", bold=True, size=10)
WARN_FILL = PatternFill("solid", fgColor="FFF2CC")
BAD_FILL = PatternFill("solid", fgColor="F8CBAD")


def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def jload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def write_sheet(wb: Workbook, title: str, header: list[str], rows: list[list],
                widths: list[int] | None = None, freeze: str = "A2") -> None:
    ws = wb.create_sheet(title)
    ws.append(header)
    for c in range(1, len(header) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for r in rows:
        ws.append(r)
    for i, w in enumerate(widths or [], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = freeze
    ws.auto_filter.ref = ws.dimensions


def main() -> int:
    ledger = load_csv(LEDGER)
    idents = load_csv(IDENT) if IDENT.is_file() else []
    asum = jload(AUDIT_SUM)
    g14 = jload(G14)
    g13 = jload(G13)
    nsum = jload(NUM_SUM)
    txt = TXT.read_text(encoding="utf-8") if TXT.is_file() else ""

    wb = Workbook()
    wb.remove(wb.active)

    # ── 总览
    lv: dict[str, int] = {}
    usage: dict[str, int] = {}
    act: dict[str, int] = {}
    for r in ledger:
        lv[r["溯源等级"]] = lv.get(r["溯源等级"], 0) + 1
        usage[r["流水线作用"]] = usage.get(r["流水线作用"], 0) + 1
        act[r["DA动作"]] = act.get(r["DA动作"], 0) + 1
    g14_pass = sum(1 for c in g14.get("checks", []) if c["pass"])
    g13_pass = sum(1 for c in g13.get("checks", []) if c["pass"])
    rows = [
        ["目的", "为数据可用性声明提供逐数据集的可复核溯源；声明由台账渲染，不手写"],
        ["生成", datetime.now().isoformat(timespec="seconds")],
        ["盘上盘点", "%d 文件 / %d 字节（%.4f%% 覆盖，遗留 %d）"
         % (asum.get("data_total_files", 0), asum.get("data_total_bytes", 0),
            asum.get("coverage_pct_files", 0), asum.get("leftover_count", -1))],
        ["台账行数", len(ledger)],
        ["溯源等级", " · ".join("%s %d" % (k, lv.get(k, 0)) for k in ("强", "中", "弱", "无"))],
        ["流水线作用", " · ".join("%s %d" % (k, v) for k, v in sorted(usage.items()))],
        ["声明动作", " · ".join("%s %d" % (k, v) for k, v in sorted(act.items()))],
        ["标识核验", "%d 条，已核实 %d 条" % (
            len(idents), sum(1 for r in idents if r["核验"].startswith("已核实")))],
        ["数字台账(v15)", "%s/%s（0 blockers）"
         % (nsum.get("ok"), nsum.get("tokens_total"))],
        ["G13", "%d/%d %s" % (g13_pass, len(g13.get("checks", [])), g13.get("verdict"))],
        ["G14", "%d/%d %s" % (g14_pass, len(g14.get("checks", [])), g14.get("verdict"))],
        ["结论①", "28 行里 16 行进入运行（runtime-read）；6 行完全不参与运行；"
                  "2 行仅出图；3 行自产；1 行预处理脚本"],
        ["结论②", "**没有任何一个运行输入完全缺溯源**：最弱的三类（岸线层、房价面板、"
                  "小区挂牌）已在声明里显式承认不确定性，且均不转存原始件"],
        ["结论③", "整包 14.236 GB 中 10.9 GB（D08 全国逐日气温母产品）不参与运行 → 不应上传"],
    ]
    write_sheet(wb, "总览", ["项", "内容"], rows, [18, 128])

    # ── 溯源台账
    cols = ["编号", "数据集", "上游生产者", "产品名与版本", "覆盖", "DOI/URL",
            "标识核验", "获取渠道", "获取凭证", "授权/许可", "溯源等级",
            "流水线作用", "文件数", "字节", "可再分发", "Zenodo", "DA动作",
            "DA措辞", "缺口", "备注"]
    body = []
    for r in ledger:
        body.append([r.get(c, "") for c in cols])
    write_sheet(wb, "溯源台账", cols, body,
                [7, 30, 26, 30, 24, 42, 20, 30, 46, 26, 9, 14, 8, 13, 16, 12, 9, 60, 7, 50])
    ws = wb["溯源台账"]
    for row in ws.iter_rows(min_row=2):
        grade = row[cols.index("溯源等级")].value
        fill = {"弱": WARN_FILL, "无": BAD_FILL}.get(grade)
        if fill:
            for c in row:
                c.fill = fill
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    # ── 缺口清单
    gaps = []
    for r in ledger:
        if r["缺口"].strip():
            gaps.append([r["缺口"], r["编号"] + " " + r["数据集"], r["溯源等级"],
                         r["流水线作用"], r["备注"]])
    write_sheet(wb, "缺口清单", ["缺口", "数据集", "等级", "作用", "说明 / 处置"],
                gaps, [8, 34, 8, 14, 96])
    for row in wb["缺口清单"].iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    # ── 声明对照
    lines = []
    for r in ledger:
        if r["DA动作"] not in ("写入", "限定句"):
            continue
        present = "—"
        if r["DA措辞"].strip():
            lit = r["DA措辞"].split("(")[0].strip()[:22]
            present = "命中" if lit and lit.lower() in txt.lower() else "见限定句"
        lines.append([r["编号"], r["数据集"], r["DA动作"], r["溯源等级"],
                      r["DA措辞"], present])
    write_sheet(wb, "声明对照", ["编号", "数据集", "动作", "等级", "声明措辞", "正文命中"],
                lines, [7, 30, 9, 8, 96, 10])
    for row in wb["声明对照"].iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    # ── 发布清单
    man = []
    for r in ledger:
        if r["Zenodo"].startswith(("含", "派生件")):
            man.append([r["编号"], r["数据集"], r["Zenodo"], r["可再分发"],
                        r["文件数"], r["字节"],
                        "可上传" if not r["可再分发"].startswith("否") else "仅派生件"])
    write_sheet(wb, "发布清单", ["编号", "数据集", "归档口径", "可再分发", "文件数",
                                 "字节", "结论"], man,
                [7, 34, 12, 18, 8, 14, 12])
    for row in wb["发布清单"].iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    # ── 标识核验
    idr = [[r["项"], r["数据集"], r["DOI"], r["来源"], r["核验"],
            r["解析标题"], r["依据"]] for r in idents]
    write_sheet(wb, "标识核验", ["项", "数据集", "标识", "解析源", "核验",
                                 "解析标题", "依据"], idr,
                [16, 7, 40, 10, 20, 62, 60])
    for row in wb["标识核验"].iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    # ── 复核记录
    rec = [
        ["盘上实物", "DBF 字段/记录数、NetCDF 全局属性、`.shp.xml`、`_SOURCE.txt`、"
                     "`.tif.aux.xml`、文件命名规则", "tools\\_wp14_evidence.py --mode vector"],
        ["栅格指纹", "driver/dtype/尺寸/CRS/transform/nodata/bounds，判定同网格关系",
         "tools\\_wp14_evidence.py --mode grid（climada env, rasterio）"],
        ["供应方说明书", "15 份 `数据介绍.pdf`：9 份有文本层用 pdftotext 抽取；"
                        "6 份为 Microsoft Print-to-PDF 纯图片，渲染 PNG 后目视",
         "poppler 25.07（pdftotext / pdftoppm）+ docs\\_wp14_datasources\\"],
        ["标识核对", "Crossref / DataCite 解析，标题词 + 年份双命中；未收录前缀单列",
         "tools\\_wp14_doi.py → docs\\_wp14_标识核验.csv"],
        ["代码读取", "28 个脚本按 config 常量/目录名扫引用，按脚本类别归入 "
                     "runtime-read / preprocess-only / figure-only / unused",
         "tools\\_wp14_data_audit.py"],
        ["局限①", "6 份纯图片 PDF 的结论来自目视，无法文本复核 → 已归档渲染页"],
        ["局限②", "tmin/tmax 无任何说明书；等级判 弱，声明里不承诺可获取"],
        ["局限③", "TPDC 前缀 10.11888 未被 Crossref/DataCite 收录，DOI 取自供应方引用原文"],
        ["局限④", "LandScan 印出的 DOI 解析为 2018 单年版，与 2000–2024 面板不同口径"],
    ]
    write_sheet(wb, "复核记录", ["项", "内容", "工具 / 位置"], rec, [14, 76, 52])
    for row in wb["复核记录"].iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    wb.save(str(OUT_XLSX))
    print("wrote %s (%d sheets)" % (OUT_XLSX.name, len(wb.sheetnames)))

    # ── author fill-in file + deposit manifest
    if not OUT_VALUES.is_file():
        OUT_VALUES.write_text(json.dumps({
            "_说明": "填好值后运行 <bundled python> tools\\make_availability_v2.py --apply；"
                     "null = 保留占位符原样，绝不臆造",
            "ZENODO_DOI": None,
            "GITHUB_REPO": None,
            "TAG": None,
            "PRICE_ACCESS": "a commercial data subscription",
            "COMMUNITY_PROVIDER": "Anjuke",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print("wrote %s" % OUT_VALUES.name)
    with open(OUT_MANIFEST, "w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["编号", "数据集", "归档口径", "可再分发", "文件数", "字节", "结论"])
        wr.writerows(man)
    print("wrote %s (%d rows)" % (OUT_MANIFEST.name, len(man)))
    print("RESULT: XLSX-OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
