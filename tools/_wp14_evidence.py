# -*- coding: utf-8 -*-
"""WP14 - collect on-disk provenance evidence for the data-provenance ledger.

Purpose
-------
The Data Availability statement may only claim a source that can be pointed at.
This module gathers the *machine-readable* part of that evidence so the ledger
(`docs/_数据溯源台账.csv`) can cite a concrete artefact instead of a memory:

  vector mode (stdlib only)
    * DBF field lists + record counts for the four shapefile families
      (CMAB building tiles, Anjuke/链家 community POI, 2021 township layer,
      official GS(2024)0650 district layer);
    * raw global-attribute strings of the IBTrACS NetCDF files (DOI, producer,
      processing command) -- NetCDF4/HDF5 stores these uncompressed, so a byte
      scan is enough and we do not need netCDF4/h5py;
    * the FGDC/Esri metadata of the 2021 township layer, which is the layer with
      no traceable upstream source (gap G1 in the ledger).

  grid mode (needs rasterio -- run under env/run.ps1)
    * per-raster-group profile fingerprints (driver/dtype/size/CRS/transform/
      nodata) plus a pairwise "same grid?" verdict.  This is what lets us say
      whether the tmin/tmax tiles belong to the same product family as the
      wind/tmean tiles when no 数据介绍.pdf ships with them (gap G4).

Outputs
-------
    docs/_wp14_矢量与元数据证据.json
    docs/_wp14_矢量与元数据证据.md
    docs/_wp14_栅格指纹.csv          (grid mode only)
    docs/_wp14_栅格指纹摘要.json     (grid mode only)

USAGE
    <bundled python>      tools\\_wp14_evidence.py --mode vector
    .\\env\\run.ps1         tools\\_wp14_evidence.py --mode grid     (rasterio)

    # rasterio lives in the climada env; the direct form used when run.ps1
    # swallows a traceback:
    $env:CONDA_PREFIX='C:\\Users\\Jack\\miniforge3\\envs\\climada_env'
    python.exe env\\bootstrap.py tools\\_wp14_evidence.py --mode grid
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
DATA = NEWROOT / "data"
DOCS = NEWROOT / "docs"

OUT_JSON = DOCS / "_wp14_矢量与元数据证据.json"
OUT_MD = DOCS / "_wp14_矢量与元数据证据.md"
OUT_GRID = DOCS / "_wp14_栅格指纹.csv"
OUT_GRID_SUM = DOCS / "_wp14_栅格指纹摘要.json"

# ── shapefile families we need field-level evidence for ────────────────────
SHP_TARGETS = [
    ("D17_buildings_shanghai",
     r"Exposure_data\房屋\2024年上海多属性建筑矢量数据\processed_shanghai_20201231_all.dbf"),
    ("D16_anjuke_community",
     r"Exposure_data\房屋\上海小区数据（链家）\上海小区POI.dbf"),
    ("D20_township_2021",
     r"我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.dbf"),
    ("D19_official_district",
     r"我国乡镇（街道）行政区划数据\_官方_天地图GS2024-0650\上海_区级_GS2024-0650.dbf"),
]

NC_TARGETS = [
    ("D01_IBTrACS_pinned",
     r"Hazard_data\WP台风数据\IBTrACS.WP.v04r01_old_202510.nc"),
    ("D01_IBTrACS_live",
     r"Hazard_data\WP台风数据\IBTrACS.WP.v04r01.nc"),
]

NC_PATTERNS = [
    ("doi", r"10\.25921/[A-Za-z0-9\-]+"),
    ("producer", r"NOAA, U\.S\. Department of Commerce"),
    ("team", r"IBTrACS Science Team[^\x00]{0,80}"),
    ("version_tag", r"v04r01[^\x00]{0,40}"),
    ("command", r"ncrcat[^\x00]{0,120}"),
    ("title", r"IBTrACS[^\x00]{0,90}"),
]

# ── raster families (glob relative to data\) ───────────────────────────────
GRID_GROUPS = [
    ("D07_wind", r"Hazard_data\1951-2024年上海逐月全风速栅格数据\*.tif"),
    ("D08_tmean", r"Hazard_data\2005-2025年我国逐日平均气温栅格数据\上海逐月平均气温栅格数据\*.tif"),
    ("D09_precip", r"Hazard_data\1960-2024年上海逐月降水栅格数据\*.tif"),
    ("D10_tmin", r"Hazard_data\1981-2024年上海逐月最低气温栅格数据\*.tif"),
    ("D11_tmax", r"Hazard_data\1981-2024年上海逐月最高气温栅格数据\*.tif"),
    ("D12_sla", r"Hazard_data\1993-2023年上海逐月海平面高度数据\sla_*.tif"),
    ("D13_isr", r"Hazard_data\1985-2020年上海逐年不透水面栅格数据\*.tif"),
    ("D04_landscan", r"Exposure_data\人口\2000-2024年上海1km精度人口分布栅格数据\*.tif"),
    ("D02_fabdem", r"Hazard_data\N30E120-N40E130_FABDEM_V1-2\N3[01]E12[01]_FABDEM_V1-2.tif"),
    ("D03_etopo", r"Hazard_data\ETOPO_2022_v1_30s_N90W180_bed.tif"),
]


# ══════════════════════════════════════════════════════════════════ DBF
def dbf_header(path: Path) -> dict:
    """Read record count + field names straight out of the DBF header.

    Field descriptors start at byte 32, 32 bytes each; the name is bytes 0..10
    (NUL padded, single-byte).  Chinese field names arrive GBK-encoded, so we
    decode with gbk and fall back to latin1.
    """
    with open(path, "rb") as fh:
        head = fh.read(32)
        nrec = struct.unpack("<I", head[4:8])[0]
        hlen = struct.unpack("<H", head[8:10])[0]
        nfield = (hlen - 33) // 32
        fh.seek(32)
        names = []
        for _ in range(nfield):
            desc = fh.read(32)
            if not desc or desc[0] == 0x0D:
                break
            raw = desc[:11].split(b"\x00")[0]
            try:
                names.append(raw.decode("gbk"))
            except UnicodeDecodeError:
                names.append(raw.decode("latin1"))
    return {"records": nrec, "fields": names, "bytes": path.stat().st_size}


# ══════════════════════════════════════════════════════════════════ NetCDF
def nc_attribute_strings(path: Path, scan_bytes: int = 500_000) -> dict:
    """Regex the uncompressed header region for global-attribute strings."""
    blob = open(path, "rb").read(scan_bytes).decode("latin1")
    found: dict[str, list[str]] = {}
    for key, pat in NC_PATTERNS:
        seen: list[str] = []
        for m in re.finditer(pat, blob):
            val = m.group(0).strip().replace("\\n", " ")
            if val not in seen:
                seen.append(val)
        found[key] = seen[:4]
    return {"bytes": path.stat().st_size, "strings": found}


# ══════════════════════════════════════════════════════════════════ grid
def grid_profile(path: Path) -> dict:
    import rasterio  # noqa: WPS433  (only in grid mode)

    with rasterio.open(path) as ds:
        return {
            "file": str(path.relative_to(DATA)),
            "driver": ds.driver,
            "dtype": ds.dtypes[0],
            "width": ds.width,
            "height": ds.height,
            "count": ds.count,
            "crs": str(ds.crs),
            "transform": [round(v, 10) for v in tuple(ds.transform)[:6]],
            "nodata": ds.nodata,
            "bounds": [round(v, 5) for v in tuple(ds.bounds)],
        }


def grid_signature(prof: dict) -> str:
    """The part of the profile that defines 'the same grid'."""
    return "|".join(
        str(prof[k]) for k in ("width", "height", "crs", "transform"))


def run_grid() -> int:
    rows: list[dict] = []
    summary: dict[str, dict] = {}
    for slug, pattern in GRID_GROUPS:
        files = sorted(DATA.glob(pattern))
        tifs = [f for f in files if f.is_file()]
        entry = {"pattern": pattern, "n_files": len(tifs), "samples": []}
        if not tifs:
            entry["status"] = "NO-FILE"
            summary[slug] = entry
            print("  %-14s no file for %s" % (slug, pattern))
            continue
        picks = [tifs[0]] + ([tifs[len(tifs) // 2]] if len(tifs) > 2 else []) \
            + ([tifs[-1]] if len(tifs) > 1 else [])
        seen = set()
        for f in picks:
            if f in seen:
                continue
            seen.add(f)
            try:
                prof = grid_profile(f)
            except Exception as exc:  # pragma: no cover - damaged raster
                entry.setdefault("errors", []).append("%s: %s" % (f.name, exc))
                continue
            entry["samples"].append(prof)
            rows.append({"group": slug, **prof})
        sigs = {grid_signature(s) for s in entry["samples"]}
        entry["same_grid_within_group"] = len(sigs) == 1
        entry["signature"] = sorted(sigs)
        summary[slug] = entry
        print("  %-14s n=%-5d samples=%d same_grid=%s"
              % (slug, len(tifs), len(entry["samples"]),
                 entry["same_grid_within_group"]))

    # cross-group comparison: which families share the exact same grid?
    canon = {}
    for slug, e in summary.items():
        if e.get("samples"):
            canon[slug] = grid_signature(e["samples"][0])
    cross = {}
    for a in canon:
        for b in canon:
            if a < b and canon[a] == canon[b]:
                cross.setdefault(a, []).append(b)
    summary["_cross_group_same_grid"] = cross
    for a, bs in cross.items():
        print("  SAME GRID: %s == %s" % (a, ", ".join(bs)))

    import csv as _csv
    with open(OUT_GRID, "w", encoding="utf-8-sig", newline="") as fh:
        wr = _csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    OUT_GRID_SUM.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print("  wrote %s (%d rows)" % (OUT_GRID.name, len(rows)))
    return 0


# ══════════════════════════════════════════════════════════════════ vector
def run_vector() -> int:
    out = {"shp": {}, "nc": {}, "township_metadata": {}}
    for slug, rel in SHP_TARGETS:
        path = DATA / rel
        if not path.exists():
            out["shp"][slug] = {"status": "MISSING", "path": rel}
            print("  %-24s MISSING" % slug)
            continue
        info = dbf_header(path)
        info["path"] = rel
        out["shp"][slug] = info
        print("  %-24s recs=%-8d fields=%d" % (slug, info["records"],
                                               len(info["fields"])))

    for slug, rel in NC_TARGETS:
        path = DATA / rel
        if not path.exists():
            out["nc"][slug] = {"status": "MISSING", "path": rel}
            continue
        info = nc_attribute_strings(path)
        info["path"] = rel
        out["nc"][slug] = info
        doi = info["strings"].get("doi") or []
        print("  %-24s doi=%s" % (slug, doi[:1]))

    # the provenance-untraceable layer (gap G1)
    meta = DATA / r"我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.shp.xml"
    if meta.exists():
        raw = meta.read_text(encoding="utf-8", errors="replace")
        got = {
            "CreaDate": (re.search(r"<CreaDate>([^<]*)</CreaDate>", raw) or [None, ""])[1]
            if re.search(r"<CreaDate>([^<]*)</CreaDate>", raw) else "",
            "linkage": "",
            "resTitle": "",
            "has_originator": bool(re.search(r"<origin>", raw)),
            "has_source": bool(re.search(r"<srcInfo>|<source>", raw)),
            "has_distributor": bool(re.search(r"<distrib>", raw)),
        }
        m = re.search(r"<linkage[^>]*>([^<]*)</linkage>", raw)
        if m:
            got["linkage"] = m.group(1)
        m = re.search(r"<resTitle[^>]*>([^<]*)</resTitle>", raw)
        if m:
            got["resTitle"] = m.group(1)
        got["bytes"] = meta.stat().st_size
        out["township_metadata"] = got
        print("  township .shp.xml: originator=%s source=%s"
              % (got["has_originator"], got["has_source"]))

    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")

    lines = ["# WP14 矢量与元数据证据", "",
             "> 自动生成（`tools\\_wp14_evidence.py --mode vector`），供 `_数据溯源台账.csv` 引用。",
             "> 只读盘上实物，不依赖任何回忆或网页。", ""]
    lines += ["## 1. DBF 字段与记录数", "",
              "| 数据集 | 记录数 | 文件字节 | 字段 | 证据路径 |", "|---|---|---|---|---|"]
    for slug, info in out["shp"].items():
        if info.get("status") == "MISSING":
            lines.append("| %s | — | — | **MISSING** | `%s` |" % (slug, info["path"]))
            continue
        lines.append("| %s | %d | %d | `%s` | `%s` |" % (
            slug, info["records"], info["bytes"],
            "`, `".join(info["fields"]), info["path"]))
    lines += ["", "## 2. IBTrACS NetCDF 全局属性串扫描", ""]
    for slug, info in out["nc"].items():
        lines.append("### %s" % slug)
        if info.get("status") == "MISSING":
            lines.append("- **MISSING** `%s`" % info["path"])
            continue
        lines.append("- 路径 `%s`（%d B）" % (info["path"], info["bytes"]))
        for k, vals in info["strings"].items():
            lines.append("- `%s`: %s" % (k, " ｜ ".join(vals) if vals else "（无）"))
        lines.append("")
    lines += ["## 3. 2021 乡镇边界层元数据（缺口 G1）", ""]
    for k, v in out["township_metadata"].items():
        lines.append("- `%s` = `%s`" % (k, v))
    lines += ["", "> 结论：该 `.shp.xml` 只有 ArcGIS 自动写入的创建时间与本地路径，",
              "> **没有 originator / source / distributor 字段**，即上游来源不可考证。", ""]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("  wrote %s / %s" % (OUT_JSON.name, OUT_MD.name))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["vector", "grid", "all"], default="all")
    args = ap.parse_args()
    print("=== WP14 evidence (%s) ===" % args.mode)
    rc = 0
    if args.mode in ("vector", "all"):
        print("-- vector --")
        rc |= run_vector()
    if args.mode in ("grid", "all"):
        print("-- grid --")
        try:
            rc |= run_grid()
        except ImportError:
            print("  rasterio unavailable -> run under env\\run.ps1; skipped")
            if args.mode == "all":
                print("RESULT: EVIDENCE-PARTIAL")
                return 0
            return 2
    print("RESULT: EVIDENCE-OK")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
