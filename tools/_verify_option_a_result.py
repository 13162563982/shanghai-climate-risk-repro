"""Verify the RESULT of option A (coastline decoupled onto the fine layer).

Run through the packaged entry point::

    env\\run.ps1 tools\\_verify_option_a_result.py

Option A pins config.COASTLINE_BOUNDARY_SHP = ADMIN_BOUNDARY_LEGACY_SHP so that
the storm-surge shoreline (``climate_functions.compute_east_sea_coast_distance``)
is derived from the fine township layer, while district assignment, area/density
and the basemap keep the official GS(2024)0650 layer.

This script re-derives the shoreline from BOTH layers exactly as the pipeline
does, and compares the three runs on disk:

    legacy   output_archive/baseline_legacy_<ts>          (fine layer everywhere)
    preA     output_archive/boundary_official_<ts>        (official layer, artefact)
    A        Climate/output                               (option A, current)

Acceptance criteria (breakpoint record sections 5.3 and 6.2):
    * shoreline from COASTLINE_BOUNDARY_SHP is back to ~347.9 km
    * building_coast_distance_m.npy in the current run is byte-identical to the
      legacy baseline (surge channel is a no-op)
    * city surge EAL (historical, baseline_nodef) is back to ~6.2471 bn
    * the residual city compound-EAL offset is ~0.2% (attribution only)

Writes docs\\_岸线解耦A验证报告.md. Otherwise read-only.
"""

import hashlib
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")   # keep stderr clean: PowerShell 5.1 aborts a
                                    # pipeline at the first native stderr line

import numpy as np          # noqa: E402
import pandas as pd         # noqa: E402
import geopandas as gpd     # noqa: E402
import rasterio             # noqa: E402
from rasterio.features import shapes   # noqa: E402
from scipy import ndimage   # noqa: E402
from shapely.geometry import shape as shp_shape   # noqa: E402

NEWROOT = Path(__file__).resolve().parent.parent
CLIMATE = NEWROOT / "Climate"
ARCH = NEWROOT / "output_archive"
DATA = NEWROOT / "data"
ADMIN_DIR = DATA / "我国乡镇（街道）行政区划数据"
METRIC = "EPSG:32651"
EAL_REL = "results/defense_sensitivity/defense_profile_eal.csv"

sys.path.insert(0, str(CLIMATE))
import importlib.util  # noqa: E402

_cfg_spec = importlib.util.spec_from_file_location("_cfg_oav", CLIMATE / "00_config.py")
cfg = importlib.util.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(cfg)

LINES = []
CHECKS = []


def say(s=""):
    print(s)
    LINES.append(s)


def check(item, ok, detail=""):
    CHECKS.append((item, bool(ok), detail))
    say(f"  [{'PASS' if ok else 'FAIL'}] {item}" + (f"   {detail}" if detail else ""))


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest().upper()


# --------------------------------------------------------------------------
# shoreline re-derivation (mirrors climate_functions:459-493 exactly)
# --------------------------------------------------------------------------
def land_polygon(shp: Path):
    g = gpd.read_file(shp)
    if "市" in g.columns:
        sh = g[g["市"] == "上海市"].copy()
        if len(sh):
            g = sh
    g["ds"] = g["县"].replace(cfg.ADMIN_DISTRICT_RENAME) if "县" in g.columns else None
    return g.dissolve().geometry.iloc[0], g.crs


def shoreline_length_km(shp: Path, dem_path: Path) -> float:
    land, land_crs = land_polygon(shp)
    land_gs = gpd.GeoSeries([land], crs=land_crs)
    with rasterio.open(str(dem_path)) as src:
        dem = src.read(1).astype(np.float64)
        dem_t, dem_crs = src.transform, src.crs
    if land_gs.crs != dem_crs:
        land_gs = land_gs.to_crs(dem_crs)
    water = np.isfinite(dem) & (dem <= 0.0)
    boundary = np.zeros_like(water)
    boundary[0, :] = water[0, :]
    boundary[-1, :] = water[-1, :]
    boundary[:, -1] = water[:, -1]
    labels, _ = ndimage.label(water, np.ones((3, 3), dtype=int))
    ids = np.unique(labels[boundary])
    ocean = np.isin(labels, ids[ids > 0])
    polys = [shp_shape(g) for g, v in shapes(ocean.astype(np.uint8), mask=ocean,
             transform=dem_t) if int(v) == 1]
    ocean_union = gpd.GeoSeries(polys, crs=dem_crs).unary_union
    tol = max(abs(dem_t.a), abs(dem_t.e)) * 0.51
    shore = land_gs.iloc[0].boundary.intersection(ocean_union.buffer(tol))
    if shore.is_empty:
        shore = land_gs.iloc[0].boundary.intersection(ocean_union)
    return gpd.GeoSeries([shore], crs=dem_crs).to_crs(METRIC).iloc[0].length / 1000.0


def find_arch(prefix: str):
    hits = sorted(ARCH.glob(prefix + "*"))
    return hits[-1] if hits else None


def city_eal(out_root: Path):
    p = out_root / EAL_REL
    if not p.exists():
        return None
    df = pd.read_csv(p)
    city = df.groupby(["scenario", "defense_profile"])[
        ["EAL_compound", "EAL_wind", "EAL_surge"]].sum()
    return city


def main() -> int:
    say("=" * 78)
    say("OPTION-A RESULT VERIFICATION  (is the surge channel back to the fine layer?)")
    say("=" * 78)
    say()
    say(f"  ADMIN_BOUNDARY_SHP        = {cfg.ADMIN_BOUNDARY_SHP}")
    say(f"  COASTLINE_BOUNDARY_SHP    = {cfg.COASTLINE_BOUNDARY_SHP}")
    say(f"  effective for shoreline   = "
        f"{'ADMIN (official)' if str(cfg.COASTLINE_BOUNDARY_SHP) == str(cfg.ADMIN_BOUNDARY_SHP) else 'COASTLINE (fine)'}")
    say()

    dem = CLIMATE / "output" / "intermediate" / "dem_shanghai.tif"
    say("-- 1. shoreline length re-derived from each layer (same DEM, same code) --")
    len_fine = shoreline_length_km(Path(cfg.COASTLINE_BOUNDARY_SHP), dem)
    len_official = shoreline_length_km(Path(cfg.ADMIN_BOUNDARY_SHP), dem)
    say(f"  fine layer     ({Path(cfg.COASTLINE_BOUNDARY_SHP).name}) : {len_fine:8.1f} km")
    say(f"  official layer ({Path(cfg.ADMIN_BOUNDARY_SHP).name}) : {len_official:8.1f} km")
    say(f"  ratio official/fine : {100.0 * len_official / len_fine:6.1f}%")
    check("shoreline actually used by the pipeline is the fine one (~347.9 km)",
          340.0 <= len_fine <= 356.0, f"{len_fine:.1f} km")
    check("official layer alone would only give ~96 km (the artefact)",
          90.0 <= len_official <= 102.0, f"{len_official:.1f} km")

    say()
    say("-- 2. surge-channel inputs across the three runs (byte identity) --")
    runs = {"legacy": find_arch("baseline_legacy_"), "preA": None, "A": None}
    preA_cands = [p for p in sorted(ARCH.glob("boundary_official_*"))
                  if not p.name.startswith("boundary_official_A_")]
    runs["preA"] = preA_cands[-1] if preA_cands else None

    files = ["building_coast_distance_m.npy", "twl_vec_hist.npy", "twl_vec_synth.npy"]
    shas = {}
    for tag, root in runs.items():
        outs = (CLIMATE / "output") if root is None else (root / "Climate" / "output")
        for f in files:
            hits = list(outs.rglob(f))
            if hits:
                shas[(tag, f)] = (sha(hits[0]), hits[0])
    for f in files:
        row = []
        for tag in ("legacy", "preA", "A"):
            v = shas.get((tag, f))
            row.append(f"{tag}={v[0][:12] if v else 'MISSING'}")
        say(f"  {f:<32} " + "  ".join(row))
    check("building_coast_distance_m.npy: A == legacy (surge channel is a no-op)",
          shas.get(("A", files[0]), ("",))[0] == shas.get(("legacy", files[0]), ("",))[0])
    check("building_coast_distance_m.npy: A != preA (the fix actually changed it)",
          shas.get(("A", files[0]), ("",))[0] != shas.get(("preA", files[0]), ("",))[0])
    for f in files[1:]:
        check(f"{f}: identical in all three runs",
              len({shas.get((t, f), ("",))[0] for t in ("legacy", "preA", "A")}) == 1)

    say()
    say("-- 3. city EAL: legacy vs preA vs A (bn CNY) --")
    eal = {"legacy": city_eal(runs["legacy"] / "Climate" / "output") if runs["legacy"] else None,
           "preA": city_eal(runs["preA"] / "Climate" / "output") if runs["preA"] else None,
           "A": city_eal(CLIMATE / "output")}
    say(f"  {'scenario':<12}{'profile':<16}{'legacy':>10}{'preA':>10}{'A':>10}"
        f"{'preA vs leg':>13}{'A vs leg':>11}")
    for sc in ("historical", "SSP2-4.5", "SSP5-8.5"):
        for dp in ("baseline_nodef", "current_def_gap"):
            vals = {}
            for tag in ("legacy", "preA", "A"):
                c = eal[tag]
                try:
                    vals[tag] = float(c.loc[(sc, dp), "EAL_compound"]) / 1e9
                except Exception:  # noqa: BLE001
                    vals[tag] = float("nan")
            r1 = 100 * (vals["preA"] - vals["legacy"]) / vals["legacy"]
            r2 = 100 * (vals["A"] - vals["legacy"]) / vals["legacy"]
            say(f"  {sc:<12}{dp:<16}{vals['legacy']:>10.4f}{vals['preA']:>10.4f}"
                f"{vals['A']:>10.4f}{r1:>12.2f}%{r2:>10.2f}%")

    say()
    say("-- 4. city SURGE EAL, historical / baseline_nodef --")
    sg = {}
    for tag in ("legacy", "preA", "A"):
        c = eal[tag]
        sg[tag] = float(c.loc[("historical", "baseline_nodef"), "EAL_surge"]) / 1e9
    say(f"  legacy={sg['legacy']:.4f}   preA={sg['preA']:.4f} "
        f"({100*(sg['preA']-sg['legacy'])/sg['legacy']:+.2f}%)   "
        f"A={sg['A']:.4f} ({100*(sg['A']-sg['legacy'])/sg['legacy']:+.2f}%)")
    check("city surge EAL is back to the legacy value (within 0.5%)",
          abs(sg["A"] - sg["legacy"]) / sg["legacy"] < 0.005,
          f"{sg['A']:.4f} vs {sg['legacy']:.4f} bn")
    check("the preA surge artefact is gone",
          abs(sg["preA"] - sg["legacy"]) / sg["legacy"] > 0.05,
          f"{100*(sg['preA']-sg['legacy'])/sg['legacy']:+.2f}% was the artefact")

    say()
    say("-- 5. residual city compound-EAL offset (attribution only) --")
    worst = 0.0
    for sc in ("historical", "SSP2-4.5", "SSP5-8.5"):
        for dp in ("baseline_nodef", "current_def_gap"):
            a = float(eal["A"].loc[(sc, dp), "EAL_compound"])
            b = float(eal["legacy"].loc[(sc, dp), "EAL_compound"])
            worst = max(worst, abs(100 * (a - b) / b))
    say(f"  max |A - legacy| over the 6 scenario x profile cells = {worst:.4f}%")
    check("residual offset is attribution-scale (< 0.5%)", worst < 0.5, f"{worst:.4f}%")

    say()
    say("=" * 78)
    nfail = sum(1 for _, ok, _ in CHECKS if not ok)
    say(f"OPTION-A RESULT VERIFICATION = {'PASS' if nfail == 0 else 'FAIL'}"
        f"   ({len(CHECKS) - nfail}/{len(CHECKS)} checks)")
    for item, ok, detail in CHECKS:
        if not ok:
            say(f"  - {item} {detail}")
    say("=" * 78)

    out = NEWROOT / "docs" / "_岸线解耦A验证报告.md"
    out.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print(f"\nreport -> {out}")
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
