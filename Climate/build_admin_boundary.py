"""
build_admin_boundary.py
=======================
Build the official Shanghai 16-district boundary layer from the TianDiTu
(National Platform for Common Geospatial Information Services) 2024-05
provincial-municipal-county administrative division dataset,
map review number GS(2024)0650.

Source package (as redistributed by 立方数据学社, keyword 289):
    data/我国乡镇（街道）行政区划数据/
        202405更新_2024年省市县三级行政区划数据（审图号：GS（2024）0650号）/
            202405更新_2024年省市县三级行政区划数据（审图号：GS（2024）0650号）/
                shp格式的数据（调整过行政区划代码，补全省市县信息）/县.shp

Output contract
---------------
Downstream code (Climate/03_exposure.py:199-202, Climate/04_vulnerability.py:102-105,
Climate/climate_functions.py:460-463, Climate/visualization/maps.py:37-39) expects
a layer it can filter with

    admin_gdf[admin_gdf["市"] == "上海市"]

and then dissolve with

    .dissolve(by="县")

therefore this script RENAMES the source columns:

    省名 -> 省      市名 -> 市      县名 -> 县
    县代码 -> adcode  市代码 -> adcode_city  省代码 -> adcode_prov

The source layer is already at county level (one row per district), so the
downstream `dissolve(by="县")` becomes a harmless no-op.

This script is idempotent: re-running produces a byte-identical shapefile for
the same source file.

Usage:
    python build_admin_boundary.py [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime
from pathlib import Path

import geopandas as gpd

V8_ROOT = Path(__file__).resolve().parent.parent
ADMIN_DIR = V8_ROOT / "data" / "我国乡镇（街道）行政区划数据"
_SRC_SUBDIR = "202405更新_2024年省市县三级行政区划数据（审图号：GS（2024）0650号）"
SRC_SHP = (
    ADMIN_DIR
    / _SRC_SUBDIR
    / _SRC_SUBDIR
    / "shp格式的数据（调整过行政区划代码，补全省市县信息）"
    / "县.shp"
)

OUT_DIR = ADMIN_DIR / "_官方_天地图GS2024-0650"
OUT_SHP = OUT_DIR / "上海_区级_GS2024-0650.shp"
OUT_SOURCE = OUT_DIR / "_SOURCE.txt"

# Shanghai bounding box (slightly padded) used to pre-filter the national layer
BBOX = (120.6, 30.5, 122.4, 32.1)
SHANGHAI_PROV_CODE_PREFIX = "31"

EXPECTED_DISTRICTS = {
    "黄浦区", "徐汇区", "长宁区", "静安区", "普陀区", "虹口区", "杨浦区", "闵行区",
    "宝山区", "嘉定区", "浦东新区", "金山区", "松江区", "青浦区", "奉贤区", "崇明区",
}

RENAME = {
    "省名": "省", "市名": "市", "县名": "县",
    "县代码": "adcode", "市代码": "adcode_city", "省代码": "adcode_prov",
}

MAP_REVIEW_NUMBER = "GS（2024）0650号"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="overwrite existing output")
    args = ap.parse_args()

    if not SRC_SHP.exists():
        print(f"ERROR: source not found: {SRC_SHP}", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    src_hash = sha256(SRC_SHP)
    print(f"SOURCE      {SRC_SHP}")
    print(f"SOURCE_SHA  {src_hash}")

    gdf = gpd.read_file(SRC_SHP, bbox=BBOX)
    print(f"READ        {len(gdf)} features in bbox  crs={gdf.crs}")

    missing = [c for c in RENAME if c not in gdf.columns]
    if missing:
        print(f"ERROR: source is missing expected columns: {missing}", file=sys.stderr)
        print(f"       actual columns: {list(gdf.columns)}", file=sys.stderr)
        return 3

    # Shanghai only, by county-level administrative code prefix
    gdf = gdf[gdf["县代码"].astype(str).str.startswith(SHANGHAI_PROV_CODE_PREFIX)].copy()
    gdf = gdf.rename(columns=RENAME)
    gdf = gdf[["省", "市", "县", "adcode", "adcode_city", "adcode_prov", "geometry"]]
    gdf = gdf.sort_values("adcode").reset_index(drop=True)
    print(f"SHANGHAI    {len(gdf)} districts")

    # ---- validation -------------------------------------------------------
    ok = True

    names = set(gdf["县"])
    if names != EXPECTED_DISTRICTS:
        ok = False
        print(f"ERROR: district name mismatch", file=sys.stderr)
        print(f"  missing: {sorted(EXPECTED_DISTRICTS - names)}", file=sys.stderr)
        print(f"  extra  : {sorted(names - EXPECTED_DISTRICTS)}", file=sys.stderr)

    bad_city = gdf[gdf["市"] != "上海市"]["县"].tolist()
    if bad_city:
        ok = False
        print(f"ERROR: non-Shanghai rows after filter: {bad_city}", file=sys.stderr)

    if not bool(gdf.geometry.is_valid.all()):
        ok = False
        print("ERROR: invalid geometries present", file=sys.stderr)

    if not ok:
        return 4

    # Topology: pairwise overlap and coverage of the union
    utm = gdf.to_crs("EPSG:32651")
    union = utm.geometry.union_all()
    sum_area = float(utm.geometry.area.sum())
    union_area = float(union.area)
    overlap = sum_area - union_area
    overlap_pct = 100.0 * overlap / sum_area if sum_area else 0.0

    print(f"AREA_SUM_KM2    {sum_area / 1e6:.3f}")
    print(f"AREA_UNION_KM2  {union_area / 1e6:.3f}")
    print(f"PAIRWISE_OVERLAP_KM2  {overlap / 1e6:.6f}  ({overlap_pct:.6f}% of sum)")
    if overlap_pct > 0.01:
        ok = False
        print(f"ERROR: district polygons overlap by {overlap_pct:.4f}% (>0.01%)", file=sys.stderr)
    if not ok:
        return 5

    # ---- write ------------------------------------------------------------
    if OUT_SHP.exists() and not args.force:
        print(f"NOTE: output exists; overwriting ({OUT_SHP.name})")

    gdf.to_file(OUT_SHP, driver="ESRI Shapefile", encoding="utf-8")
    out_hash = sha256(OUT_SHP)

    table = gdf.drop(columns="geometry").to_string(index=False)
    print("\n--- DISTRICTS ---")
    print(table)

    OUT_SOURCE.write_text(
        "\n".join([
            "Shanghai district boundary layer — provenance",
            "=" * 60,
            "",
            "Title        : 2024年省、市、县三级行政区划数据（2024年5月更新版）",
            "Provider     : 国家基础地理信息中心 / 国家地理信息公共服务平台（天地图）",
            f"Map review no: {MAP_REVIEW_NUMBER}",
            "Source page  : https://cloudcenter.tianditu.gov.cn/administrativeDivision",
            "Format       : Shapefile, EPSG:4326 (source GeoJSON was CGCS2000/EPSG:4490-consistent WGS84)",
            "",
            "Obtained via : 立方数据学社（公众号关键词 289）发布的加工版",
            "               'shp格式的数据（调整过行政区划代码，补全省市县信息）'",
            "               The redistributor converted the official GeoJSON to Shapefile,",
            "               appended parent province/city names, and replaced the",
            "               non-standard source codes with standard GB/T 2260 codes.",
            "",
            f"Local source : {SRC_SHP}",
            f"Source SHA256: {src_hash}",
            f"Output       : {OUT_SHP}",
            f"Output SHA256: {out_hash}",
            f"Generated    : {datetime.now().isoformat(timespec='seconds')}",
            "",
            "Processing performed by build_admin_boundary.py:",
            "  1. read national county layer with bbox (120.6, 30.5, 122.4, 32.1)",
            "  2. keep rows whose 县代码 starts with '31' (Shanghai) -> 16 districts",
            "  3. rename 省名/市名/县名 -> 省/市/县; 县代码 -> adcode, etc.",
            "       (schema compatibility with Climate/00_config.py ADMIN_BOUNDARY_SHP)",
            "  4. validate: 16 expected district names, geometries valid,",
            "       pairwise overlap <= 0.01%",
            "  5. write Shapefile",
            "",
            "NOTE: the source layer is already at county level, so downstream",
            "      dissolve(by='县') is a no-op. ADMIN_DISTRICT_RENAME no longer",
            "      matches anything on this layer (no 闸北区 / 崇明县 present).",
            "",
            "CAVEAT: this is the official *cartographic* boundary product. It is",
            "        generalised for map display (780 vertices for all 16 districts",
            "        vs 17,869 in the previously used township-derived layer).",
            "        See _边界几何裁决报告.md for the measured impact.",
            "",
        ]),
        encoding="utf-8",
    )
    print(f"\nWROTE  {OUT_SHP}")
    print(f"WROTE  {OUT_SOURCE}")
    print(f"OUTPUT_SHA  {out_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
