"""Verify WHY the official boundary layer cut surge EAL by ~13%.

Causal chain (from the source):
    ADMIN_BOUNDARY_SHP
      -> dissolve(16 districts) = land polygon            climate_functions.py:460-464
      -> shoreline = land.boundary INTERSECT ocean_mask   climate_functions.py:474-490
      -> building_coast_distance_m.npy                    climate_functions.py:492-498
      -> inundation depth = min(TWL-elev, TWL-crest) * exp(-3*cdist/reach)
                                                          climate_functions.py:357-362
      -> surge EAL

So the ONLY boundary-dependent inputs to surge damage are the shoreline (hence the
coast-distance field) and the per-building district assignment (exposure/value).

This script measures, independently of the pipeline:
  V1  geometry of the two admin layers (area, Jaccard, symmetric difference)
  V2  the two derived shorelines (length + how far one moved relative to the other)
  V3  the two coast-distance fields (as saved by each run, and recomputed here)
  V4  hybrid-zone assignment counts
  V5  the depth/EAL consequence + per-district attribution
  V6  invariants that must NOT have changed (TWL, elevation)

Writes docs\\_潮损偏移复核报告.md. Read-only.
"""

import hashlib
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")   # keep stderr clean: PowerShell kills the
                                    # pipeline at the first native stderr line

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import shape as shp_shape

NEWROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NEWROOT / "Climate"))

import rasterio  # noqa: E402
from rasterio.features import shapes  # noqa: E402
from scipy import ndimage  # noqa: E402

CLIMATE = NEWROOT / "Climate"
DATA = NEWROOT / "data"
ADMIN_DIR = DATA / "我国乡镇（街道）行政区划数据"
LEGACY_SHP = ADMIN_DIR / "2021年我国乡镇（街道）边界数据.shp"
OFFICIAL_SHP = ADMIN_DIR / "_官方_天地图GS2024-0650" / "上海_区级_GS2024-0650.shp"
DEM = CLIMATE / "output" / "intermediate" / "dem_shanghai.tif"
METRIC = "EPSG:32651"

# the layer the pipeline ACTUALLY uses for the shoreline (option A decouples it)
import importlib.util  # noqa: E402

_cs = importlib.util.spec_from_file_location("_cfg_vso", CLIMATE / "00_config.py")
_cfg = importlib.util.module_from_spec(_cs)
_cs.loader.exec_module(_cfg)
COAST_SHP = Path(getattr(_cfg, "COASTLINE_BOUNDARY_SHP", _cfg.ADMIN_BOUNDARY_SHP))

ARCH = NEWROOT / "output_archive"
LEG_OUT = sorted(ARCH.glob("baseline_legacy_*"))[-1] / "Climate" / "output"
NEW_OUT = CLIMATE / "output"

ROWS = []


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def note(section, item, value, ok=None):
    ROWS.append({"section": section, "item": item, "value": value, "ok": ok})
    print(f"  {item:<52} {value}")


def load_land(shp: Path) -> gpd.GeoSeries:
    """Reproduce climate_functions.compute_east_sea_coast_distance's land polygon."""
    g = gpd.read_file(shp)
    if "市" in g.columns:
        sh = g[g["市"] == "上海市"].copy()
        if len(sh):
            g = sh
    g = g.to_crs(METRIC)
    land = g.dissolve().geometry.iloc[0]
    return gpd.GeoSeries([land], crs=METRIC)


def build_shoreline(land_metric: gpd.GeoSeries):
    """Reproduce climate_functions.py:466-493 exactly (same DEM, same tolerance)."""
    with rasterio.open(str(DEM)) as src:
        dem = src.read(1).astype(np.float64)
        dem_t = src.transform
        dem_crs = src.crs
    land_native = land_metric.to_crs(dem_crs)
    water = np.isfinite(dem) & (dem <= 0.0)
    boundary = np.zeros_like(water)
    boundary[0, :] = water[0, :]
    boundary[-1, :] = water[-1, :]
    boundary[:, -1] = water[:, -1]
    labels, _ = ndimage.label(water, np.ones((3, 3), dtype=int))
    ocean_ids = np.unique(labels[boundary])
    ocean_ids = ocean_ids[ocean_ids > 0]
    ocean_mask = np.isin(labels, ocean_ids)
    polys = [shp_shape(g) for g, v in shapes(ocean_mask.astype(np.uint8),
             mask=ocean_mask, transform=dem_t) if int(v) == 1]
    ocean_union = gpd.GeoSeries(polys, crs=dem_crs).unary_union
    tol = max(abs(dem_t.a), abs(dem_t.e)) * 0.51
    shore = land_native.iloc[0].boundary.intersection(ocean_union.buffer(tol))
    if shore.is_empty:
        shore = land_native.iloc[0].boundary.intersection(ocean_union)
    return shore, land_native.iloc[0], ocean_union, dem_crs


def main() -> int:
    # ── guard: this report is the EVIDENCE for the pre-option-A artefact ──
    # It hard-codes "current run == official layer", which stopped being true
    # once option A decoupled the shoreline onto COASTLINE_BOUNDARY_SHP.
    # Re-running it now would both mislabel the comparison AND overwrite the
    # artefact evidence. Use tools/_verify_option_a_result.py for the A state.
    if str(COAST_SHP) != str(OFFICIAL_SHP) and "--force" not in sys.argv:
        print("REFUSING TO RUN - option A is active.")
        print(f"  ADMIN_BOUNDARY_SHP     = {OFFICIAL_SHP}")
        print(f"  COASTLINE_BOUNDARY_SHP = {COAST_SHP}")
        print("  The current run no longer derives its shoreline from the official")
        print("  layer, so this script's premise (current == official) is invalid,")
        print("  and its report is the frozen evidence for the -13% artefact.")
        print("  Preserved copy: docs/_潮损偏移复核报告_伪影证据.md")
        print("  For the option-A state run: tools/_verify_option_a_result.py")
        print("  Re-run with --force only to regenerate the pre-A report on a")
        print("  machine where COASTLINE_BOUNDARY_SHP is still the official layer.")
        return 2

    print("=" * 78)
    print("SURGE-OFFSET VERIFICATION  (why did surge EAL drop ~13%?)")
    print("=" * 78)
    print(f"legacy layer  : {LEGACY_SHP.name}")
    print(f"official layer: {OFFICIAL_SHP.name}")
    print(f"legacy run    : {LEG_OUT.parent.parent.name}")
    print(f"official run  : {NEW_OUT}")

    # ---------------- V1: layer geometry ----------------
    print("\n-- V1  admin layer geometry --")
    land_leg = load_land(LEGACY_SHP)
    land_off = load_land(OFFICIAL_SHP)
    a_leg = land_leg.iloc[0].area / 1e6
    a_off = land_off.iloc[0].area / 1e6
    note("V1", "legacy union area (km2)", f"{a_leg:,.3f}")
    note("V1", "official union area (km2)", f"{a_off:,.3f}")
    note("V1", "area delta (km2)", f"{a_off - a_leg:+,.3f} ({(a_off / a_leg - 1) * 100:+.2f}%)")
    inter = land_leg.iloc[0].intersection(land_off.iloc[0]).area
    union = land_leg.iloc[0].union(land_off.iloc[0]).area
    note("V1", "Jaccard overlap", f"{inter / union * 100:.2f}%")
    g_leg = gpd.read_file(LEGACY_SHP)
    g_off = gpd.read_file(OFFICIAL_SHP)
    note("V1", "legacy vertices, DISSOLVED (plan 2.5 convention)",
         f"{_dissolved_vertices(g_leg):,}")
    note("V1", "official vertices, DISSOLVED (plan 2.5 convention)",
         f"{_dissolved_vertices(g_off):,}")

    # ---------------- V2: derived shorelines ----------------
    print("\n-- V2  derived shoreline (the actual driver) --")
    shore_leg, land_leg_native, ocean, dem_crs = build_shoreline(land_leg)
    shore_off, _, _, _ = build_shoreline(land_off)
    l_leg = gpd.GeoSeries([shore_leg], crs=dem_crs).to_crs(METRIC).iloc[0].length / 1e3
    l_off = gpd.GeoSeries([shore_off], crs=dem_crs).to_crs(METRIC).iloc[0].length / 1e3
    note("V2", "legacy shoreline length (km)", f"{l_leg:,.1f}")
    note("V2", "official shoreline length (km)", f"{l_off:,.1f}")

    # how far did the shoreline move? sample points evenly along each and measure
    s_leg_m = gpd.GeoSeries([shore_leg], crs=dem_crs).to_crs(METRIC).iloc[0]
    s_off_m = gpd.GeoSeries([shore_off], crs=dem_crs).to_crs(METRIC).iloc[0]
    pts_leg = _sample(s_leg_m, 1500)
    pts_off = _sample(s_off_m, 1500)
    d_leg2off = np.array([s_off_m.distance(p) for p in pts_leg])
    d_off2leg = np.array([s_leg_m.distance(p) for p in pts_off])
    note("V2", "legacy->official P50 / P90 / max (m)",
         f"{np.median(d_leg2off):,.0f} / {np.percentile(d_leg2off, 90):,.0f} / {d_leg2off.max():,.0f}")
    note("V2", "official->legacy P50 / P90 / max (m)",
         f"{np.median(d_off2leg):,.0f} / {np.percentile(d_off2leg, 90):,.0f} / {d_off2leg.max():,.0f}")
    note("V2", "two-sided Hausdorff (m)", f"{max(d_leg2off.max(), d_off2leg.max()):,.0f}")

    # V2b: which districts lost their coastline under the coarse layer?
    print("\n-- V2b  per-district centroid -> derived shoreline (km) --")
    dl = _district_centroid_dist(g_leg, shore_leg, dem_crs)
    do = _district_centroid_dist(g_off, shore_off, dem_crs)
    for d in sorted(set(dl.index) | set(do.index)):
        v1 = float(dl.get(d, np.nan))
        v2 = float(do.get(d, np.nan))
        note("V2b", f"{d} centroid->shoreline (km)", f"{v1:6.1f} -> {v2:6.1f}  ({v2 - v1:+.1f})")

    # ---------------- V3: coast-distance fields ----------------
    print("\n-- V3  building coast-distance field --")
    cd_leg = np.load(LEG_OUT / "intermediate" / "building_coast_distance_m.npy")
    cd_new = np.load(NEW_OUT / "intermediate" / "building_coast_distance_m.npy")
    note("V3", "n buildings (legacy / official)", f"{cd_leg.size:,} / {cd_new.size:,}",
         cd_leg.size == cd_new.size)
    for tag, arr in (("legacy", cd_leg), ("official", cd_new)):
        note("V3", f"{tag} mean / median / P90 (km)",
             f"{arr.mean() / 1e3:,.2f} / {np.median(arr) / 1e3:,.2f} / {np.percentile(arr, 90) / 1e3:,.2f}")
    d = cd_new.astype(np.float64) - cd_leg.astype(np.float64)
    note("V3", "delta mean / median (m)", f"{d.mean():+,.0f} / {np.median(d):+,.0f}")
    note("V3", "buildings moved FURTHER from coast", f"{(d > 1).sum():,} ({(d > 1).mean() * 100:.1f}%)")
    note("V3", "buildings moved CLOSER", f"{(d < -1).sum():,} ({(d < -1).mean() * 100:.1f}%)")
    note("V3", "correlation(legacy, official)", f"{np.corrcoef(cd_leg, cd_new)[0, 1]:.4f}")

    # ---------------- V4: hybrid zone assignment ----------------
    print("\n-- V4  hybrid surge zone assignment --")
    try:
        from climate_functions import assign_surge_hybrid_zones
        import importlib.util
        spec = importlib.util.spec_from_file_location("cfg", CLIMATE / "00_config.py")
        cfg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cfg)
        hp = np.load(LEG_OUT / "intermediate" / "building_huangpu_overbank_template_m.npy")
        for tag, arr in (("legacy", cd_leg), ("official", cd_new)):
            z = assign_surge_hybrid_zones(arr, river_template=hp, config=cfg)
            vals, cnt = np.unique(np.asarray(z), return_counts=True)
            note("V4", f"{tag} zones", ", ".join(f"{v}={c:,}" for v, c in zip(vals, cnt)))
    except Exception as exc:  # noqa: BLE001
        note("V4", "zone assignment", f"SKIPPED ({type(exc).__name__}: {exc})", False)

    # ---------------- V5: depth consequence ----------------
    print("\n-- V5  inundation depth consequence (baseline_nodef) --")
    elev = np.load(LEG_OUT / "intermediate" / "building_elevation.npy")
    twl = np.load(LEG_OUT / "intermediate" / "twl_vec_hist.npy")
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("cfg2", CLIMATE / "00_config.py")
    cfg = _ilu.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    from climate_functions import compute_coastal_inundation_depth
    hp_leg = np.load(LEG_OUT / "intermediate" / "building_huangpu_overbank_template_m.npy")
    hp_new = np.load(NEW_OUT / "intermediate" / "building_huangpu_overbank_template_m.npy")
    prof = {"coastal_defense_enabled": False, "coastal_defense_crest_m": 0.0}
    for tag, cdist, hpt in (("legacy", cd_leg, hp_leg), ("official", cd_new, hp_new)):
        h = compute_coastal_inundation_depth(twl, elev, cdist, cfg,
                                             river_template=hpt, defense_profile=prof)
        note("V5", f"{tag} mean depth over all (events x bldg)", f"{h.mean():.4f} m")
        note("V5", f"{tag} fraction of pairs with depth>0", f"{(h > 0).mean() * 100:.3f}%")

    # ---------------- V6: invariants ----------------
    print("\n-- V6  invariants that must NOT have changed --")
    for name in ("twl_vec_hist.npy", "twl_vec_synth.npy", "building_elevation.npy",
                 "dem_shanghai.tif"):
        p1 = LEG_OUT / "intermediate" / name
        p2 = NEW_OUT / "intermediate" / name
        if p1.exists() and p2.exists():
            same = sha(p1) == sha(p2)
            note("V6", f"{name} identical", "YES" if same else "NO", same)
        else:
            note("V6", f"{name} present", "missing", False)

    # ---------------- attribution ----------------
    print("\n-- attribution: per-district surge delta vs coast-distance delta --")
    eal_leg = pd.read_csv(LEG_OUT / "results" / "defense_sensitivity" / "defense_profile_eal.csv")
    eal_new = pd.read_csv(NEW_OUT / "results" / "defense_sensitivity" / "defense_profile_eal.csv")
    sel = lambda df: df[(df["scenario"] == "historical") & (df["defense_profile"] == "baseline_nodef")]
    a = sel(eal_leg).set_index("district")
    b = sel(eal_new).set_index("district")
    tbl = pd.DataFrame({
        "EAL_surge_legacy": a["EAL_surge"], "EAL_surge_official": b["EAL_surge"],
    })
    tbl["surge_rel%"] = (tbl["EAL_surge_official"] / tbl["EAL_surge_legacy"] - 1) * 100
    tbl["wind_rel%"] = (b["EAL_wind"] / a["EAL_wind"] - 1) * 100
    print(tbl.round(2).to_string())
    tot_l = a["EAL_surge"].sum()
    tot_n = b["EAL_surge"].sum()
    note("ATTR", "city surge EAL legacy (bn)", f"{tot_l / 1e9:,.4f}")
    note("ATTR", "city surge EAL official (bn)", f"{tot_n / 1e9:,.4f}")
    note("ATTR", "city surge delta", f"{(tot_n / tot_l - 1) * 100:+.2f}%")
    note("ATTR", "city wind delta",
         f"{(b['EAL_wind'].sum() / a['EAL_wind'].sum() - 1) * 100:+.2f}%")

    # report
    lines = ["# 潮损偏移复核报告（官方层 vs 旧乡镇层）", "",
             "> 目的：确认城市潮损 EAL −13% 是**官方边界层的几何必然**，而非代码/输入错误。",
             "> 生成脚本：`tools/_verify_surge_offset.py`（只读，不修改任何产物）", "",
             "## 因果链", "",
             "```",
             "ADMIN_BOUNDARY_SHP → dissolve(16 区) = 陆地多边形",
             "  → 岸线 = 陆地边界 ∩ DEM 海洋掩膜        (climate_functions.py:460-490)",
             "  → building_coast_distance_m.npy        (climate_functions.py:492-498)",
             "  → 淹没深度 = min(TWL−elev, TWL−crest)·exp(−3·cdist/reach)",
             "  → 潮损 EAL",
             "```", "",
             "边界层只通过**两个**入口影响潮损：① 岸线（进而岸距场）② 建筑→区县归属。", "",
             "| 段 | 项 | 值 |", "|---|---|---|"]
    for r in ROWS:
        lines.append(f"| {r['section']} | {r['item']} | {r['value']} |")
    lines += ["", "## 区级归因", "", "```", tbl.round(3).to_string(), "```", ""]
    (NEWROOT / "docs" / "_潮损偏移复核报告.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nreport -> {NEWROOT / 'docs' / '_潮损偏移复核报告.md'}")

    verdict = all(r["ok"] for r in ROWS if r["ok"] is not None)
    print("=" * 78)
    print(f"INVARIANTS OK = {verdict}")
    print("=" * 78)
    return 0


def _iter_polys(gdf):
    for geom in gdf.geometry:
        if geom is None:
            continue
        if geom.geom_type == "Polygon":
            yield geom
        elif geom.geom_type == "MultiPolygon":
            yield from geom.geoms


def _shanghai(gdf):
    if "市" in gdf.columns:
        sub = gdf[gdf["市"] == "上海市"]
        if len(sub):
            return sub
    return gdf


def _dissolved_vertices(gdf) -> int:
    """Vertex count of the DISSOLVED (unioned) layer -- plan section 2.5 convention."""
    g = _shanghai(gdf).to_crs(METRIC)
    geom = g.dissolve().geometry.iloc[0]
    return sum(len(p.exterior.coords) for p in _iter_polys(gpd.GeoDataFrame(geometry=[geom])))


def _district_centroid_dist(gdf, shore, shore_crs) -> pd.Series:
    g = _shanghai(gdf).copy()
    namecol = "县" if "县" in g.columns else g.columns[0]
    g["ds"] = g[namecol].replace({"崇明县": "崇明区", "闸北区": "静安区"})
    g = g.dissolve(by="ds").to_crs(METRIC)
    s = gpd.GeoSeries([shore], crs=shore_crs).to_crs(METRIC).iloc[0]
    return g.centroid.distance(s) / 1e3


def _sample(line, n):
    return [line.interpolate(i / n, normalized=True) for i in range(n + 1)]


if __name__ == "__main__":
    sys.exit(main())
