# -*- coding: utf-8 -*-
"""WP14 - on-disk inventory of every input dataset + who actually reads it.

Why this exists
---------------
A Data Availability statement may only claim what a reader can act on.  Before
writing one we need two facts per dataset, both of which must come from the
repository rather than from memory:

  1. what is on disk (file count, bytes, which metadata files ship with it);
  2. whether the *model* reads it, or only a preprocessing/figure script, or
     nothing at all.

(2) matters because the package is a 14 GB corpus that contains material the
pipeline never touches (the Amap POI exports, the typhoon-name workbook, the
ETOPO grid itself).  Those rows must not be promised in the statement, and they
must not go to the archive either.

How usage is decided
--------------------
Each dataset declares ``code_tokens`` -- the literal identifiers that a script
would have to mention in order to touch it (config constants such as
``TMIN_RASTER_DIR``, or a directory basename such as ``上海小区数据（链家）``).
The scan then classifies every hit by the *kind* of script that contains it:

    Climate/Finance/Composite + run_v8.py, minus preprocess_*  -> runtime-read
    preprocess_*.py                                            -> preprocess-only
    basic_facts / generate_figures* / historical_tc / maps      -> figure-only
    tools/                                                     -> ignored
    nowhere                                                    -> unused

Outputs
-------
    docs/_wp14_数据盘点.csv      one row per dataset
    docs/_wp14_盘点摘要.json     totals + coverage verdict + leftovers

USAGE
    <bundled python> tools\\_wp14_data_audit.py
    <bundled python> tools\\_wp14_data_audit.py --csv docs/xxx.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DATA = NEWROOT / "data"
DOCS = NEWROOT / "docs"

OUT_CSV = DOCS / "_wp14_数据盘点.csv"
OUT_SUMMARY = DOCS / "_wp14_盘点摘要.json"

# ── logical datasets ────────────────────────────────────────────────────────
# (slug, 名称, [directory roots under data\ (recursive)], [single files], [code tokens])
DATASETS: list[tuple[str, str, list[str], list[str], list[str]]] = [
    ("D01", "IBTrACS 台风最佳路径（WP 盆 v04r01，含钉住旧快照）",
     [r"Hazard_data\WP台风数据"], [],
     ["IBTRACS_FILE", "IBTrACS"]),
    ("D02", "FABDEM V1-2 森林冠层校正 DEM（30 m）",
     [r"Hazard_data\N30E120-N40E130_FABDEM_V1-2"], [],
     ["FABDEM_DIR", "FABDEM_TILES_SHANGHAI", "FABDEM"]),
    ("D03", "ETOPO 2022 全球地形（15 arc-s，仅用于派生陆架参数）",
     [], [r"Hazard_data\ETOPO_2022_v1_30s_N90W180_bed.tif"],
     ["ETOPO"]),
    ("D04", "LandScan 逐年人口栅格（1 km，2000–2024）",
     [r"Exposure_data\人口\2000-2024年上海1km精度人口分布栅格数据"], [],
     ["LANDSCAN_DIR", "LANDSCAN"]),
    ("D05", "第五 / 六 / 七次全国人口普查（街道人口 + 区县受教育情况）",
     [r"Exposure_data\人口\上海第五次人口普查街道数据",
      r"Exposure_data\人口\上海第六次人口普查街道数据",
      r"Exposure_data\人口\上海第七次人口普查街道数据",
      r"Exposure_data\人口\上海区县层级的人口受教育情况-五六七普人口"], [],
     ["CENSUS_5TH_DIR", "CENSUS_6TH_DIR", "CENSUS_7TH_DIR"]),
    ("D06", "逐年乡镇人口（LandScan 聚合派生）",
     [r"Exposure_data\人口\2000-2024年上海逐年乡镇人口数量数据"], [],
     ["TOWNSHIP_POP_DIR"]),
    ("D07", "逐月全风速栅格（1951–2024，0.1°）",
     [r"Hazard_data\1951-2024年上海逐月全风速栅格数据"], [],
     ["WIND_RASTER_DIR", "wind_"]),
    ("D08", "逐月平均气温栅格（2005–2025 产品，上海 0.1°）",
     [r"Hazard_data\2005-2025年我国逐日平均气温栅格数据"], [],
     ["tmean"]),
    ("D09", "逐月降水栅格（1960–2024，0.1°）",
     [r"Hazard_data\1960-2024年上海逐月降水栅格数据"], [],
     ["PRECIP_RASTER_DIR"]),
    ("D10", "逐月最低气温栅格（1981–2024，0.05°）",
     [r"Hazard_data\1981-2024年上海逐月最低气温栅格数据"], [],
     ["TMIN_RASTER_DIR", "tmin_"]),
    ("D11", "逐月最高气温栅格（1981–2024，0.05°）",
     [r"Hazard_data\1981-2024年上海逐月最高气温栅格数据"], [],
     ["TMAX_RASTER_DIR", "tmax_"]),
    ("D12", "逐月海平面高度异常栅格（1993–2023，0.125°）",
     [r"Hazard_data\1993-2023年上海逐月海平面高度数据"], [],
     ["SLA_DIR", "sla_"]),
    ("D13", "逐年不透水面比例栅格（1985/90/…/2020，0.01°）",
     [r"Hazard_data\1985-2020年上海逐年不透水面栅格数据"], [],
     ["ISR_DIR"]),
    ("D14", "全市逐月二手房价格（2011-01–2025-07）",
     [r"Exposure_data\房屋\2011-2025年上海逐月二手房房价数据"], [],
     ["CITY_PRICE_DIR", "CITY_PRICE_EXCEL"]),
    ("D15", "区县逐月二手房价格（2015-01–2025-07）",
     [r"Exposure_data\房屋\2015-2025年上海逐月区县二手房房价数据"], [],
     ["DISTRICT_PRICE_DIR", "DISTRICT_PRICE_EXCEL"]),
    ("D16", "小区级挂牌资料（均价 / 竣工时间 / 35 字段，目录名「链家」）",
     [r"Exposure_data\房屋\上海小区数据（链家）"], [],
     ["LIANJIA_POI_DIR", "上海小区数据（链家）"]),
    ("D17", "2024 年多属性建筑矢量（CMAB 派生，25 个 shp 瓦片）",
     [r"Exposure_data\房屋\2024年上海多属性建筑矢量数据"], [],
     ["BUILDING_VECTOR_DIR"]),
    ("D18", "1975–2020 城市建成区矢量（GHSL 派生，10 期）",
     [r"Exposure_data\房屋\1975-2020年上海城市建成区矢量数据"], [],
     ["BUILT_UP_AREA_DIR"]),
    ("D19", "官方区县边界层 GS(2024)0650（含上游母产品与说明书）",
     [r"我国乡镇（街道）行政区划数据\_官方_天地图GS2024-0650",
      r"我国乡镇（街道）行政区划数据\202405更新_2024年省市县三级行政区划数据（审图号：GS（2024）0650号）"],
     [r"我国乡镇（街道）行政区划数据\2024年省市县行政区划数据.pdf"],
     ["ADMIN_BOUNDARY_SHP", "_官方_天地图"]),
    ("D20", "2021 年全国乡镇（街道）边界层（岸线 / 预处理裁剪掩膜）",
     [], [r"我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.shp",
          r"我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.dbf",
          r"我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.shx",
          r"我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.prj",
          r"我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.cpg",
          r"我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.sbn",
          r"我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.sbx",
          r"我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.shp.xml",
          r"我国乡镇（街道）行政区划数据\我国乡镇（街道）行政区划数据.pdf"],
     ["ADMIN_BOUNDARY_LEGACY_SHP", "COASTLINE_BOUNDARY_SHP",
      "2021年我国乡镇（街道）边界数据"]),
    ("D21", "《中国海洋灾害公报》原件 + 1995–2023 损失转录表（校准目标）",
     [r"中国海洋灾害公报"], [r"风暴潮台风损害影响1995_2023.xlsx"],
     ["海洋灾害公报", "风暴潮台风损害"]),
    ("D22", "高德 POI 导出（公共设施 11 类 + 交通运输 3 类）",
     [r"Exposure_data\公共设施", r"Exposure_data\交通运输"], [],
     ["FACILITY_DIR"]),
    ("D23", "高德 POI「商务住宅」小区导出",
     [r"Exposure_data\房屋\上海小区数据（高德）"], [],
     ["上海小区数据（高德）"]),
    ("D24", "影响上海的台风名录（作者整理，2000–2023）",
     [], [r"影响上海的台风记录2000_2023.xlsx"],
     ["影响上海的台风记录"]),
    ("D28", "随包携带的预处理脚本（data\\ 下 preprocess_*.py）",
     [], [r"Exposure_data\preprocess_exposure.py",
          r"Exposure_data\人口\上海区县层级的人口受教育情况-五六七普人口\preprocess_education.py",
          r"Exposure_data\人口\上海第七次人口普查街道数据\preprocess_census_7.py",
          r"Exposure_data\人口\上海第五次人口普查街道数据\preprocess_census_5.py",
          r"Exposure_data\人口\上海第六次人口普查街道数据\preprocess_census_6.py",
          r"Hazard_data\1951-2024年上海逐月全风速栅格数据\preprocess_clip_wind.py",
          r"Hazard_data\1960-2024年上海逐月降水栅格数据\preprocess_clip_precipitation.py",
          r"Hazard_data\1981-2024年上海逐月最低气温栅格数据\preprocess_clip_tmin.py",
          r"Hazard_data\1981-2024年上海逐月最高气温栅格数据\preprocess_clip_tmax.py",
          r"Hazard_data\1985-2020年上海逐年不透水面栅格数据\preprocess_impervious.py",
          r"Hazard_data\1993-2023年上海逐月海平面高度数据\preprocess_clip_sla.py",
          r"Hazard_data\2005-2025年我国逐日平均气温栅格数据\preprocess_aggregate_tmean_monthly.py",
          r"Hazard_data\WP台风数据\preprocess_copy_typhoon.py"],
     ["preprocess_"]),
]

# usage note overrides where the automatic verdict needs a qualifier
USAGE_NOTE = {
    "D03": "参数派生：仅 L_SHELF_M=550 km / H_SHELF_M=55 m 两个常数取自 ETOPO，栅格本体从不被读取",
    "D08": "生成 tmean_shanghai.xlsx 后无任何步骤读取（热应激用 Tmax）",
    "D21": "不参与运行；1995–2023 报告损失序列是该模型校准与验证的目标",
    "D22": "不参与运行，稿件 Methods 亦未描述",
    "D23": "仅被 preprocess_exposure.py 原样复制，无下游读取",
    "D24": "不参与运行（preprocess_copy_typhoon.py 仅作归档参考）",
    "D06": "仅 basic_facts.py 出图使用",
    "D18": "仅 basic_facts / generate_figures 出图使用",
    "D28": "预处理脚本自身（非数据）；记录在此以便覆盖率闭合",
}

# automatic verdict is impossible/meaningless for these (no downstream reader)
USAGE_OVERRIDE = {"D28": "preprocess-only"}

# self-produced artefacts: no file walk, sizes come from the code tree
SELF_MADE = [
    ("D25", "处理后面板与结果表", "Climate\\output\\results + Finance\\results + Composite\\results"),
    ("D26", "图表源数据与渲染图（41 张 + 表 1–8）", "manuscript\\figures + Climate\\output\\figures"),
    ("D27", "模型代码与灵敏度配置", "run_v8.py + Climate\\ + Finance\\ + Composite\\ + config\\ + env\\"),
]

PIPELINE_DIRS = ("Climate", "Finance", "Composite")
ENTRY_SCRIPTS = ("run_v8.py", "run_sensitivity.py")
FIGURE_MARKERS = ("basic_facts", "generate_figures", "historical_tc", "maps.py",
                  "visualization")


def classify(script_rel: str) -> str:
    """Map a script path to the usage bucket it contributes to."""
    name = Path(script_rel).name
    top = script_rel.split("\\")[0].split("/")[0]
    if script_rel.startswith("tools"):
        return "ignore"
    if name.startswith("preprocess_alias"):        # pragma: no cover
        return "ignore"
    if name.startswith("preprocess"):
        return "preprocess-only"
    if any(m in script_rel for m in FIGURE_MARKERS):
        return "figure-only"
    if top in PIPELINE_DIRS or name in ENTRY_SCRIPTS:
        return "runtime-read"
    return "other"


def iter_scripts() -> list[Path]:
    out = []
    for p in NEWROOT.rglob("*.py"):
        rel = str(p.relative_to(NEWROOT)).replace("/", "\\")
        if rel.startswith(("tools\\", "env\\", "output_archive\\",
                           "data\\", "_sensitivity_results\\")):
            continue
        out.append(p)
    return sorted(out)


def scan_tokens(scripts: list[Path]) -> dict[str, list[tuple[str, int, str]]]:
    """token -> [(script_rel, lineno, bucket)]"""
    hits: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for p in scripts:
        rel = str(p.relative_to(NEWROOT)).replace("/", "\\")
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        bucket = classify(rel)
        for i, line in enumerate(lines, 1):
            for _slug, _title, _roots, _files, tokens in DATASETS:
                for tok in tokens:
                    if tok in line:
                        hits[tok].append((rel, i, bucket))
    return hits


def walk_dataset(roots: list[str], files: list[str]) -> tuple[int, int, dict[str, int], list[str], set[Path]]:
    picked: dict[Path, None] = {}
    for rel in roots:
        base = DATA / rel
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if f.is_file():
                picked[f] = None
    for rel in files:
        f = DATA / rel
        if f.is_file():
            picked[f] = None
    nbytes = sum(f.stat().st_size for f in picked)
    ext: dict[str, int] = defaultdict(int)
    for f in picked:
        ext[f.suffix.lower() or "(none)"] += 1
    meta = sorted({f.name for f in picked
                   if f.suffix.lower() in (".pdf", ".txt", ".xml", ".json")
                   or f.name.startswith("preprocess_")
                   or f.name.startswith("_")})
    return len(picked), nbytes, dict(ext), meta, set(picked)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(OUT_CSV))
    args = ap.parse_args()
    out_csv = Path(args.csv)

    print("=== WP14 data audit ===")
    scripts = iter_scripts()
    print("  scripts scanned: %d" % len(scripts))
    hits = scan_tokens(scripts)

    rows = []
    assigned: dict[Path, str] = {}
    problems: list[str] = []

    for slug, title, roots, files, tokens in DATASETS:
        nfiles, nbytes, ext, meta, picked = walk_dataset(roots, files)
        if nfiles == 0:
            problems.append("%s: 0 files" % slug)
        for f in picked:
            prev = assigned.get(f)
            if prev and prev != slug and "D28" not in (prev, slug):
                problems.append("%s 同时命中 %s 与 %s" % (f.name, prev, slug))
            assigned[f] = slug

        buckets: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for tok in tokens:
            for rel, lineno, bucket in hits.get(tok, []):
                if Path(rel).name == "00_config.py":
                    continue          # definition site, not a reader
                buckets[bucket].append((rel, lineno))
        order = ["runtime-read", "preprocess-only", "figure-only", "other"]
        usage = "unused"
        readers = []
        for b in order:
            if buckets.get(b):
                usage = b
                seen = set()
                for rel, lineno in sorted(buckets[b]):
                    key = (rel, lineno)
                    if key in seen:
                        continue
                    seen.add(key)
                    readers.append("%s:%d" % (rel, lineno))
                break
        usage = USAGE_OVERRIDE.get(slug, usage)
        rows.append({
            "编号": slug,
            "数据集": title,
            "文件数": nfiles,
            "字节": nbytes,
            "扩展名分布": "; ".join("%s×%d" % (k, v) for k, v in sorted(ext.items())),
            "元数据/说明件": "; ".join(meta[:6]),
            "流水线作用": usage,
            "读取者": "; ".join(readers[:8]),
            "读取点数量": len(readers),
            "代码命中桶": "; ".join("%s=%d" % (b, len(buckets[b]))
                                    for b in order if buckets.get(b)),
            "作用备注": USAGE_NOTE.get(slug, ""),
        })
        print("  %-4s %-6s files=%-6d bytes=%-11d %s"
              % (slug, usage, nfiles, nbytes, title[:26]))

    # ── coverage: every file under data\ must belong to exactly one dataset
    all_files = [p for p in DATA.rglob("*") if p.is_file()]
    leftover = [p for p in all_files if p not in assigned]
    for p in leftover:
        problems.append("未被任何数据集覆盖: %s" % p.relative_to(DATA))

    total_files = len(all_files)
    total_bytes = sum(p.stat().st_size for p in all_files)
    covered_files = total_files - len(leftover)
    covered_bytes = sum(p.stat().st_size for p in assigned)

    with open(out_csv, "w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    usage_count: dict[str, int] = defaultdict(int)
    for r in rows:
        usage_count[r["流水线作用"]] += 1

    summary = {
        "n_datasets": len(rows),
        "self_made": [{"id": s, "name": n, "where": w} for s, n, w in SELF_MADE],
        "data_total_files": total_files,
        "data_total_bytes": total_bytes,
        "covered_files": covered_files,
        "covered_bytes": covered_bytes,
        "coverage_pct_files": round(100.0 * covered_files / total_files, 4),
        "leftover_files": [str(p.relative_to(DATA)) for p in leftover][:40],
        "leftover_count": len(leftover),
        "usage_count": dict(usage_count),
        "problems": problems[:40],
        "problem_count": len(problems),
        "csv": out_csv.name,
    }
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")

    print("")
    print("  data\\ total: %d files / %d B" % (total_files, total_bytes))
    print("  covered    : %d files / %d B (%.4f%%)"
          % (covered_files, covered_bytes, summary["coverage_pct_files"]))
    print("  usage      : %s" % dict(usage_count))
    if leftover:
        print("  LEFTOVER   : %d" % len(leftover))
        for p in leftover[:10]:
            print("     %s" % p.relative_to(DATA))
    if problems:
        print("  PROBLEMS   : %d" % len(problems))
        for p in problems[:10]:
            print("     %s" % p)
    print("  wrote %s" % out_csv.name)
    print("RESULT: AUDIT-%s" % ("OK" if not leftover else "INCOMPLETE"))
    return 0 if not leftover else 3


if __name__ == "__main__":
    raise SystemExit(main())
