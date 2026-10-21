"""Basic-fact figure renderers (10 figures in 01_basic_facts/).

Figures produced:
  bf_01  TC annual event count bar chart
  bf_02  TC monthly count heatmap
  bf_03  Historical TC tracks (West Pacific)
  bf_04  Combined building + population exposure map
  bf_07  Historical built-up area (multi-panel)
  bf_08  Historical housing price by district
  bf_09  Historical population stacked bar
  (bf_05, bf_06 vulnerability hexbin and bf_10 building-type map
   are rendered directly in generate_figures_new.py / historical_tc.py)
"""
from __future__ import annotations

import pickle
import re
from pathlib import Path

import cartopy.crs as ccrs
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from climada.hazard import TCTracks
from matplotlib.collections import LineCollection
from matplotlib.colors import BoundaryNorm, LogNorm
from matplotlib.lines import Line2D
from rasterio.plot import plotting_extent

from climate_functions import load_raster_clip_shanghai
from district_price_data import load_district_price_long

from .maps import (
    add_east_china_sea_label,
    add_gov_markers,
    add_map_legend,
    aggregate_points_to_masked_grid,
    annotate_district_labels,
    filter_points_to_shanghai,
    load_district_boundaries,
    style_map_axis,
)
from .style import DISTRICT_EN_LOOKUP

# ── Track visualization constants ──
WEST_PACIFIC_BBOX = (110.0, 5.0, 160.0, 45.0)
SAFFIR_SIMPSON_THRESHOLDS_KT = [34.0, 64.0, 83.0, 96.0, 113.0, 137.0]
SAFFIR_SIMPSON_COLORS = {
    -1: "#6baed6", 0: "#74c476", 1: "#fdd835", 2: "#fb8c00",
    3: "#e53935", 4: "#ad1457", 5: "#6a1b9a",
}
SAFFIR_SIMPSON_LABELS = {
    -1: "TD", 0: "TS", 1: "Cat 1", 2: "Cat 2",
    3: "Cat 3", 4: "Cat 4", 5: "Cat 5",
}

# ── Track helpers ──

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
        return lon, lat, np.asarray([], dtype=int)
    segment_wind = np.nanmax(np.column_stack([wind[:-1], wind[1:]]), axis=1)
    segment_category = np.array([_wind_to_category_knots(v) for v in segment_wind], dtype=int)
    return lon, lat, segment_category


def _plot_tc_tracks_by_category(ax, track_set, linewidth, alpha, linestyle="solid"):
    tracks = track_set.data if isinstance(track_set, TCTracks) else track_set
    by_cat: dict[int, list] = {}
    for track in tracks:
        lon, lat, cats = _track_segment_categories(track)
        if lon.size < 2:
            continue
        coords = np.column_stack([lon, lat])
        segments = np.stack([coords[:-1], coords[1:]], axis=1)
        for cat in sorted(SAFFIR_SIMPSON_COLORS):
            m = cats == cat
            if np.any(m):
                by_cat.setdefault(cat, []).extend(list(segments[m]))
    for cat, segs in sorted(by_cat.items()):
        if segs:
            ax.add_collection(LineCollection(
                segs, colors=SAFFIR_SIMPSON_COLORS.get(cat, "#999"),
                linewidths=linewidth, linestyles=linestyle, alpha=alpha,
                transform=ccrs.PlateCarree(), zorder=3,
            ))


def _plot_tc_tracks_single_style(ax, track_set, color, linewidth, alpha):
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


def _track_peak_wind(track) -> float:
    w = np.asarray(track["max_sustained_wind"], dtype=float)
    return float(np.nanmax(w)) if w.size else float("-inf")


def _select_top_intensity(track_set, count=18):
    tracks = track_set.data if isinstance(track_set, TCTracks) else track_set
    ranked = sorted(tracks, key=lambda t: -_track_peak_wind(t))
    return TCTracks(data=ranked[:count])


def _add_category_legend(ax):
    handles = [Line2D([0], [0], color="#b0b0b0", lw=0.7, alpha=0.3)]
    labels = ["All historical tracks"]
    for cat in sorted(SAFFIR_SIMPSON_COLORS.keys()):
        handles.append(Line2D([0], [0], color=SAFFIR_SIMPSON_COLORS[cat], lw=1.4, alpha=0.85))
        labels.append(SAFFIR_SIMPSON_LABELS[cat])
    ax.legend(handles, labels, loc="upper left", fontsize=7.2, frameon=True,
              facecolor="white", edgecolor="#e5e7eb", framealpha=0.92)


# ── Data loaders ──

def load_tc_alignment(config) -> pd.DataFrame:
    return (pd.read_csv(config.TC_DATE_ALIGNMENT_CSV)
            .sort_values(["hazard_year", "hazard_month", "event_name"])
            .reset_index(drop=True))


def load_tc_tracks(config):
    with open(config.TC_TRACKS_PKL, "rb") as f:
        return pickle.load(f)


def _month_label(month: int) -> str:
    return pd.Timestamp(year=2000, month=month, day=1).strftime("%b")


def _iter_built_up_files(config):
    files = []
    for shp in sorted(config.BUILT_UP_AREA_DIR.glob("*.shp")):
        m = re.match(r"(\d{4})_", shp.stem)
        if m:
            files.append((int(m.group(1)), shp))
    return files


def _melt_district_price_table(config) -> pd.DataFrame:
    long = load_district_price_long(config)
    long = long[["district_std", "date", "district_price", "price_imputed"]].rename(
        columns={"district_std": "district", "district_price": "price_cny_per_sqm"},
    )
    return long.dropna(subset=["price_cny_per_sqm"]).copy()


def _load_district_population_series(config) -> pd.DataFrame:
    pop_path = config.TOWNSHIP_POP_DIR / "excel格式的数据" / "上海乡镇层级_人口数.xlsx"
    population = pd.read_excel(pop_path)
    year_cols = [c for c in population.columns if re.fullmatch(r"\d{4}", str(c))]
    district_col = "County" if "County" in population.columns else "District"
    district = population.groupby(district_col, as_index=False)[year_cols].sum()
    district[district_col] = district[district_col].replace(config.ADMIN_DISTRICT_RENAME)
    long = district.melt(id_vars=[district_col], value_vars=year_cols,
                         var_name="year", value_name="population_total")
    long = long.rename(columns={district_col: "district"})
    long["year"] = long["year"].astype(int)
    long["population_total"] = long["population_total"].astype(float)
    return long


# ═══════════════════════════════════════════════════════════════════════
# Renderers
# ═══════════════════════════════════════════════════════════════════════

def render_annual_tc_event_count(config, output_path: Path) -> Path:
    alignment = load_tc_alignment(config)
    annual = alignment.groupby("hazard_year").size()
    fig, ax = plt.subplots(figsize=(13.2, 4.8))
    ax.bar(annual.index.to_numpy(int), annual.to_numpy(float),
           width=0.8, color="#2b6f77", edgecolor="#173f4f", linewidth=0.4)
    ax.set_title("Annual Tropical Cyclone Event Count in Shanghai")
    ax.set_xlabel("Year"); ax.set_ylabel("Event count")
    ax.grid(axis="y", color="#d9e2ec", linewidth=0.7, alpha=0.9); ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.set_xlim(int(annual.index.min()) - 1, int(annual.index.max()) + 1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight"); plt.close(fig)
    return output_path


def render_monthly_tc_count_heatmap(config, output_path: Path) -> Path:
    alignment = load_tc_alignment(config)
    monthly = alignment.groupby("hazard_month").size().reindex(range(1, 13), fill_value=0)
    heat = monthly.to_numpy(float)[np.newaxis, :]
    fig, ax = plt.subplots(figsize=(11.5, 2.8))
    im = ax.imshow(heat, aspect="auto", cmap="YlOrRd", vmin=0,
                   vmax=max(1.0, float(monthly.max())))
    ax.set_title("Monthly Tropical Cyclone Event Frequency")
    ax.set_xticks(np.arange(12))
    ax.set_xticklabels([_month_label(m) for m in range(1, 13)])
    ax.set_yticks([0]); ax.set_yticklabels(["Historical period"])
    ax.set_xlabel("Month")
    for i, cnt in enumerate(monthly.to_numpy(int)):
        color = "#102a43" if cnt < 20 else "white"
        ax.text(i, 0, str(cnt), ha="center", va="center", color=color, fontsize=10, fontweight="bold")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.colorbar(im, ax=ax, shrink=0.88, pad=0.02).set_label("Event count")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight"); plt.close(fig)
    return output_path


def render_historical_tc_tracks(config, output_path: Path) -> Path:
    tracks = load_tc_tracks(config)
    focus = _select_top_intensity(tracks, count=18)
    fig = plt.figure(figsize=(11.2, 8.2))
    ax = fig.add_subplot(111, projection=ccrs.PlateCarree())
    _plot_tc_tracks_single_style(ax, tracks, "#b0b0b0", 0.7, 0.16)
    _plot_tc_tracks_by_category(ax, focus, 1.25, 0.78)
    style_map_axis(ax, config, "Historical Tropical Cyclone Tracks in the West Pacific",
                   bbox=WEST_PACIFIC_BBOX)
    _add_category_legend(ax)
    ax.text(0.02, 0.03,
            f"{tracks.size} historical tracks; {focus.size} representative tracks highlighted",
            transform=ax.transAxes, fontsize=7.8, color="#334e68", ha="left", va="bottom",
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white",
                  "edgecolor": "#e5e7eb", "alpha": 0.82})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight"); plt.close(fig)
    return output_path


def render_combined_exposure_map(config, output_path: Path) -> Path:
    districts = load_district_boundaries(config)
    building = pd.read_parquet(config.BUILDING_SKELETON_PARQUET)
    building = filter_points_to_shanghai(building, "centroid_lon", "centroid_lat", districts)

    # Pre-compute hexbin stats for consistent norm
    fig_tmp, ax_tmp = plt.subplots()
    hb_tmp = ax_tmp.hexbin(
        building["centroid_lon"].to_numpy(float),
        building["centroid_lat"].to_numpy(float),
        C=building["value"].to_numpy(float),
        reduce_C_function=np.sum, gridsize=82, mincnt=1,
    )
    hex_vals = hb_tmp.get_array().data
    plt.close(fig_tmp)
    # Quantile-equalized norm: ~equal number of cells per colour level
    _pcts = np.linspace(0, 100, 51)
    _raw = np.percentile(hex_vals, _pcts)
    _bounds = np.unique(_raw)
    _bounds = _bounds[_bounds >= 1e5]
    if len(_bounds) >= 3:
        norm = BoundaryNorm(_bounds, ncolors=256, clip=True)
    else:
        norm = LogNorm(vmin=max(float(hex_vals.min()), 1e5),
                       vmax=float(hex_vals.max()))

    fig, ax = plt.subplots(figsize=(9.6, 8.6))
    districts.plot(ax=ax, facecolor=plt.colormaps["YlOrRd"](0.0), edgecolor="none", zorder=1)
    hb = ax.hexbin(
        building["centroid_lon"].to_numpy(float),
        building["centroid_lat"].to_numpy(float),
        C=building["value"].to_numpy(float),
        reduce_C_function=np.sum, gridsize=82, mincnt=1,
        cmap="YlOrRd", norm=norm,
        linewidths=0, zorder=2,
    )
    districts.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=0.8, zorder=4)
    annotate_district_labels(ax, districts)
    add_east_china_sea_label(ax)
    add_gov_markers(ax)
    style_map_axis(ax, config, "Combined Building Exposure")
    add_map_legend(ax)
    fig.colorbar(hb, ax=ax, shrink=0.82, pad=0.02).set_label("Building asset exposure (sum, CNY)")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight"); plt.close(fig)
    return output_path


def render_historical_built_up_area(config, output_path: Path) -> Path:
    districts = load_district_boundaries(config)
    built_up_files = _iter_built_up_files(config)
    fig, axes = plt.subplots(2, 5, figsize=(18.5, 10.2), constrained_layout=True)
    for ax, (year, shp_path) in zip(axes.ravel(), built_up_files):
        bu = gpd.read_file(shp_path)[["geometry"]].copy()
        if bu.crs is None:
            bu = bu.set_crs(config.CRS_STANDARD)
        elif bu.crs.to_string() != config.CRS_STANDARD:
            bu = bu.to_crs(config.CRS_STANDARD)
        area_km2 = bu.to_crs("EPSG:32651").geometry.area.sum() / 1e6
        bu.plot(ax=ax, color="#c97b63", alpha=0.75, linewidth=0.0, zorder=2)
        districts.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=0.7, zorder=4)
        annotate_district_labels(ax, districts)
        add_east_china_sea_label(ax)
        add_gov_markers(ax)
        style_map_axis(ax, config, str(year))
        ax.text(120.92, 30.72, f"Built-up area: {area_km2:.0f} km\u00b2",
                fontsize=8, color="#102a43", ha="left", va="bottom", zorder=9,
                bbox={"boxstyle": "round,pad=0.18", "facecolor": "white",
                      "edgecolor": "#d9e2ec", "alpha": 0.9})
    fig.suptitle("Historical Built-up Area in Shanghai", y=1.01)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight"); plt.close(fig)
    return output_path


def render_historical_housing_price(config, output_path: Path) -> Path:
    long = _melt_district_price_table(config)
    city_mean = long.groupby("date", as_index=False)["price_cny_per_sqm"].mean()
    district_band = long.groupby("date")["price_cny_per_sqm"].agg(["min", "max"]).reset_index()
    districts = sorted(long["district"].dropna().unique().tolist(),
                       key=lambda n: DISTRICT_EN_LOOKUP.get(n, n))
    palette = plt.cm.tab20(np.linspace(0, 1, len(districts)))
    imputed_count = int(long.get("price_imputed", pd.Series(dtype=bool)).fillna(False).sum())

    fig, ax = plt.subplots(figsize=(13.8, 6.2))
    ax.fill_between(district_band["date"], district_band["min"], district_band["max"],
                    color="#d9d9d9", alpha=0.45, label="District range")
    ax.plot(city_mean["date"], city_mean["price_cny_per_sqm"],
            color="#7f5539", linewidth=2.8, label="City mean")
    for color, d in zip(palette, districts):
        panel = long[long["district"] == d].sort_values("date")
        ax.plot(panel["date"], panel["price_cny_per_sqm"],
                color=color, linewidth=1.0, alpha=0.9,
                label=DISTRICT_EN_LOOKUP.get(d, d))
    ax.set_title("Historical Housing Price Context by District")
    ax.set_xlabel("Month"); ax.set_ylabel("Second-hand housing price (CNY/m\u00b2)")
    ax.grid(axis="y", color="#d9e2ec", linewidth=0.7, alpha=0.9)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.text(long["date"].min(), float(district_band["max"].max()) * 0.985,
            "Coverage reflects district price table support: 2015-2025 monthly series",
            fontsize=8.5, color="#52606d", ha="left", va="top")
    if imputed_count > 0:
        ax.text(long["date"].min(), float(district_band["max"].max()) * 0.94,
                f"Interior missing months linearly interpolated: {imputed_count}",
                fontsize=8.3, color="#8a1538", ha="left", va="top")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), frameon=False, ncol=4)
    fig.subplots_adjust(bottom=0.22)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight"); plt.close(fig)
    return output_path


def render_historical_population(config, output_path: Path) -> Path:
    district = _load_district_population_series(config)
    districts = (
        district.sort_values(["year", "population_total"])
        .groupby("district", as_index=False).tail(1)
        .sort_values("population_total", ascending=False)["district"].tolist()
    )
    palette = plt.cm.tab20(np.linspace(0, 1, len(districts)))
    years = sorted(district["year"].unique().tolist())
    stacked = np.zeros(len(years), dtype=float)

    fig, ax = plt.subplots(figsize=(14.6, 6.8))
    for color, dn in zip(palette, districts):
        panel = (district[district["district"] == dn]
                 .groupby("year", as_index=False)["population_total"].sum()
                 .sort_values("year"))
        vals = (panel.set_index("year").reindex(years)["population_total"]
                .fillna(0.0).to_numpy(float) / 1e6)
        ax.bar(years, vals, width=0.82, bottom=stacked, color=color,
               edgecolor="white", linewidth=0.25,
               label=DISTRICT_EN_LOOKUP.get(dn, dn))
        stacked += vals
    ax.set_title("Historical Population Composition by District")
    ax.set_xlabel("Year"); ax.set_ylabel("Township-aggregated population (million persons)")
    ax.grid(axis="y", color="#d9e2ec", linewidth=0.7, alpha=0.9)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.set_xticks(years[::2]); ax.margins(x=0.01)
    ax.text(years[0] - 0.35, float(stacked.max()) * 0.99,
            "Stacked bars replace district linework to avoid label crowding.",
            fontsize=8.5, color="#52606d", ha="left", va="top")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), frameon=False, ncol=4)
    fig.subplots_adjust(bottom=0.33)
    fig.text(0.5, 0.015,
             "Source: township annual population table aggregated to district totals.",
             fontsize=8.5, color="#52606d", ha="center")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight"); plt.close(fig)
    return output_path
