"""Map rendering utilities: district boundaries, hexbin grids, axis styling."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, Tuple

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from climate_functions import load_raster_clip_shanghai
from .style import DISTRICT_LABEL_SPECS


# ═══════════════════════════════════════════════════════════════════════
# District boundaries
# ═══════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=4)
def _load_district_boundaries_cached(
    admin_boundary_shp: str,
    shanghai_bbox: tuple[float, float, float, float],
    crs_standard: str,
    rename_items: tuple[tuple[str, str], ...],
):
    admin_raw = gpd.read_file(admin_boundary_shp, bbox=shanghai_bbox)
    if admin_raw.empty:
        admin_raw = gpd.read_file(admin_boundary_shp)

    rename_map = dict(rename_items)
    shanghai_admin = admin_raw[admin_raw["市"] == "上海市"].copy()
    shanghai_admin["district_std"] = shanghai_admin["县"].replace(rename_map)
    district_boundaries = shanghai_admin.dissolve(by="district_std", as_index=False)
    district_boundaries = district_boundaries[["district_std", "geometry"]]
    if district_boundaries.crs is None:
        district_boundaries = district_boundaries.set_crs(crs_standard)
    elif district_boundaries.crs.to_string() != crs_standard:
        district_boundaries = district_boundaries.to_crs(crs_standard)
    return district_boundaries


def load_district_boundaries(config):
    rename_items = tuple(sorted(getattr(config, "ADMIN_DISTRICT_RENAME", {}).items()))
    return _load_district_boundaries_cached(
        str(config.ADMIN_BOUNDARY_SHP),
        tuple(config.SHANGHAI_BBOX),
        config.CRS_STANDARD,
        rename_items,
    ).copy()


# ═══════════════════════════════════════════════════════════════════════
# Point filtering
# ═══════════════════════════════════════════════════════════════════════

def filter_points_to_shanghai(
    frame: pd.DataFrame, lon_col: str, lat_col: str, district_boundaries,
) -> pd.DataFrame:
    points = gpd.GeoDataFrame(
        frame.copy(),
        geometry=gpd.points_from_xy(frame[lon_col], frame[lat_col]),
        crs=district_boundaries.crs,
    )
    mask = points.within(district_boundaries.unary_union)
    return frame.loc[mask.to_numpy()].copy()


# ═══════════════════════════════════════════════════════════════════════
# Grid aggregation
# ═══════════════════════════════════════════════════════════════════════

def aggregate_points_to_masked_grid(
    frame: pd.DataFrame,
    lon_col: str,
    lat_col: str,
    value_col: str,
    district_boundaries,
    bbox,
    nx: int,
    ny: int | None = None,
):
    xmin, ymin, xmax, ymax = bbox
    if ny is None:
        x_span = max(xmax - xmin, 1e-9)
        y_span = max(ymax - ymin, 1e-9)
        ny = max(1, int(round(nx * y_span / x_span)))

    x_edges = np.linspace(xmin, xmax, nx + 1)
    y_edges = np.linspace(ymin, ymax, ny + 1)
    x_index = np.searchsorted(x_edges, frame[lon_col].to_numpy(dtype=float), side="right") - 1
    y_index = np.searchsorted(y_edges, frame[lat_col].to_numpy(dtype=float), side="right") - 1
    valid = (x_index >= 0) & (x_index < nx) & (y_index >= 0) & (y_index < ny)

    grid = np.full((ny, nx), np.nan, dtype=float)
    if np.any(valid):
        grouped = (
            pd.DataFrame({
                "x_index": x_index[valid],
                "y_index": y_index[valid],
                "value": frame.loc[valid, value_col].to_numpy(dtype=float),
            })
            .groupby(["y_index", "x_index"], sort=False)["value"]
            .sum()
        )
        for (y_cell, x_cell), cell_value in grouped.items():
            grid[int(y_cell), int(x_cell)] = float(cell_value)

    x_centers = (x_edges[:-1] + x_edges[1:]) / 2.0
    y_centers = (y_edges[:-1] + y_edges[1:]) / 2.0
    center_x, center_y = np.meshgrid(x_centers, y_centers)
    center_points = gpd.GeoSeries(
        gpd.points_from_xy(center_x.ravel(), center_y.ravel()),
        crs=district_boundaries.crs,
    )
    center_mask = center_points.within(district_boundaries.unary_union).to_numpy().reshape((ny, nx))
    grid[~center_mask] = np.nan
    return x_edges, y_edges, np.ma.masked_invalid(grid)


# ═══════════════════════════════════════════════════════════════════════
# Professional map style constants (aligned with V5 reference)
# ═══════════════════════════════════════════════════════════════════════

_FONT = "DejaVu Sans"

_GOV_LOCATIONS: Dict[str, Tuple[float, float]] = {
    "市政府": (121.4737, 31.2304),
    "黄浦": (121.4903, 31.2293),
    "徐汇": (121.4370, 31.1883),
    "长宁": (121.4247, 31.2204),
    "静安": (121.4478, 31.2281),
    "普陀": (121.3953, 31.2495),
    "虹口": (121.5054, 31.2644),
    "杨浦": (121.5260, 31.2596),
    "闵行": (121.3813, 31.1118),
    "宝山": (121.4896, 31.4044),
    "嘉定": (121.2653, 31.3748),
    "浦东": (121.5447, 31.2214),
    "金山": (121.3416, 30.7417),
    "松江": (121.2274, 31.0327),
    "青浦": (121.1241, 31.1496),
    "奉贤": (121.4743, 30.9178),
    "崇明": (121.3973, 31.6228),
}

_WATER_LABELS: Dict[str, Tuple[float, float]] = {
    "East China Sea": (121.90, 30.88),
    "Hangzhou Bay": (121.25, 30.68),
    "Yangtze Estuary": (121.75, 31.75),
}

# Small central districts use smaller fontsize
_LABEL_FONTSIZE_FACTOR: Dict[str, float] = {
    "黄浦区": 0.7, "静安区": 0.7, "虹口区": 0.7, "杨浦区": 0.7,
    "长宁区": 0.7, "普陀区": 0.7, "徐汇区": 0.7,
}


# ═══════════════════════════════════════════════════════════════════════
# Axis styling
# ═══════════════════════════════════════════════════════════════════════

def style_map_axis(ax, config, title, bbox=None):
    bbox = config.SHANGHAI_BBOX if bbox is None else bbox
    if hasattr(ax, "set_extent"):
        # Cartopy GeoAxes (track maps covering West Pacific)
        ax.set_extent((bbox[0], bbox[2], bbox[1], bbox[3]), crs=ccrs.PlateCarree())
        ax.add_feature(cfeature.OCEAN, facecolor="#e8f0fe", edgecolor="none", zorder=0)
        ax.add_feature(cfeature.LAND, facecolor="#f5f5f0", edgecolor="none", zorder=0)
        ax.coastlines(resolution="50m", color="#666666", linewidth=0.6, zorder=1)
        gl = ax.gridlines(draw_labels=True, linewidth=0.3, color="#cccccc",
                          alpha=0.7, linestyle="--")
        gl.top_labels = False
        gl.right_labels = False
        gl.xlabel_style = {"size": 8, "color": "#333333"}
        gl.ylabel_style = {"size": 8, "color": "#333333"}
        ax.set_title(title, fontsize=13, fontweight="normal", pad=10, fontfamily=_FONT)
    else:
        # Standard matplotlib axes (Shanghai detail maps)
        ax.set_xlim(bbox[0], bbox[2])
        ax.set_ylim(bbox[1], bbox[3])
        ax.set_aspect("equal")
        ax.set_facecolor("#e8e8e8")
        ax.set_title(title, fontsize=13, fontweight="normal", pad=10, fontfamily=_FONT)
        ax.set_xlabel("Longitude (°E)", fontsize=10, fontfamily=_FONT)
        ax.set_ylabel("Latitude (°N)", fontsize=10, fontfamily=_FONT)
        ax.tick_params(labelsize=9)


# ═══════════════════════════════════════════════════════════════════════
# District label annotation
# ═══════════════════════════════════════════════════════════════════════

def annotate_district_labels(ax, district_boundaries, fontsize=8.5):
    for row in district_boundaries.itertuples(index=False):
        district_name = str(row.district_std)
        spec = DISTRICT_LABEL_SPECS.get(district_name)
        fs = fontsize * _LABEL_FONTSIZE_FACTOR.get(district_name, 1.0)
        if spec is None:
            rp = row.geometry.representative_point()
            ax.annotate(district_name, xy=(rp.x, rp.y), ha="center", va="center",
                        fontsize=fs, color="#222222", fontfamily=_FONT, zorder=8)
            continue
        label = spec["label"]
        arrow_to = spec.get("arrow_to")
        if arrow_to is not None:
            ax.annotate(
                label, xy=arrow_to, xytext=spec["xy"],
                fontsize=fs, ha="center", va="center", color="#222222",
                fontfamily=_FONT, zorder=9,
                arrowprops={"arrowstyle": "-", "color": "#555555", "lw": 0.6},
            )
        else:
            ax.annotate(
                label, xy=spec["xy"], ha="center", va="center",
                fontsize=fs, color="#222222", fontfamily=_FONT, zorder=9,
            )


def add_water_labels(ax, fontsize=7):
    """Label surrounding water bodies (Yangtze Estuary, Yellow Sea, etc.)."""
    for wname, (wx, wy) in _WATER_LABELS.items():
        ax.annotate(
            wname, xy=(wx, wy), ha="center", va="center",
            fontsize=fontsize, fontstyle="italic", color="#1565C0",
            fontweight="normal", alpha=0.85, zorder=8, fontfamily=_FONT,
        )


def add_gov_markers(ax, show_district_gov=True, city_fontsize=7, dist_fontsize=5):
    """Mark Shanghai City Gov (★) and District Gov (●) locations."""
    cx, cy = _GOV_LOCATIONS["市政府"]
    ax.plot(cx, cy, marker="*", color="red", markersize=10, zorder=10,
            markeredgecolor="black", markeredgewidth=0.3)
    ax.annotate("City Gov.", xy=(cx, cy), xytext=(cx + 0.02, cy + 0.025),
                fontsize=city_fontsize, color="red", fontweight="normal",
                zorder=10, fontfamily=_FONT)
    if show_district_gov:
        for name, (gx, gy) in _GOV_LOCATIONS.items():
            if name == "市政府":
                continue
            ax.plot(gx, gy, marker="o", color="#D32F2F", markersize=3.5, zorder=9,
                    markeredgecolor="black", markeredgewidth=0.2)


def add_map_legend(ax, compact=False):
    """Add legend: City Gov (★), District Gov (●), District Boundary (—)."""
    fs = 6 if compact else 8
    handles = [
        Line2D([0], [0], marker="*", color="w", markerfacecolor="red",
               markeredgecolor="black", markersize=9, label="Shanghai City Gov."),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#D32F2F",
               markeredgecolor="black", markersize=5, label="District Gov."),
        Line2D([0], [0], color="black", linewidth=0.9, label="District Boundary"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=fs,
              framealpha=0.7, edgecolor="gray", fancybox=False,
              handletextpad=0.4, borderpad=0.3, prop={"family": _FONT})


def add_east_china_sea_label(ax, bbox=None):
    """Backward-compatible alias — now calls add_water_labels for all water bodies."""
    add_water_labels(ax)
