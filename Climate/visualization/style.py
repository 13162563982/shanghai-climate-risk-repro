"""Consistent visual style constants for all figures."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

# ── Matplotlib RC defaults ──
BASE_RC_PARAMS = {
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Liberation Sans"],
    "axes.unicode_minus": False,
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.figsize": (10, 6),
}

# ── District label positions (English names + callout arrows) ──
# Coordinates derived from actual shapefile centroids (representative_point()).
# Small central districts use arrows from an external label to the true centroid.
DISTRICT_LABEL_SPECS = {
    "黄浦区": {"label": "Huangpu",   "xy": (121.58, 31.14),  "arrow_to": (121.480, 31.218)},
    "徐汇区": {"label": "Xuhui",     "xy": (121.36, 31.08),  "arrow_to": (121.432, 31.162)},
    "静安区": {"label": "Jing'an",   "xy": (121.38, 31.34),  "arrow_to": (121.451, 31.270)},
    "虹口区": {"label": "Hongkou",   "xy": (121.56, 31.33),  "arrow_to": (121.474, 31.281)},
    "杨浦区": {"label": "Yangpu",    "xy": (121.62, 31.36),  "arrow_to": (121.521, 31.299)},
    "普陀区": {"label": "Putuo",     "xy": (121.395, 31.263)},
    "长宁区": {"label": "Changning", "xy": (121.375, 31.213)},
    "浦东新区": {"label": "Pudong",    "xy": (121.660, 31.180)},
    "宝山区": {"label": "Baoshan",   "xy": (121.414, 31.405)},
    "闵行区": {"label": "Minhang",   "xy": (121.340, 31.080)},
    "嘉定区": {"label": "Jiading",   "xy": (121.218, 31.364)},
    "青浦区": {"label": "Qingpu",    "xy": (121.080, 31.118)},
    "松江区": {"label": "Songjiang", "xy": (121.180, 31.030)},
    "奉贤区": {"label": "Fengxian",  "xy": (121.567, 30.888)},
    "金山区": {"label": "Jinshan",   "xy": (121.230, 30.816)},
    "崇明区": {"label": "Chongming", "xy": (121.450, 31.660)},
}

# Chinese district name → English label
DISTRICT_EN_LOOKUP = {d: s["label"] for d, s in DISTRICT_LABEL_SPECS.items()}

# ── Building category system ──
PRIMARY_BUILDING_CATEGORIES = ("A_old", "A_new", "B_old", "B_new", "C", "D")

BUILDING_CATEGORY_COLLAPSE = {
    "A_old": "A_old", "A_new": "A_new",
    "B_old": "B_old", "B_new": "B_new",
    "C": "C", "D": "D",
    "A_unknown_age": "A_old", "B_unknown_age": "B_old",
    "unknown": "D",
}

BUILDING_CATEGORY_LABELS = {
    "A_old": "Old low-rise residential",
    "A_new": "New low-rise residential",
    "B_old": "Old mid/high-rise residential",
    "B_new": "New mid/high-rise residential",
    "C": "Super high-rise residential",
    "D": "Commercial and public buildings",
    "A_unknown_age": "Low-rise residential (age unknown)",
    "B_unknown_age": "Mid/high-rise residential (age unknown)",
    "unknown": "Other or unknown",
}
