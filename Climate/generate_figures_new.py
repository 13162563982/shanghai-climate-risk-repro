"""
Generate all publication and manuscript-support figures into output/figures_new/.

Structure:
  01_basic_facts/      10 figures — TC stats, exposure, vulnerability, built-up, price, population, building types
  02_impact_func/       2 figures — TC and SS impact-function curves
  historical/
      01_TC/            3 figures — TC tracks, damage hexbin, damage by district
      02_SS/            4 figures — SS depth/occurrence/damage hexbin, damage by district
      03_compound/      1 figure  — TC×SS compound damage decomposition
  synthetic/
      01_TC/            3 figures — synthetic tracks, SSP damage hexbin/bar
      02_SS/            4 figures — SSP SS depth/occurrence/damage hexbin/bar
      03_compound/      1 figure  — SSP compound damage decomposition
  climate_index/        1 figure  — Climate risk index time series
    04_defense/           1 figure  — defense-sensitivity evidence figure

Usage:
    cd Climate
    conda activate climada_env
    python generate_figures_new.py              # full figure suite
    python generate_figures_new.py --only basic_facts
    python generate_figures_new.py --only impact_func
    python generate_figures_new.py --only historical
    python generate_figures_new.py --only synthetic
    python generate_figures_new.py --only climate_index
    python generate_figures_new.py --only defense
"""
from __future__ import annotations

import argparse
import pickle
import re
import sys
import types
from pathlib import Path

# Mock osgeo before any CLIMADA import to avoid hard GDAL dependency
for _mod in ("osgeo", "osgeo.gdal", "osgeo.osr"):
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

import cartopy.crs as ccrs
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from climada.hazard import TCTracks
from matplotlib.collections import LineCollection
from matplotlib.colors import BoundaryNorm, LogNorm, PowerNorm, TwoSlopeNorm
from matplotlib.lines import Line2D

# ── Bootstrap: add Climate/ to path, load config ──
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import importlib
config = importlib.import_module("00_config")
config.init_environment()

from visualization.maps import (
    add_east_china_sea_label,
    add_gov_markers,
    add_map_legend,
    add_water_labels,
    aggregate_points_to_masked_grid,
    annotate_district_labels,
    filter_points_to_shanghai,
    load_district_boundaries,
    style_map_axis,
)
from visualization.style import (
    BASE_RC_PARAMS,
    BUILDING_CATEGORY_LABELS,
    DISTRICT_EN_LOOKUP,
    DISTRICT_LABEL_SPECS,
    PRIMARY_BUILDING_CATEGORIES,
)

plt.rcParams.update(BASE_RC_PARAMS)

# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════
FIGURES_NEW_DIR = config.OUTPUT_DIR / "figures_new"

SCENARIO_ORDER = ["SSP2-4.5", "SSP5-8.5"]
SCENARIO_LABELS = {
    "historical": "Historical",
    "SSP2-4.5": "SSP2-4.5",
    "SSP5-8.5": "SSP5-8.5",
}
SCENARIO_COLORS = {
    "historical": "#1d3557",
    "SSP2-4.5": "#2a9d8f",
    "SSP5-8.5": "#e76f51",
}

SAFFIR_SIMPSON_THRESHOLDS_KT = [34.0, 64.0, 83.0, 96.0, 113.0, 137.0]
SAFFIR_SIMPSON_COLORS = {
    -1: "#6baed6", 0: "#74c476", 1: "#fdd835", 2: "#fb8c00",
    3: "#e53935", 4: "#ad1457", 5: "#6a1b9a",
}
SAFFIR_SIMPSON_LABELS = {
    -1: "TD", 0: "TS", 1: "Cat 1", 2: "Cat 2",
    3: "Cat 3", 4: "Cat 4", 5: "Cat 5",
}

BUILDING_CATEGORY_COLORS = {
    "A_old": "#7f5539", "A_new": "#ddb892", "B_old": "#386641",
    "B_new": "#6a994e", "C": "#3d5a80", "D": "#bc4749",
}

WEST_PACIFIC_BBOX = (110.0, 5.0, 160.0, 45.0)
DEFENSE_PROFILE = "baseline_nodef"
HEXBIN_GRIDSIZE = 82
HEXBIN_EXTENT = (
    config.SHANGHAI_BBOX[0],
    config.SHANGHAI_BBOX[2],
    config.SHANGHAI_BBOX[1],
    config.SHANGHAI_BBOX[3],
)


# ═══════════════════════════════════════════════════════════════════════
# Utility helpers
# ═══════════════════════════════════════════════════════════════════════

def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_fig(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", dpi=300)
    plt.close(fig)
    print(f"  [OK] {path.relative_to(FIGURES_NEW_DIR)}")
    return path


def _compute_hexbin_cells(x, y, c, reduce_fn, gridsize: int = HEXBIN_GRIDSIZE,
                          extent=HEXBIN_EXTENT) -> pd.DataFrame:
    if len(x) == 0:
        return pd.DataFrame(columns=["lon", "lat", "value"])

    fig_tmp, ax_tmp = plt.subplots()
    hb_tmp = ax_tmp.hexbin(
        x,
        y,
        C=c,
        reduce_C_function=reduce_fn,
        gridsize=gridsize,
        mincnt=1,
        extent=extent,
    )
    offsets = hb_tmp.get_offsets()
    values = np.asarray(hb_tmp.get_array(), dtype=float).ravel()
    plt.close(fig_tmp)

    if offsets.size == 0 or values.size == 0:
        return pd.DataFrame(columns=["lon", "lat", "value"])

    return pd.DataFrame({
        "lon": np.round(offsets[:, 0], 10),
        "lat": np.round(offsets[:, 1], 10),
        "value": values,
    })


def _build_hex_delta(left_cells: pd.DataFrame, right_cells: pd.DataFrame) -> pd.DataFrame:
    if left_cells.empty and right_cells.empty:
        return pd.DataFrame(columns=["lon", "lat", "delta"])

    merged = (
        left_cells.rename(columns={"value": "left_value"})
        .merge(
            right_cells.rename(columns={"value": "right_value"}),
            on=["lon", "lat"],
            how="outer",
        )
        .fillna(0.0)
    )
    merged["delta"] = merged["right_value"] - merged["left_value"]
    return merged[["lon", "lat", "delta"]]


def _build_delta_norm(values: np.ndarray):
    if values.size == 0:
        return TwoSlopeNorm(vmin=-1.0, vcenter=0.0, vmax=1.0)

    vmax = max(float(np.quantile(np.abs(values), 0.995)), 1e-9)
    return TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)


# ── Track segment helpers ──

def _wind_to_category_knots(wind_speed: float) -> int:
    if not np.isfinite(wind_speed):
        return -1
    for i, threshold in enumerate(SAFFIR_SIMPSON_THRESHOLDS_KT):
        if wind_speed < threshold:
            return i - 1
    return 5


def _track_segment_categories(track):
    lon = np.asarray(track["lon"], dtype=float)
    lat = np.asarray(track["lat"], dtype=float)
    wind = np.asarray(track["max_sustained_wind"], dtype=float)
    valid = np.isfinite(lon) & np.isfinite(lat) & np.isfinite(wind)
    lon, lat, wind = lon[valid], lat[valid], wind[valid]
    if lon.size < 2:
        return lon, lat, np.array([], dtype=int)
    seg_wind = np.nanmax(np.column_stack([wind[:-1], wind[1:]]), axis=1)
    return lon, lat, np.array([_wind_to_category_knots(v) for v in seg_wind], dtype=int)


def _plot_tracks_by_category(ax, track_set, linewidth=1.0, alpha=0.7, linestyle="solid"):
    tracks = track_set.data if isinstance(track_set, TCTracks) else track_set
    by_cat: dict[int, list] = {}
    for track in tracks:
        lon, lat, cats = _track_segment_categories(track)
        if lon.size < 2:
            continue
        coords = np.column_stack([lon, lat])
        segs = np.stack([coords[:-1], coords[1:]], axis=1)
        for cat in sorted(SAFFIR_SIMPSON_COLORS):
            m = cats == cat
            if np.any(m):
                by_cat.setdefault(cat, []).extend(list(segs[m]))
    for cat, segs in sorted(by_cat.items()):
        if segs:
            ax.add_collection(LineCollection(
                segs, colors=SAFFIR_SIMPSON_COLORS.get(cat, "#999"),
                linewidths=linewidth, linestyles=linestyle, alpha=alpha,
                transform=ccrs.PlateCarree(), zorder=3,
            ))


def _plot_tracks_single_color(ax, track_set, color="#b0b0b0", linewidth=0.7, alpha=0.12):
    tracks = track_set.data if isinstance(track_set, TCTracks) else track_set
    segs = []
    for track in tracks:
        lon = np.asarray(track["lon"], dtype=float)
        lat = np.asarray(track["lat"], dtype=float)
        m = np.isfinite(lon) & np.isfinite(lat)
        lon, lat = lon[m], lat[m]
        if lon.size < 2:
            continue
        coords = np.column_stack([lon, lat])
        segs.extend(np.stack([coords[:-1], coords[1:]], axis=1))
    if segs:
        ax.add_collection(LineCollection(
            segs, colors=color, linewidths=linewidth, alpha=alpha,
            transform=ccrs.PlateCarree(), zorder=2,
        ))


def _select_top_intensity(track_set, count=18, unique_source=False):
    tracks = track_set.data if isinstance(track_set, TCTracks) else track_set
    def peak(t):
        w = np.asarray(t["max_sustained_wind"], dtype=float)
        return float(np.nanmax(w)) if w.size else -np.inf
    ranked = sorted(tracks, key=lambda t: -peak(t))
    if not unique_source:
        return TCTracks(data=ranked[:count])
    seen, sel = set(), []
    for t in ranked:
        key = re.sub(r"_gen\d+$", "", str(t.attrs.get("sid", t.attrs.get("name", ""))))
        if key in seen:
            continue
        seen.add(key); sel.append(t)
        if len(sel) >= count:
            break
    return TCTracks(data=sel)


def _add_category_legend(ax, include_synthetic=False):
    handles = [Line2D([0], [0], color="#b0b0b0", lw=0.7, alpha=0.3)]
    labels = ["Background tracks"]
    for cat in sorted(SAFFIR_SIMPSON_COLORS.keys()):
        handles.append(Line2D([0], [0], color=SAFFIR_SIMPSON_COLORS[cat], lw=1.4, alpha=0.85))
        labels.append(SAFFIR_SIMPSON_LABELS[cat])
    if include_synthetic:
        handles.append(Line2D([0], [0], color="#666", lw=1.2, linestyle=(0, (4, 3))))
        labels.append("Synthetic (dashed)")
    ax.legend(handles, labels, loc="upper left", fontsize=7.2, frameon=True,
              facecolor="white", edgecolor="#e5e7eb", framealpha=0.92)


# ═══════════════════════════════════════════════════════════════════════
# Data loading (cached)
# ═══════════════════════════════════════════════════════════════════════
_cache: dict = {}


def _load_districts():
    if "districts" not in _cache:
        _cache["districts"] = load_district_boundaries(config)
    return _cache["districts"]


def _load_buildings():
    if "buildings" not in _cache:
        bldg = pd.read_parquet(
            config.BUILDING_SKELETON_PARQUET,
            columns=["building_id", "centroid_lon", "centroid_lat", "district",
                      "building_category", "value", "impf_TC", "impf_SS"],
        )
        bldg = filter_points_to_shanghai(bldg, "centroid_lon", "centroid_lat", _load_districts())
        _cache["buildings"] = bldg
    return _cache["buildings"]


def _load_impf_set(kind="TC"):
    key = f"impf_{kind}"
    if key not in _cache:
        pkl = config.IMPF_SET_TC_PKL if kind == "TC" else config.IMPF_SET_SS_PKL
        with open(pkl, "rb") as f:
            _cache[key] = pickle.load(f)
    return _cache[key]


def _load_hazard_metrics(scenario: str, defense_profile=DEFENSE_PROFILE):
    token = {"historical": "historical", "SSP2-4.5": "ssp245", "SSP5-8.5": "ssp585"}[scenario]
    path = config.DEFENSE_HAZARD_METRICS_DIR / f"hazard_metrics_{token}_{defense_profile}.npz"
    data = np.load(path, allow_pickle=True)
    return pd.DataFrame({
        "building_id": data["building_id"].astype(str),
        "tc_max_wind_mps": data["tc_max_wind_mps"].astype(float),
        "tc_event_count": data["tc_event_count"].astype(float),
        "surge_max_depth_m": data["surge_max_depth_m"].astype(float),
        "surge_event_count": data["surge_event_count"].astype(float),
    })


def _load_historical_tracks():
    if "hist_tracks" not in _cache:
        with open(config.TC_TRACKS_PKL, "rb") as f:
            _cache["hist_tracks"] = pickle.load(f)
    return _cache["hist_tracks"]


def _load_all_tracks():
    if "all_tracks" not in _cache:
        with open(config.TC_TRACKS_ALL_PKL, "rb") as f:
            _cache["all_tracks"] = pickle.load(f)
    return _cache["all_tracks"]


def _load_synthetic_tracks():
    if "synth_tracks" not in _cache:
        all_t = _load_all_tracks()
        synth = [t for t in all_t.data if not bool(getattr(t, "orig_event_flag", False))]
        _cache["synth_tracks"] = TCTracks(data=synth)
    return _cache["synth_tracks"]


# ═══════════════════════════════════════════════════════════════════════
# Building-level damage computation (max-event MDR × value proxy)
# ═══════════════════════════════════════════════════════════════════════

def _compute_building_damage(scenario: str, channel: str) -> pd.DataFrame:
    bldg = _load_buildings()
    metrics = _load_hazard_metrics(scenario)
    intensity_col = "tc_max_wind_mps" if channel == "TC" else "surge_max_depth_m"
    impf_col = "impf_TC" if channel == "TC" else "impf_SS"
    haz_type = channel

    merged = bldg.merge(metrics[["building_id", intensity_col]], on="building_id", how="left")
    merged[intensity_col] = merged[intensity_col].fillna(0.0)
    merged["mdr"] = 0.0

    impf_set = _load_impf_set(channel)
    for func in impf_set.get_func(haz_type=haz_type):
        mask = merged[impf_col] == func.id
        if not mask.any():
            continue
        intensities = merged.loc[mask, intensity_col].to_numpy(dtype=float)
        mdd = np.interp(intensities, np.asarray(func.intensity), np.asarray(func.mdd))
        paa = np.interp(intensities, np.asarray(func.intensity), np.asarray(func.paa))
        merged.loc[mask, "mdr"] = mdd * paa

    merged["damage"] = merged["mdr"] * merged["value"]
    return merged[["building_id", "centroid_lon", "centroid_lat", "district", "damage"]].copy()


# ═══════════════════════════════════════════════════════════════════════
# Figure renderers
# ═══════════════════════════════════════════════════════════════════════

# ── Vulnerability hexbin (bf_05, bf_06) ──

def _render_vulnerability_hexbin(out_path: Path, haz_type: str = "TC",
                                  ref_intensity: float = 60.0):
    bld = pd.read_parquet(config.BUILDING_SKELETON_PARQUET,
                          columns=["centroid_lon", "centroid_lat", "impf_TC", "impf_SS"])
    impf_set = _load_impf_set(haz_type)
    bld["mdr"] = 0.0
    col = "impf_TC" if haz_type == "TC" else "impf_SS"
    for func in impf_set.get_func(haz_type=haz_type):
        mask = bld[col] == func.id
        if not mask.any():
            continue
        mdr_curve = np.asarray(func.mdd) * np.asarray(func.paa)
        bld.loc[mask, "mdr"] = float(np.interp(ref_intensity, np.asarray(func.intensity), mdr_curve))

    districts = _load_districts()
    label = "TC" if haz_type == "TC" else "SS"
    fig, ax = plt.subplots(figsize=(10, 8.6))
    districts.plot(ax=ax, facecolor=plt.colormaps["YlOrRd"](0.0), edgecolor="none", zorder=1)
    hb = ax.hexbin(bld["centroid_lon"].to_numpy(), bld["centroid_lat"].to_numpy(),
                   C=bld["mdr"].to_numpy(), gridsize=75, cmap="YlOrRd",
                   reduce_C_function=np.mean, mincnt=1, zorder=2)
    districts.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=0.8, zorder=4)
    annotate_district_labels(ax, districts)
    add_east_china_sea_label(ax)
    add_gov_markers(ax)
    style_map_axis(ax, config, f"{label} Building Vulnerability (MDR @ {ref_intensity:.0f} m/s)")
    add_map_legend(ax)
    fig.colorbar(hb, ax=ax, shrink=0.82, pad=0.02).set_label(
        f"Mean damage ratio at {ref_intensity:.0f} m/s ({label})")
    _save_fig(fig, out_path)


# ── Basic facts (10 figures) ──

def render_basic_facts(out_dir: Path):
    from visualization.basic_facts import (
        render_annual_tc_event_count,
        render_monthly_tc_count_heatmap,
        render_historical_tc_tracks,
        render_combined_exposure_map,
        render_historical_built_up_area,
        render_historical_housing_price,
        render_historical_population,
    )
    from visualization.historical_tc import render_building_type_distribution

    d = _ensure_dir(out_dir)
    render_annual_tc_event_count(config, d / "bf_01_tc_annual_event_count.png")
    render_monthly_tc_count_heatmap(config, d / "bf_02_tc_monthly_count_heatmap.png")
    render_historical_tc_tracks(config, d / "bf_03_historical_tc_tracks.png")
    render_combined_exposure_map(config, d / "bf_04_combined_exposure_map.png")
    _render_vulnerability_hexbin(d / "bf_05_tc_vulnerability_hexbin.png",
                                 haz_type="TC", ref_intensity=60.0)
    _render_vulnerability_hexbin(d / "bf_06_ss_vulnerability_hexbin.png",
                                 haz_type="SS", ref_intensity=3.0)
    render_historical_built_up_area(config, d / "bf_07_historical_built_up_area.png")
    render_historical_housing_price(config, d / "bf_08_historical_housing_price.png")
    render_historical_population(config, d / "bf_09_historical_population.png")
    render_building_type_distribution(config, d / "bf_10_building_type_distribution_map.png")
    print(f"  Basic facts: 10 figures done")


# ── Impact functions (2 figures) ──

def _parse_building_category_from_name(func_name: str) -> str:
    name = str(func_name)
    for prefix in ["TC_", "SS_"]:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    for sep in ["_vhalf", " (k="]:
        if sep in name:
            name = name[:name.index(sep)]
            break
    return name


def render_h_02_tc_impact_functions(out_path: Path):
    impf_set = _load_impf_set("TC")
    fig, ax = plt.subplots(figsize=(11.8, 6.8))
    for func in impf_set.get_func(haz_type="TC"):
        intensity = np.asarray(func.intensity)
        mdr = np.asarray(func.mdd) * np.asarray(func.paa)
        cat_key = _parse_building_category_from_name(func.name)
        label = BUILDING_CATEGORY_LABELS.get(cat_key, str(func.name))
        color = BUILDING_CATEGORY_COLORS.get(cat_key, None)
        x_fine = np.linspace(0, intensity.max(), 300)
        y_fine = np.interp(x_fine, intensity, mdr)
        ax.plot(x_fine, y_fine, linewidth=2.0, label=label, color=color)
        key_winds = np.array([40, 60, 80, 100, 120, 160])
        key_mdr = np.interp(key_winds, intensity, mdr)
        ax.scatter(key_winds, key_mdr, s=30, color=color, zorder=5,
                   edgecolors="white", linewidths=0.5)
    ax.set_title("Tropical Cyclone Impact Functions by Building Type")
    ax.set_xlabel("Wind intensity (m/s)")
    ax.set_ylabel("Mean damage ratio (MDR)")
    ax.set_xlim(0, 180); ax.set_ylim(0, 1.0)
    ax.grid(color="#d9e2ec", linewidth=0.7, alpha=0.9)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.legend(loc="lower right", frameon=False)
    _save_fig(fig, out_path)


def render_h_02_ss_impact_functions(out_path: Path):
    impf_set = _load_impf_set("SS")
    class_labels = {11: "Low-rise residential", 12: "Mid/high-rise residential",
                    13: "High-rise / super tall", 14: "Commercial / public"}
    class_colors = {11: "#e76f51", 12: "#f4a261", 13: "#264653", 14: "#2a9d8f"}
    fig, ax = plt.subplots(figsize=(11.8, 6.8))
    for func in impf_set.get_func(haz_type="SS"):
        depths = np.asarray(func.intensity)
        mdr = np.asarray(func.mdd) * np.asarray(func.paa)
        mask = depths <= 3.05
        d_show, mdr_show = depths[mask], mdr[mask]
        x_fine = np.linspace(0, min(d_show.max(), 3.0), 200)
        y_fine = np.interp(x_fine, d_show, mdr_show)
        label = class_labels.get(func.id, f"ID {func.id}")
        color = class_colors.get(func.id, None)
        ax.plot(x_fine, y_fine, linewidth=2.0, label=label, color=color)
        ax.scatter(d_show, mdr_show, s=25, color=color, zorder=5,
                   edgecolors="white", linewidths=0.5)
    scale = getattr(config, "SURGE_MDR_CALIBRATION_SCALE", 1.0)
    ax.set_title("Storm Surge Depth-Damage Functions (Shanghai RC Calibrated)")
    ax.set_xlabel("Inundation depth (m)")
    ax.set_ylabel("Mean damage ratio (MDR)")
    ax.set_xlim(0, 3.2)
    y_max = max(
        (np.asarray(f.mdd) * np.asarray(f.paa))[np.asarray(f.intensity) <= 3.05].max()
        for f in impf_set.get_func(haz_type="SS")
    )
    ax.set_ylim(0, max(y_max * 1.2, 0.15))
    ax.grid(color="#d9e2ec", linewidth=0.7, alpha=0.9)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.legend(loc="lower right", frameon=False)
    ax.text(0.02, 0.97,
            f"Calibrated from HAZUS-MH Flood Technical Manual (scale={scale:.3f}).\n"
            "Adjusted for Shanghai reinforced-concrete building stock.",
            transform=ax.transAxes, fontsize=8.2, color="#52606d",
            ha="left", va="top", style="italic")
    _save_fig(fig, out_path)


def render_impact_func(out_dir: Path):
    d = _ensure_dir(out_dir)
    render_h_02_tc_impact_functions(d / "if_01_tc_impact_functions.png")
    render_h_02_ss_impact_functions(d / "if_02_ss_impact_functions.png")
    print(f"  Impact functions: 2 figures done")


# ── Historical TC (3 figures) ──

def render_h_03_tc_tracks_historical(out_path: Path):
    tracks = _load_historical_tracks()
    focus = _select_top_intensity(tracks, count=18)
    fig = plt.figure(figsize=(11.2, 8.2))
    ax = fig.add_subplot(111, projection=ccrs.PlateCarree())
    _plot_tracks_single_color(ax, tracks, "#b0b0b0", 0.7, 0.12)
    _plot_tracks_by_category(ax, focus, 1.25, 0.78)
    style_map_axis(ax, config, "Historical Tropical Cyclone Tracks (West Pacific)",
                   bbox=WEST_PACIFIC_BBOX)
    _add_category_legend(ax, include_synthetic=False)
    ax.text(0.02, 0.03,
            f"{tracks.size} historical tracks; {focus.size} representative tracks highlighted",
            transform=ax.transAxes, fontsize=7.8, color="#334e68", ha="left", va="bottom",
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white",
                  "edgecolor": "#e5e7eb", "alpha": 0.82})
    _save_fig(fig, out_path)


def _render_damage_hexbin(scenario: str, channel: str, out_path: Path, title: str):
    damage = _compute_building_damage(scenario, channel)
    districts = _load_districts()
    damage = damage[damage["damage"] > 0].copy()
    if damage.empty:
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.text(0.5, 0.5, f"No {channel} damage for scenario={scenario}",
                ha="center", va="center", fontsize=14, transform=ax.transAxes)
        ax.set_title(title)
        _save_fig(fig, out_path); return

    x = damage["centroid_lon"].to_numpy(float)
    y = damage["centroid_lat"].to_numpy(float)
    c = damage["damage"].to_numpy(float)

    hex_cells = _compute_hexbin_cells(x, y, c, np.sum)
    hex_vals = hex_cells["value"].to_numpy(float)
    # Quantile-equalized norm: ~equal number of cells per colour level
    _pcts = np.linspace(0, 100, 51)
    _raw = np.percentile(hex_vals, _pcts)
    _bounds = np.unique(_raw)
    _bounds = _bounds[_bounds >= 1e3]
    if len(_bounds) >= 3:
        norm = BoundaryNorm(_bounds, ncolors=256, clip=True)
    else:
        norm = LogNorm(vmin=max(float(hex_vals.min()), 1e3),
                       vmax=float(hex_vals.max()))

    fig, ax = plt.subplots(figsize=(10, 8.6))
    districts.plot(ax=ax, facecolor=plt.colormaps["YlOrRd"](0.0), edgecolor="none", zorder=1)
    hb = ax.hexbin(x, y, C=c, reduce_C_function=np.sum, gridsize=HEXBIN_GRIDSIZE, mincnt=1,
                   extent=HEXBIN_EXTENT,
                   cmap="YlOrRd", norm=norm,
                   linewidths=0, zorder=2)
    districts.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=0.8, zorder=4)
    annotate_district_labels(ax, districts)
    add_east_china_sea_label(ax)
    add_gov_markers(ax)
    style_map_axis(ax, config, title)
    add_map_legend(ax)
    fig.colorbar(hb, ax=ax, shrink=0.82, pad=0.02).set_label("Total damage per cell (CNY)")
    _save_fig(fig, out_path)


def _render_damage_hexbin_dual_ssp(channel: str, out_path: Path, title: str):
    districts = _load_districts()
    payloads = {}
    hex_payloads = {}
    all_hex = []
    for sc in SCENARIO_ORDER:
        dmg = _compute_building_damage(sc, channel)
        dmg = dmg[dmg["damage"] > 0].copy()
        payloads[sc] = dmg
        if not dmg.empty:
            cells = _compute_hexbin_cells(
                dmg["centroid_lon"].to_numpy(float),
                dmg["centroid_lat"].to_numpy(float),
                dmg["damage"].to_numpy(float),
                np.sum,
            )
            hex_payloads[sc] = cells
            all_hex.append(cells["value"].to_numpy(float))
        else:
            hex_payloads[sc] = pd.DataFrame(columns=["lon", "lat", "value"])
    if all_hex:
        combined = np.concatenate(all_hex)
        # Quantile-equalized norm: ~equal number of cells per colour level
        _pcts = np.linspace(0, 100, 51)
        _raw = np.percentile(combined, _pcts)
        _bounds_g = np.unique(_raw)
        _bounds_g = _bounds_g[_bounds_g >= 1e3]
        if len(_bounds_g) >= 3:
            norm_g = BoundaryNorm(_bounds_g, ncolors=256, clip=True)
        else:
            norm_g = LogNorm(vmin=max(float(combined.min()), 1e3),
                             vmax=float(combined.max()))
    else:
        norm_g = LogNorm(vmin=1.0, vmax=10.0)

    delta_cells = _build_hex_delta(hex_payloads["SSP2-4.5"], hex_payloads["SSP5-8.5"])
    delta_cells["delta"] = delta_cells["delta"].clip(lower=0)
    delta_vals = delta_cells["delta"].to_numpy(float)
    delta_vmax = max(float(np.quantile(delta_vals[delta_vals > 0], 0.995)), 1e-9) if np.any(delta_vals > 0) else 1.0
    delta_norm = PowerNorm(gamma=0.5, vmin=0, vmax=delta_vmax)

    fig = plt.figure(figsize=(28, 8.5))
    gs = fig.add_gridspec(1, 5, width_ratios=[1, 1, 0.04, 1, 0.04],
                          wspace=0.08, left=0.03, right=0.97, top=0.90, bottom=0.06)
    axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])]
    cax_abs = fig.add_subplot(gs[0, 2])
    ax_delta = fig.add_subplot(gs[0, 3])
    cax_delta = fig.add_subplot(gs[0, 4])

    hb_last = None
    for ax, sc in zip(axes, SCENARIO_ORDER):
        districts.plot(ax=ax, facecolor=plt.colormaps["YlOrRd"](0.0), edgecolor="none", zorder=1)
        dmg = payloads[sc]
        if dmg.empty:
            ax.text(0.5, 0.5, "No damage", ha="center", va="center", transform=ax.transAxes)
        else:
            hb_last = ax.hexbin(dmg["centroid_lon"].to_numpy(float),
                                dmg["centroid_lat"].to_numpy(float),
                                C=dmg["damage"].to_numpy(float),
                                reduce_C_function=np.sum, gridsize=HEXBIN_GRIDSIZE, mincnt=1,
                                extent=HEXBIN_EXTENT,
                                cmap="YlOrRd", norm=norm_g,
                                linewidths=0, zorder=2)
        districts.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=0.8, zorder=4)
        annotate_district_labels(ax, districts)
        add_east_china_sea_label(ax)
        add_gov_markers(ax)
        style_map_axis(ax, config, SCENARIO_LABELS[sc])

    districts.plot(ax=ax_delta, facecolor="#f8fafc", edgecolor="none", zorder=1)
    hb_delta = None
    if delta_cells.empty:
        ax_delta.text(0.5, 0.5, "No delta", ha="center", va="center", transform=ax_delta.transAxes)
    else:
        pos_delta = delta_cells[delta_cells["delta"] > 0]
        hb_delta = ax_delta.hexbin(
            pos_delta["lon"].to_numpy(float),
            pos_delta["lat"].to_numpy(float),
            C=pos_delta["delta"].to_numpy(float),
            reduce_C_function=np.mean,
            gridsize=HEXBIN_GRIDSIZE,
            mincnt=1,
            extent=HEXBIN_EXTENT,
            cmap="OrRd",
            norm=delta_norm,
            linewidths=0,
            zorder=2,
        )
    districts.plot(ax=ax_delta, facecolor="none", edgecolor="black", linewidth=0.8, zorder=4)
    annotate_district_labels(ax_delta, districts)
    add_east_china_sea_label(ax_delta)
    add_gov_markers(ax_delta)
    style_map_axis(ax_delta, config, "SSP5-8.5 \u2212 SSP2-4.5")

    if hb_last is not None:
        fig.colorbar(hb_last, cax=cax_abs).set_label("Total damage per cell (CNY)", fontsize=9)
    if hb_delta is not None:
        fig.colorbar(hb_delta, cax=cax_delta).set_label("\u0394 Damage (CNY)", fontsize=9)
    fig.suptitle(title, y=0.96)
    _save_fig(fig, out_path)


def _render_damage_by_district_bar(scenario: str, channel: str, out_path: Path, title: str):
    damage = _compute_building_damage(scenario, channel)
    summary = (damage.groupby("district", as_index=False)["damage"].sum()
               .sort_values("damage", ascending=True))
    summary["district_en"] = summary["district"].map(DISTRICT_EN_LOOKUP).fillna(summary["district"])
    fig, ax = plt.subplots(figsize=(10.8, 7.2))
    color = "#457b9d" if channel == "TC" else "#2a9d8f"
    ax.barh(summary["district_en"], summary["damage"] / 1e9,
            color=color, edgecolor="#1f2933", linewidth=0.5)
    ax.set_title(title)
    ax.set_xlabel("Damage (billion CNY, max-event proxy)")
    ax.set_ylabel("District")
    ax.grid(axis="x", color="#d9e2ec", linewidth=0.7, alpha=0.9)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    _save_fig(fig, out_path)


def _render_damage_by_district_bar_dual_ssp(channel: str, out_path: Path, title: str):
    all_data = {}
    for sc in SCENARIO_ORDER:
        dmg = _compute_building_damage(sc, channel)
        s = dmg.groupby("district", as_index=False)["damage"].sum()
        s["district_en"] = s["district"].map(DISTRICT_EN_LOOKUP).fillna(s["district"])
        all_data[sc] = s.set_index("district_en")["damage"]
    combined = pd.DataFrame(all_data).fillna(0).sort_values("SSP5-8.5", ascending=True)
    y = np.arange(len(combined))
    bar_h = 0.35
    fig, ax = plt.subplots(figsize=(12, 7.6))
    ax.barh(y - bar_h / 2, combined["SSP2-4.5"] / 1e9, bar_h,
            color=SCENARIO_COLORS["SSP2-4.5"], label="SSP2-4.5",
            edgecolor="#1f2933", linewidth=0.3)
    ax.barh(y + bar_h / 2, combined["SSP5-8.5"] / 1e9, bar_h,
            color=SCENARIO_COLORS["SSP5-8.5"], label="SSP5-8.5",
            edgecolor="#1f2933", linewidth=0.3)
    ax.set_yticks(y); ax.set_yticklabels(combined.index)
    ax.set_title(title)
    ax.set_xlabel("Damage (billion CNY, max-event proxy)")
    ax.set_ylabel("District")
    ax.grid(axis="x", color="#d9e2ec", linewidth=0.7, alpha=0.9)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.legend(loc="lower right", frameon=False)
    _save_fig(fig, out_path)


def render_historical_03(out_dir: Path):
    d = _ensure_dir(out_dir)
    render_h_03_tc_tracks_historical(d / "h_0101_tc_tracks_historical.png")
    _render_damage_hexbin("historical", "TC", d / "h_0102_tc_damage_hexbin.png",
                          "TC Wind Damage Distribution (Historical)")
    _render_damage_by_district_bar("historical", "TC", d / "h_0103_tc_damage_by_district.png",
                                   "TC Wind Damage by District (Historical)")
    print(f"  Historical TC: 3 figures done")


# ── Historical SS (4 figures) ──

def _render_metric_hexbin(scenario: str, metric_col: str, out_path: Path, title: str,
                          cmap: str, color_label: str, use_lognorm: bool = False):
    bldg = _load_buildings()
    metrics = _load_hazard_metrics(scenario)
    merged = bldg.merge(metrics[["building_id", metric_col]], on="building_id", how="left")
    merged[metric_col] = merged[metric_col].fillna(0.0)
    districts = _load_districts()
    pos = merged[merged[metric_col] > 0].copy()

    fig, ax = plt.subplots(figsize=(10, 8.6))
    districts.plot(ax=ax, facecolor=plt.colormaps[cmap](0.0), edgecolor="none", zorder=1)
    if pos.empty:
        ax.text(0.5, 0.5, f"No data for {metric_col}", ha="center", va="center",
                transform=ax.transAxes, fontsize=14)
    else:
        if use_lognorm:
            vmin_v = max(float(pos[metric_col].quantile(0.05)), 1e-6)
            vmax_v = float(pos[metric_col].quantile(0.995))
            norm = LogNorm(vmin=vmin_v, vmax=max(vmax_v, vmin_v * 5))
        else:
            vmax_v = max(float(pos[metric_col].quantile(0.995)), 1e-6)
            norm = PowerNorm(gamma=0.55, vmin=0, vmax=vmax_v)
        hb = ax.hexbin(pos["centroid_lon"].to_numpy(float), pos["centroid_lat"].to_numpy(float),
                       C=pos[metric_col].to_numpy(float),
                       reduce_C_function=np.max, gridsize=HEXBIN_GRIDSIZE, mincnt=1,
                       extent=HEXBIN_EXTENT, cmap=cmap,
                       norm=norm, linewidths=0, zorder=2)
        fig.colorbar(hb, ax=ax, shrink=0.82, pad=0.02).set_label(color_label)
    districts.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=0.8, zorder=4)
    annotate_district_labels(ax, districts)
    add_east_china_sea_label(ax)
    add_gov_markers(ax)
    style_map_axis(ax, config, title)
    add_map_legend(ax)
    _save_fig(fig, out_path)


def _render_metric_hexbin_dual_ssp(metric_col: str, out_path: Path, title: str,
                                    cmap: str, color_label: str, use_lognorm: bool = False):
    bldg = _load_buildings()
    districts = _load_districts()
    payloads = {}
    hex_payloads = {}
    vmin_v, vmax_v = np.inf, 0
    for sc in SCENARIO_ORDER:
        m = _load_hazard_metrics(sc)
        merged = bldg.merge(m[["building_id", metric_col]], on="building_id", how="left")
        merged[metric_col] = merged[metric_col].fillna(0.0)
        pos = merged[merged[metric_col] > 0].copy()
        payloads[sc] = pos
        if not pos.empty:
            hex_payloads[sc] = _compute_hexbin_cells(
                pos["centroid_lon"].to_numpy(float),
                pos["centroid_lat"].to_numpy(float),
                pos[metric_col].to_numpy(float),
                np.max,
            )
            vmin_v = min(vmin_v, float(pos[metric_col].quantile(0.05)))
            vmax_v = max(vmax_v, float(pos[metric_col].quantile(0.995)))
        else:
            hex_payloads[sc] = pd.DataFrame(columns=["lon", "lat", "value"])
    vmin_v = max(vmin_v, 1e-6)
    vmax_v = max(vmax_v, vmin_v * 5)

    norm = LogNorm(vmin=vmin_v, vmax=vmax_v) if use_lognorm else PowerNorm(gamma=0.55, vmin=0, vmax=vmax_v)

    delta_cells = _build_hex_delta(hex_payloads["SSP2-4.5"], hex_payloads["SSP5-8.5"])
    delta_norm = _build_delta_norm(delta_cells["delta"].to_numpy(float))

    fig = plt.figure(figsize=(28, 8.5))
    gs = fig.add_gridspec(1, 5, width_ratios=[1, 1, 0.04, 1, 0.04],
                          wspace=0.08, left=0.03, right=0.97, top=0.90, bottom=0.06)
    axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])]
    cax_abs = fig.add_subplot(gs[0, 2])
    ax_delta = fig.add_subplot(gs[0, 3])
    cax_delta = fig.add_subplot(gs[0, 4])

    hb_last = None
    for ax, sc in zip(axes, SCENARIO_ORDER):
        districts.plot(ax=ax, facecolor=plt.colormaps[cmap](0.0), edgecolor="none", zorder=1)
        pos = payloads[sc]
        if pos.empty:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        else:
            hb_last = ax.hexbin(pos["centroid_lon"].to_numpy(float),
                                pos["centroid_lat"].to_numpy(float),
                                C=pos[metric_col].to_numpy(float),
                                reduce_C_function=np.max, gridsize=HEXBIN_GRIDSIZE, mincnt=1,
                                extent=HEXBIN_EXTENT, cmap=cmap,
                                norm=norm, linewidths=0, zorder=2)
        districts.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=0.8, zorder=4)
        annotate_district_labels(ax, districts)
        add_east_china_sea_label(ax)
        add_gov_markers(ax)
        style_map_axis(ax, config, SCENARIO_LABELS[sc])

    districts.plot(ax=ax_delta, facecolor="#f8fafc", edgecolor="none", zorder=1)
    hb_delta = None
    if delta_cells.empty:
        ax_delta.text(0.5, 0.5, "No delta", ha="center", va="center", transform=ax_delta.transAxes)
    else:
        hb_delta = ax_delta.hexbin(
            delta_cells["lon"].to_numpy(float),
            delta_cells["lat"].to_numpy(float),
            C=delta_cells["delta"].to_numpy(float),
            reduce_C_function=np.mean,
            gridsize=HEXBIN_GRIDSIZE,
            mincnt=1,
            extent=HEXBIN_EXTENT,
            cmap="RdBu_r",
            norm=delta_norm,
            linewidths=0,
            zorder=2,
        )
    districts.plot(ax=ax_delta, facecolor="none", edgecolor="black", linewidth=0.8, zorder=4)
    annotate_district_labels(ax_delta, districts)
    add_east_china_sea_label(ax_delta)
    add_gov_markers(ax_delta)
    style_map_axis(ax_delta, config, "SSP5-8.5 \u2212 SSP2-4.5")

    if hb_last is not None:
        fig.colorbar(hb_last, cax=cax_abs).set_label(color_label, fontsize=9)
    if hb_delta is not None:
        fig.colorbar(hb_delta, cax=cax_delta).set_label(f"\u0394 {color_label}", fontsize=9)
    fig.suptitle(title, y=0.96)
    _save_fig(fig, out_path)


def render_historical_04(out_dir: Path):
    d = _ensure_dir(out_dir)
    _render_metric_hexbin("historical", "surge_max_depth_m",
                          d / "h_0201_ss_depth_hexbin.png",
                          "Storm Surge Depth Distribution (Historical)",
                          "Blues", "Maximum surge depth (m)", use_lognorm=True)
    _render_metric_hexbin("historical", "surge_event_count",
                          d / "h_0202_ss_occurrence_hexbin.png",
                          "Storm Surge Event Occurrence (Historical)",
                          "YlOrRd", "Surge event count", use_lognorm=True)
    _render_damage_hexbin("historical", "SS",
                          d / "h_0203_ss_damage_hexbin.png",
                          "Storm Surge Damage Distribution (Historical)")
    _render_damage_by_district_bar("historical", "SS",
                                   d / "h_0204_ss_damage_by_district.png",
                                   "Storm Surge Damage by District (Historical)")
    print(f"  Historical SS: 4 figures done")


# ── Historical compound (1 figure) ──

def _render_compound_bar(scenarios: list[str], out_path: Path, title: str):
    defense_eal = pd.read_csv(config.DEFENSE_PROFILE_EAL_CSV)
    subset = defense_eal[defense_eal["defense_profile"] == DEFENSE_PROFILE].copy()

    if len(scenarios) == 1:
        panel = subset[subset["scenario"] == scenarios[0]].copy()
        panel = panel.sort_values("EAL_compound", ascending=True)
        panel["district_en"] = panel["district"].map(DISTRICT_EN_LOOKUP).fillna(panel["district"])
        tc = panel["EAL_wind"].to_numpy(float) / 1e9
        ss = panel["EAL_base_surge_only"].to_numpy(float) / 1e9
        interaction = panel["EAL_compound_adjustment"].to_numpy(float) / 1e9
        y = np.arange(len(panel))

        fig, ax = plt.subplots(figsize=(12, 7.6))
        ax.barh(y, tc, color="#457b9d", label="TC wind")
        ax.barh(y, ss, left=tc, color="#2a9d8f", label="SS surge")
        pos = np.clip(interaction, 0, None)
        neg = np.clip(interaction, None, 0)
        ax.barh(y, pos, left=tc + ss, color="#f4a261", label="Interaction (+)")
        ax.barh(y, neg, left=tc + ss, color="#e76f51", label="Interaction (-)")
        total = tc + ss + interaction
        ax.plot(total, y, "o", color="#1f2933", markersize=3.5, label="Total compound")
        ax.set_yticks(y); ax.set_yticklabels(panel["district_en"])
        ax.set_xlabel("Expected Annual Loss (billion CNY)")
        ax.set_ylabel("District"); ax.set_title(title)
        ax.grid(axis="x", color="#d9e2ec", linewidth=0.7, alpha=0.9)
        ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
        ax.legend(loc="lower right", frameon=False)
        _save_fig(fig, out_path)
    else:
        fig, axes = plt.subplots(1, len(scenarios), figsize=(9 * len(scenarios), 7.6))
        if len(scenarios) == 1:
            axes = [axes]
        for ax, sc in zip(axes, scenarios):
            panel = subset[subset["scenario"] == sc].copy()
            panel = panel.sort_values("EAL_compound", ascending=True)
            panel["district_en"] = panel["district"].map(DISTRICT_EN_LOOKUP).fillna(panel["district"])
            tc = panel["EAL_wind"].to_numpy(float) / 1e9
            ss = panel["EAL_base_surge_only"].to_numpy(float) / 1e9
            interaction = panel["EAL_compound_adjustment"].to_numpy(float) / 1e9
            y = np.arange(len(panel))
            ax.barh(y, tc, color="#457b9d", label="TC wind")
            ax.barh(y, ss, left=tc, color="#2a9d8f", label="SS surge")
            pos = np.clip(interaction, 0, None)
            neg = np.clip(interaction, None, 0)
            ax.barh(y, pos, left=tc + ss, color="#f4a261", label="Interaction (+)")
            ax.barh(y, neg, left=tc + ss, color="#e76f51", label="Interaction (-)")
            total = tc + ss + interaction
            ax.plot(total, y, "o", color="#1f2933", markersize=3.5,
                    label="Total compound" if sc == scenarios[0] else None)
            ax.set_yticks(y); ax.set_yticklabels(panel["district_en"])
            ax.set_title(SCENARIO_LABELS[sc])
            ax.set_xlabel("Expected Annual Loss (billion CNY)")
            ax.grid(axis="x", color="#d9e2ec", linewidth=0.7, alpha=0.9)
            ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
        axes[0].set_ylabel("District")
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=5, frameon=False,
                   bbox_to_anchor=(0.5, -0.05))
        fig.suptitle(title, y=1.02)
        fig.subplots_adjust(bottom=0.12, wspace=0.12)
        _save_fig(fig, out_path)


def render_historical_05(out_dir: Path):
    d = _ensure_dir(out_dir)
    _render_compound_bar(
        ["historical"],
        d / "h_0301_compound_damage_by_district.png",
        "TC x SS Compound Damage by District (Historical, with Interaction)",
    )
    print(f"  Historical compound: 1 figure done")


# ── Synthetic TC (3 figures) ──

def render_s_03_tc_tracks_synthetic(out_path: Path):
    synth = _load_synthetic_tracks()
    focus = _select_top_intensity(synth, count=18, unique_source=True)
    fig = plt.figure(figsize=(11.2, 8.2))
    ax = fig.add_subplot(111, projection=ccrs.PlateCarree())
    _plot_tracks_single_color(ax, synth, "#d4d4d4", 0.4, 0.08)
    _plot_tracks_by_category(ax, focus, 1.1, 0.65, linestyle=(0, (4, 3)))
    style_map_axis(ax, config, "Synthetic Tropical Cyclone Tracks (West Pacific)",
                   bbox=WEST_PACIFIC_BBOX)
    handles = [
        Line2D([0], [0], color="#d4d4d4", lw=0.7, alpha=0.2),
        Line2D([0], [0], color="#666", lw=1.2, linestyle=(0, (4, 3))),
    ]
    labels = [f"All synthetic tracks ({synth.size})",
              f"Representative synthetic ({focus.size}, dashed)"]
    for cat in sorted(SAFFIR_SIMPSON_COLORS.keys()):
        handles.append(Line2D([0], [0], color=SAFFIR_SIMPSON_COLORS[cat], lw=1.4, alpha=0.85,
                              linestyle=(0, (4, 3))))
        labels.append(SAFFIR_SIMPSON_LABELS[cat])
    ax.legend(handles, labels, loc="upper left", fontsize=7, frameon=True,
              facecolor="white", edgecolor="#e5e7eb", framealpha=0.92)
    _save_fig(fig, out_path)


def render_synthetic_03(out_dir: Path):
    d = _ensure_dir(out_dir)
    render_s_03_tc_tracks_synthetic(d / "s_0101_tc_tracks_synthetic.png")
    _render_damage_hexbin_dual_ssp("TC", d / "s_0102_tc_damage_hexbin.png",
                                   "TC Wind Damage Distribution (SSP Scenarios)")
    _render_damage_by_district_bar_dual_ssp("TC", d / "s_0103_tc_damage_by_district.png",
                                            "TC Wind Damage by District (SSP Scenarios)")
    print(f"  Synthetic TC: 3 figures done")


# ── Synthetic SS (4 figures) ──

def render_synthetic_04(out_dir: Path):
    d = _ensure_dir(out_dir)
    _render_metric_hexbin_dual_ssp("surge_max_depth_m",
                                    d / "s_0201_ss_depth_hexbin.png",
                                    "Storm Surge Depth Distribution (SSP Scenarios)",
                                    "Blues", "Maximum surge depth (m)", use_lognorm=True)
    _render_metric_hexbin_dual_ssp("surge_event_count",
                                    d / "s_0202_ss_occurrence_hexbin.png",
                                    "Storm Surge Event Occurrence (SSP Scenarios)",
                                    "YlOrRd", "Surge event count", use_lognorm=True)
    _render_damage_hexbin_dual_ssp("SS", d / "s_0203_ss_damage_hexbin.png",
                                   "Storm Surge Damage Distribution (SSP Scenarios)")
    _render_damage_by_district_bar_dual_ssp("SS", d / "s_0204_ss_damage_by_district.png",
                                            "Storm Surge Damage by District (SSP Scenarios)")
    print(f"  Synthetic SS: 4 figures done")


# ── Synthetic compound (1 figure) ──

def render_synthetic_05(out_dir: Path):
    d = _ensure_dir(out_dir)
    _render_compound_bar(
        SCENARIO_ORDER,
        d / "s_0301_compound_damage_by_district.png",
        "TC x SS Compound Damage by District (SSP Scenarios, with Interaction)",
    )
    print(f"  Synthetic compound: 1 figure done")


# ── Climate Risk Index (1 figure) ──

def render_climate_index(out_dir: Path):
    d = _ensure_dir(out_dir)

    # ── Load CRI data ────────────────────────────────────────────────
    haz = pd.read_csv(config.CFI_HAZARD_CITY_CSV)
    haz["date"] = pd.to_datetime(haz["date"])
    haz = haz.sort_values("date")

    has_cri = "cri_index" in haz.columns and haz["cri_index"].notna().any()

    if not has_cri:
        haz["cri_raw"] = haz["hazard_index"]
        haz["cri_12m"] = haz["cri_raw"].rolling(12, min_periods=6).mean()
        first_valid = haz["cri_12m"].first_valid_index()
        base = haz.loc[first_valid, "cri_12m"] if first_valid is not None else 1.0
        haz["cri_index"] = 100.0 * haz["cri_12m"] / max(base, 1e-12)
        haz["e_norm"] = 1.0
        haz["v_norm"] = 1.0
        haz["damage_signal"] = 0.0

    df = haz.copy()

    # ── Load projection CSV ──────────────────────────────────────────
    proj_csv = config.CRI_PROJECTION_CSV
    has_proj = proj_csv.exists()
    proj = None
    if has_proj:
        proj = pd.read_csv(proj_csv)
        proj["date"] = pd.to_datetime(proj["date"])
        proj = proj.sort_values(["scenario", "date"])

    # ── Color palette ────────────────────────────────────────────────
    C_MAIN = "#D35400"
    C_RAW = "#F5B895"
    C_DAMAGE = "#E74C3C"
    C_FILL = "#FDEBD0"
    C_GRID = "#ECF0F1"
    C_HIST_PROJ = "#E67E22"
    C_SSP245 = "#2980B9"
    C_SSP585 = "#C0392B"

    end_year = config.CRI_PROJECTION_END_YEAR if has_proj else 2023

    # ── Two-panel figure ─────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(22, 8),
                                   gridspec_kw={"width_ratios": [1.15, 1],
                                                "wspace": 0.18})

    base_val = df.loc[df["cri_12m"].first_valid_index(), "cri_12m"] if has_cri else 1.0
    base_val = max(base_val, 1e-12)
    last_cri_val = df.dropna(subset=["cri_index"])["cri_index"].iloc[-1]
    valid_hist = df.dropna(subset=["cri_index"])

    # ── Helper: draw historical portion on an axis ───────────────────
    def _draw_hist(ax, show_raw=True, show_events=True):
        valid_mask = df["cri_index"].notna()
        ax.fill_between(df.loc[valid_mask, "date"], 0,
                        df.loc[valid_mask, "cri_index"],
                        color=C_FILL, alpha=0.4, zorder=0)
        if show_raw and has_cri:
            raw_idx = 100.0 * df["cri_raw"] / base_val
            clip_hi = np.nanpercentile(raw_idx.dropna(), 99.5)
            ax.plot(df["date"], raw_idx.clip(upper=clip_hi),
                    color=C_RAW, linewidth=0.5, alpha=0.4, zorder=1)
        ax.plot(df["date"], df["cri_index"], color=C_MAIN, linewidth=2.8,
                label="Shanghai CRI (12-mo mean)", zorder=4)
        if show_events and "risk_total" in df.columns:
            events = df[df["risk_total"] > 0].copy()
            if not events.empty:
                top_events = events.nlargest(min(12, len(events)), "risk_total")
                ax.scatter(top_events["date"], top_events["cri_index"],
                           color=C_DAMAGE, s=30, zorder=5,
                           edgecolors="white", linewidths=0.6,
                           label="TC Damage Events (CLIMADA)")

    # ── Helper: style an axis ────────────────────────────────────────
    def _style_ax(ax, ylabel=True):
        if ylabel:
            ax.set_ylabel("CRI Level (Base 100)", fontsize=13, fontweight="bold")
        ax.set_xlabel("Date", fontsize=12)
        ax.grid(True, alpha=0.3, linestyle="-", color=C_GRID, zorder=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.xaxis.set_major_locator(mdates.YearLocator(5))
        ax.xaxis.set_minor_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # ══════════════════════════════════════════════════════════════════
    # Panel A (left): Scenario Comparison — p50 median lines
    # ══════════════════════════════════════════════════════════════════
    _draw_hist(ax1, show_raw=True, show_events=True)

    scenario_styles = {
        "Historical Baseline": {"color": C_HIST_PROJ, "ls": "--",
                                "lw": 2.2, "fill": "#F5CBA7",
                                "label": "Historical Baseline"},
        "SSP2-4.5":            {"color": C_SSP245,    "ls": "-.",
                                "lw": 2.2, "fill": "#AED6F1",
                                "label": "SSP2-4.5"},
        "SSP5-8.5":            {"color": C_SSP585,    "ls": "-",
                                "lw": 2.2, "fill": "#F5B7B1",
                                "label": "SSP5-8.5"},
    }

    end_vals_a = []
    if has_proj and proj is not None:
        last_hist_date = df["date"].max()
        ax1.axvline(last_hist_date, color="#95A5A6", linewidth=0.8,
                    linestyle=":", alpha=0.6, zorder=2)

        for scenario, style in scenario_styles.items():
            s_data = proj[proj["scenario"] == scenario].copy()
            if s_data.empty:
                continue

            dates_plot = pd.DatetimeIndex(
                [last_hist_date] + s_data["date"].tolist())

            # Use p50 (median) for monotonic main line
            vals_main = np.concatenate(
                [[last_cri_val], s_data["cri_index_p50"].values])

            if "cri_index_p10" in s_data.columns:
                vals_p10 = np.concatenate(
                    [[last_cri_val], s_data["cri_index_p10"].values])
                vals_p90 = np.concatenate(
                    [[last_cri_val], s_data["cri_index_p90"].values])
                ax1.fill_between(dates_plot, vals_p10, vals_p90,
                                 color=style["fill"], alpha=0.22, zorder=1)

            ax1.plot(dates_plot, vals_main,
                     color=style["color"], linewidth=style["lw"],
                     linestyle=style["ls"], label=style["label"],
                     zorder=4)

            end_val = s_data["cri_index_p50"].iloc[-1]
            end_date = s_data["date"].iloc[-1]
            end_vals_a.append((end_val, end_date, style["color"]))

    ax1.legend(fontsize=8.5, loc="upper left", framealpha=0.9,
               edgecolor="#D5DBDB", fancybox=True, ncol=2)
    _style_ax(ax1)

    x_end = proj["date"].max() if has_proj and proj is not None else df["date"].max()
    ax1.set_xlim(df["date"].min(), x_end + pd.Timedelta(days=180))
    y_max = df["cri_index"].max()
    if has_proj and proj is not None and "cri_index_p90" in proj.columns:
        y_max = max(y_max, proj["cri_index_p90"].max())
    ax1.set_ylim(0, y_max * 1.12)

    # Anti-overlap annotations for Panel A (needs y_max)
    if has_proj and end_vals_a:
        end_vals_a.sort(key=lambda x: x[0])
        min_gap_a = y_max * 0.04
        placed_a = []
        for val, dt, col in end_vals_a:
            y_pos = val
            for p in placed_a:
                if abs(y_pos - p) < min_gap_a:
                    y_pos = p + min_gap_a
            placed_a.append(y_pos)
            ax1.annotate(f"{val:.0f}",
                         xy=(dt, val),
                         xytext=(6, y_pos - val),
                         textcoords="offset points",
                         fontsize=10, color=col, fontweight="bold",
                         va="center")

    if len(valid_hist) > 0:
        y_start = valid_hist["cri_index"].iloc[0]
        ax1.annotate(f"{y_start:.0f}",
                     xy=(valid_hist["date"].iloc[0], y_start),
                     fontsize=9, color=C_MAIN, fontweight="bold",
                     xytext=(-30, 10), textcoords="offset points")

    ax1.set_title("A. Scenario Comparison (Median Projections)",
                  fontsize=12, fontweight="bold", pad=8)

    # ══════════════════════════════════════════════════════════════════
    # Panel B (right): Representative Pathways — all 3 scenarios
    # ══════════════════════════════════════════════════════════════════
    _draw_hist(ax2, show_raw=False, show_events=False)

    if has_proj and proj is not None:
        last_hist_date = df["date"].max()
        ax2.axvline(last_hist_date, color="#95A5A6", linewidth=0.8,
                    linestyle=":", alpha=0.6, zorder=2)

        end_vals = []  # collect (end_val, end_date, color) for anti-overlap
        for scenario, style in scenario_styles.items():
            s_data = proj[proj["scenario"] == scenario].copy()
            if s_data.empty:
                continue

            dates_plot = pd.DatetimeIndex(
                [last_hist_date] + s_data["date"].tolist())

            # Representative characteristic path
            vals_rep = np.concatenate(
                [[last_cri_val], s_data["cri_index_rep"].values])
            ax2.plot(dates_plot, vals_rep,
                     color=style["color"], linewidth=2.2,
                     linestyle=style["ls"], label=style["label"],
                     zorder=4)

            end_val = s_data["cri_index_rep"].iloc[-1]
            end_date = s_data["date"].iloc[-1]
            end_vals.append((end_val, end_date, style["color"]))

        # Anti-overlap annotation: sort by value, nudge if too close
        end_vals.sort(key=lambda x: x[0])
        min_gap = y_max * 0.065  # Increased from 0.04
        placed = []
        for val, dt, col in end_vals:
            y_pos = val
            for p in placed:
                if abs(y_pos - p) < min_gap:
                    y_pos = p + min_gap
            placed.append(y_pos)
            ax2.annotate(f"{val:.0f}",
                         xy=(dt, val),
                         xytext=(6, y_pos - val),
                         textcoords="offset points",
                         fontsize=10, color=col, fontweight="bold",
                         va="center")

    ax2.legend(fontsize=8.5, loc="upper left", framealpha=0.9,
               edgecolor="#D5DBDB", fancybox=True, ncol=1)
    _style_ax(ax2, ylabel=False)

    ax2.set_xlim(df["date"].min(), x_end + pd.Timedelta(days=180))
    ax2.set_ylim(0, y_max * 1.12)

    ax2.set_title("B. Representative Pathways (Characteristic MC Paths)",
                  fontsize=12, fontweight="bold", pad=8)

    # ── Suptitle & footnote ──────────────────────────────────────────
    fig.suptitle(f"Shanghai Climate Risk Index (1993 \u2013 {end_year})",
                 fontsize=16, fontweight="bold", y=0.98)
    fig.text(0.5, 0.01,
             "CRI = H(OU) \u00d7 E(Logistic-GBM) \u00d7 V(Logistic-GBM) "
             "\u00d7 (1 + \u03ba\u00b7S(Compound Poisson))  |  "
             "Bands: 10th\u201390th percentile, N=500 MC paths",
             fontsize=7.5, color="#7F8C8D", ha="center", va="bottom",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                       edgecolor="#E5E7EB", alpha=0.9))

    _save_fig(fig, d / "ci_01_climate_risk_index.png")
    print(f"  Climate index: 1 figure done")


def render_defense_evidence(out_dir: Path):
    d = _ensure_dir(out_dir)
    df = pd.read_csv(config.DEFENSE_PROFILE_EAL_CSV)

    scenario_order = ["historical", "SSP2-4.5", "SSP5-8.5"]
    scenario_labels = {
        "historical": "Historical",
        "SSP2-4.5": "SSP2-4.5",
        "SSP5-8.5": "SSP5-8.5",
    }
    profile_order = ["baseline_nodef", "current_def_gap"]
    profile_labels = {
        "baseline_nodef": "No\ndefence",
        "current_def_gap": "Current\n6 m",
    }

    city = (
        df.groupby(["scenario", "defense_profile"], as_index=False)
        [["EAL_compound", "EAL_wind", "EAL_surge"]]
        .sum()
    )

    hist = df[df["scenario"] == "historical"].copy()
    hist_pivot = hist.pivot(index="district", columns="defense_profile", values="EAL_compound")
    hist_pivot = hist_pivot.dropna(subset=profile_order)
    hist_pivot["reduction_pct"] = 100.0 * (
        1.0 - hist_pivot["current_def_gap"] / hist_pivot["baseline_nodef"]
    )
    hist_pivot["district_en"] = [DISTRICT_EN_LOOKUP.get(idx, idx) for idx in hist_pivot.index]
    hist_pivot = hist_pivot.sort_values("reduction_pct", ascending=True)

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(16.8, 7.4), gridspec_kw={"width_ratios": [1.08, 0.92], "wspace": 0.26}
    )
    fig.subplots_adjust(bottom=0.22)

    wind_color = "#457b9d"
    surge_nodef = "#e76f51"
    surge_def = "#2a9d8f"
    edge_color = "#1f2933"
    width = 0.34
    centers = np.arange(len(scenario_order)) * 1.7
    offsets = {"baseline_nodef": -0.26, "current_def_gap": 0.26}

    xticks = []
    xlabels = []
    total_max = 0.0
    for profile in profile_order:
        xs = centers + offsets[profile]
        subset = city[city["defense_profile"] == profile].set_index("scenario").loc[scenario_order]
        wind = subset["EAL_wind"].to_numpy(float) / 1e9
        surge = subset["EAL_surge"].to_numpy(float) / 1e9
        ax1.bar(
            xs, wind, width=width, color=wind_color, edgecolor=edge_color, linewidth=0.5,
            label="TC wind" if profile == "baseline_nodef" else None,
        )
        ax1.bar(
            xs, surge, width=width, bottom=wind,
            color=surge_nodef if profile == "baseline_nodef" else surge_def,
            edgecolor=edge_color, linewidth=0.5,
            label=("SS surge (no defence)" if profile == "baseline_nodef" else "SS surge (current 6 m)"),
        )
        totals = wind + surge
        total_max = max(total_max, float(totals.max()))
        for x, total in zip(xs, totals):
            ax1.text(x, total + 2.3, f"{total:.1f}", ha="center", va="bottom", fontsize=8, color="#334e68")
        xticks.extend(xs.tolist())
        xlabels.extend([profile_labels[profile]] * len(xs))

    ax1.set_xticks(xticks)
    ax1.set_xticklabels(xlabels)
    ax1.tick_params(axis="x", labelsize=9, pad=10)
    ax1.set_ylabel("City-wide EAL (billion CNY)")
    ax1.set_title("A. City-wide EAL by Scenario and Defence Profile")
    ax1.grid(axis="y", color="#d9e2ec", linewidth=0.7, alpha=0.9)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    for center, scenario in zip(centers, scenario_order):
        ax1.text(
            center, -0.14, scenario_labels[scenario],
            transform=ax1.get_xaxis_transform(), ha="center", va="top",
            fontsize=9, color="#52606d",
        )
    ax1.text(
        0.98, 0.98,
        "TC wind totals are identical across defence profiles by construction.",
        transform=ax1.transAxes, ha="right", va="top", fontsize=8.4, color="#52606d",
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "#d9e2ec", "alpha": 0.9},
    )
    y_top = np.ceil(max(total_max * 1.26, total_max + 7.0) / 5.0) * 5.0
    ax1.set_ylim(0, y_top)
    ax1.legend(loc="upper left", frameon=False)

    y = np.arange(len(hist_pivot))
    city_hist = city[city["scenario"] == "historical"].set_index("defense_profile")
    city_reduction = 100.0 * (
        1.0 - city_hist.loc["current_def_gap", "EAL_compound"] / city_hist.loc["baseline_nodef", "EAL_compound"]
    )
    ax2.barh(
        y, hist_pivot["reduction_pct"].to_numpy(float), color="#2a9d8f",
        edgecolor=edge_color, linewidth=0.45,
    )
    ax2.axvline(city_reduction, color="#e76f51", linestyle="--", linewidth=1.4,
                label=f"City-wide mean = {city_reduction:.1f}%")
    ax2.set_yticks(y)
    ax2.set_yticklabels(hist_pivot["district_en"])
    ax2.set_xlabel("Historical EAL reduction (%)")
    ax2.set_ylabel("District")
    ax2.set_title("B. Historical District-Level Reduction Rates")
    ax2.grid(axis="x", color="#d9e2ec", linewidth=0.7, alpha=0.9)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.set_xlim(0, max(75, hist_pivot["reduction_pct"].max() * 1.08))
    ax2.legend(loc="lower right", frameon=False)

    fig.suptitle("Defence Sensitivity Evidence from Active Model Outputs", y=0.98, fontsize=14)
    _save_fig(fig, d / "df_01_defense_evidence.png")
    print(f"  Defense evidence: 1 figure done")


# ═══════════════════════════════════════════════════════════════════════
# Main orchestration
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Generate publication figures (v8)")
    parser.add_argument("--only", type=str, default=None,
                        help="Generate only: basic_facts, impact_func, historical, synthetic, climate_index, defense")
    args = parser.parse_args()

    target = args.only
    bf_dir = FIGURES_NEW_DIR / "01_basic_facts"
    if_dir = FIGURES_NEW_DIR / "02_impact_func"
    hist_dir = FIGURES_NEW_DIR / "historical"
    synth_dir = FIGURES_NEW_DIR / "synthetic"
    ci_dir = FIGURES_NEW_DIR / "climate_index"
    defense_dir = FIGURES_NEW_DIR / "04_defense"

    if target is None or target == "basic_facts":
        print("=== BASIC FACTS (shared) ===")
        render_basic_facts(bf_dir)

    if target is None or target == "impact_func":
        print("=== IMPACT FUNCTIONS ===")
        render_impact_func(if_dir)

    if target is None or target == "historical":
        print("=== HISTORICAL ===")
        render_historical_03(hist_dir / "01_TC")
        render_historical_04(hist_dir / "02_SS")
        render_historical_05(hist_dir / "03_compound")

    if target is None or target == "synthetic":
        print("=== SYNTHETIC ===")
        render_synthetic_03(synth_dir / "01_TC")
        render_synthetic_04(synth_dir / "02_SS")
        render_synthetic_05(synth_dir / "03_compound")

    if target is None or target == "climate_index":
        print("=== CLIMATE INDEX ===")
        render_climate_index(ci_dir)

    if target is None or target == "defense":
        print("=== DEFENSE EVIDENCE ===")
        render_defense_evidence(defense_dir)

    print(f"\nAll figures saved to: {FIGURES_NEW_DIR}")


if __name__ == "__main__":
    main()
