"""Building-type spatial distribution renderer (bf_10)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from .maps import (
    add_east_china_sea_label,
    add_gov_markers,
    annotate_district_labels,
    filter_points_to_shanghai,
    load_district_boundaries,
    style_map_axis,
)
from .style import (
    BUILDING_CATEGORY_COLLAPSE,
    BUILDING_CATEGORY_LABELS,
    PRIMARY_BUILDING_CATEGORIES,
)

BUILDING_CATEGORY_COLORS = {
    "A_old": "#7f5539", "A_new": "#ddb892",
    "B_old": "#386641", "B_new": "#6a994e",
    "C": "#3d5a80", "D": "#bc4749",
    "A_unknown_age": "#8d99ae", "B_unknown_age": "#adb5bd",
    "unknown": "#ced4da",
}


def render_building_type_distribution(config, output_path: Path) -> Path:
    districts = load_district_boundaries(config)
    building = pd.read_parquet(config.BUILDING_SKELETON_PARQUET)
    building = filter_points_to_shanghai(building, "centroid_lon", "centroid_lat", districts)
    building["building_category_display"] = (
        building["building_category"].map(BUILDING_CATEGORY_COLLAPSE).fillna("D")
    )
    fig, axes = plt.subplots(2, 3, figsize=(15.2, 11.0), constrained_layout=True)
    fig.get_layout_engine().set(rect=[0, 0, 1, 0.95])
    for ax, category in zip(axes.ravel(), PRIMARY_BUILDING_CATEGORIES):
        cat_df = building[building["building_category_display"] == category]
        if len(cat_df) > 25000:
            cat_df = cat_df.sample(n=25000, random_state=42)
        districts.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=0.8, zorder=3)
        if not cat_df.empty:
            ax.scatter(
                cat_df["centroid_lon"], cat_df["centroid_lat"],
                s=4, alpha=0.6, linewidths=0,
                color=BUILDING_CATEGORY_COLORS.get(category, "#ced4da"),
                zorder=2,
            )
        annotate_district_labels(ax, districts)
        add_east_china_sea_label(ax)
        add_gov_markers(ax)
        style_map_axis(ax, config, BUILDING_CATEGORY_LABELS.get(category, category))
    fig.suptitle("Building Type Distribution in Shanghai", y=0.98, fontsize=15)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path
