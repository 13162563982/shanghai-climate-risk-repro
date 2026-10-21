"""
Generate vulnerability sensitivity analysis figures:
  1. TC impact function family under V_HALF_BASE_SCALE variation
  2. SS depth-damage family under SURGE_MDR_CALIBRATION_SCALE variation
  3. TC impact function family under V_THRESH variation
  4. Combined panel: TC + SS sensitivity overview
"""
import argparse
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.colors import to_rgb

# ── Configuration ────────────────────────────────────────────────────
# Emanuel sigmoid: MDR(v) = v^3 / (1 + v^3), where v = max(0, V - V_thresh) / (V_half - V_thresh)
V_HALF_WP3_BASE = 112.8  # m/s, WP3 reference
V_THRESH_BASE = 25.7     # m/s

V_HALF_ADJ = {"A_old": 0.80, "A_new": 0.90, "B_old": 0.95,
              "B_new": 1.00, "C": 1.05, "D": 1.10}

SURGE_DEPTH_DAMAGE = {
    "low_rise":   {"depths": [0.0, 0.3, 0.6, 1.2, 1.8, 2.4, 3.0],
                   "mdr":    [0.00, 0.08, 0.15, 0.30, 0.42, 0.50, 0.55]},
    "mid_rise":   {"depths": [0.0, 0.3, 0.6, 1.2, 1.8, 2.4, 3.0],
                   "mdr":    [0.00, 0.04, 0.08, 0.18, 0.25, 0.30, 0.35]},
    "high_rise":  {"depths": [0.0, 0.3, 0.6, 1.2, 1.8, 2.4, 3.0],
                   "mdr":    [0.00, 0.02, 0.04, 0.10, 0.15, 0.18, 0.22]},
    "commercial": {"depths": [0.0, 0.3, 0.6, 1.2, 1.8, 2.4, 3.0],
                   "mdr":    [0.00, 0.05, 0.10, 0.22, 0.32, 0.38, 0.42]},
}

# Sweep values
SURGE_SCALES = [0.10, 0.14, 0.176, 0.22, 0.30]
TC_BASE_SCALES = [0.95, 0.975, 1.0, 1.025, 1.05]
TC_THRESHOLDS = [23.0, 24.5, 25.7, 27.0, 28.5]

# Output directory. Resolved from the package root (parent of tools/) so the
# script is location-independent; overridable with --out.
_NEWROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ap = argparse.ArgumentParser(description="Generate vulnerability sensitivity figures sa_01-sa_04")
_ap.add_argument("--out", default=os.path.join(_NEWROOT, "manuscript", "figures"),
                 help="output directory for sa_01..sa_04 (default: <NEWROOT>/manuscript/figures)")
_args, _unknown = _ap.parse_known_args()
OUT_DIR = _args.out
os.makedirs(OUT_DIR, exist_ok=True)
WIND_MAX = 320
WIND_TICKS = np.arange(0, WIND_MAX + 1, 40)
SS_CLASS_COLORS = {
    "low_rise": "#e76f51",
    "mid_rise": "#f4a261",
    "high_rise": "#264653",
    "commercial": "#2a9d8f",
}


def emanuel_mdr(wind, v_thresh, v_half):
    """Emanuel sigmoid MDR curve."""
    v = np.maximum(0, wind - v_thresh) / (v_half - v_thresh)
    return v**3 / (1 + v**3)


def extend_surge_curve(depths_ref, mdr_ref):
    """Extend surge curve to 10m with exponential saturation."""
    depths = list(depths_ref)
    mdr = list(mdr_ref)
    mdr_max = mdr[-1]
    for extra_d in [4.0, 5.0, 6.0, 8.0, 10.0]:
        if extra_d > depths[-1]:
            gap = extra_d - depths[-1]
            sat = mdr_max + (1.0 - mdr_max) * (1 - np.exp(-0.3 * gap))
            depths.append(extra_d)
            mdr.append(sat)
    return np.array(depths), np.array(mdr)


def _marker_edge_color(color):
    """Keep markers visible for both dark and pale palette colors."""
    r, g, b = to_rgb(color)
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#4d4d4d" if luminance > 0.72 else "white"


def add_ss_key_markers(ax, depths, mdr, color, size=26):
    """Match Figure 6 style: show key depth-damage control points."""
    ax.scatter(depths, mdr, s=size, color=color, zorder=5,
               edgecolors=_marker_edge_color(color), linewidths=0.65)


# ── Style config ─────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "legend.fontsize": 9,
    "figure.dpi": 300,
})

BASELINE_COLOR = "#2166AC"
SWEEP_CMAP = plt.cm.RdYlBu_r  # warm=high, cool=low
CAT_COLORS = {"A_old": "#d73027", "A_new": "#f46d43", "B_old": "#fdae61",
              "B_new": "#fee090", "C": "#abd9e9", "D": "#4575b4"}


def _sweep_colors(n):
    """Return n colors from diverging colormap, centered at midpoint."""
    return [SWEEP_CMAP(i / (n - 1)) for i in range(n)]


# ═══════════════════════════════════════════════════════════════════════
# Figure 1: TC Impact Function Sensitivity — V_HALF_BASE_SCALE
# ═══════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), sharey=True)
wind = np.linspace(0, WIND_MAX, 1200)
colors = _sweep_colors(len(TC_BASE_SCALES))

# Panel (a): A_old category (most vulnerable)
ax = axes[0]
cat = "A_old"
adj = V_HALF_ADJ[cat]
for i, scale in enumerate(TC_BASE_SCALES):
    v_half = V_HALF_WP3_BASE * adj * scale
    mdr = emanuel_mdr(wind, V_THRESH_BASE, v_half)
    lw = 2.5 if scale == 1.0 else 1.3
    ls = "-" if scale == 1.0 else "--"
    ax.plot(wind, mdr, color=colors[i], linewidth=lw, linestyle=ls,
            label=f"scale={scale:.3f} ($V_{{half}}$={v_half:.1f})")
ax.set_xlabel("Wind speed (m/s)")
ax.set_ylabel("Mean Damage Ratio (MDR)")
ax.set_title(f"(a) {cat}: pre-2002 low-rise")
ax.legend(loc="upper left", framealpha=0.9)
ax.set_xlim(0, WIND_MAX)
ax.set_xticks(WIND_TICKS)
ax.set_ylim(0, 1.0)
ax.grid(True, alpha=0.3)
ax.axvline(V_THRESH_BASE, color="gray", ls=":", lw=0.8, alpha=0.5)
ax.text(V_THRESH_BASE + 1, 0.95, f"$V_{{thresh}}$={V_THRESH_BASE}", fontsize=8, color="gray")

# Panel (b): C category (least vulnerable residential)
ax = axes[1]
cat = "C"
adj = V_HALF_ADJ[cat]
for i, scale in enumerate(TC_BASE_SCALES):
    v_half = V_HALF_WP3_BASE * adj * scale
    mdr = emanuel_mdr(wind, V_THRESH_BASE, v_half)
    lw = 2.5 if scale == 1.0 else 1.3
    ls = "-" if scale == 1.0 else "--"
    ax.plot(wind, mdr, color=colors[i], linewidth=lw, linestyle=ls,
            label=f"scale={scale:.3f} ($V_{{half}}$={v_half:.1f})")
ax.set_xlabel("Wind speed (m/s)")
ax.set_title(f"(b) C: high-rise")
ax.legend(loc="upper left", framealpha=0.9)
ax.set_xlim(0, WIND_MAX)
ax.set_xticks(WIND_TICKS)
ax.grid(True, alpha=0.3)
ax.axvline(V_THRESH_BASE, color="gray", ls=":", lw=0.8, alpha=0.5)

fig.suptitle("TC Wind Vulnerability Sensitivity: $V_{half}$ Base Scale Variation", fontsize=13, y=1.01)
plt.tight_layout()
fig.savefig(f"{OUT_DIR}/sa_01_tc_vhalf_sensitivity.png", bbox_inches="tight", dpi=300)
plt.close()
print("  [OK] sa_01_tc_vhalf_sensitivity.png")


# ═══════════════════════════════════════════════════════════════════════
# Figure 2: TC Impact Function Sensitivity — V_THRESH variation
# ═══════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), sharey=True)
colors_vt = _sweep_colors(len(TC_THRESHOLDS))

for panel, (cat, ax) in enumerate(zip(["A_old", "C"], axes)):
    adj = V_HALF_ADJ[cat]
    v_half = V_HALF_WP3_BASE * adj
    for i, vt in enumerate(TC_THRESHOLDS):
        mdr = emanuel_mdr(wind, vt, v_half)
        lw = 2.5 if vt == 25.7 else 1.3
        ls = "-" if vt == 25.7 else "--"
        ax.plot(wind, mdr, color=colors_vt[i], linewidth=lw, linestyle=ls,
                label=f"$V_{{thresh}}$={vt:.1f} m/s")
    ax.set_xlabel("Wind speed (m/s)")
    if panel == 0:
        ax.set_ylabel("Mean Damage Ratio (MDR)")
    title_label = "pre-2002 low-rise" if cat == "A_old" else "high-rise"
    ax.set_title(f"({'a' if panel==0 else 'b'}) {cat}: {title_label}")
    ax.legend(loc="upper left", framealpha=0.9)
    ax.set_xlim(0, WIND_MAX)
    ax.set_xticks(WIND_TICKS)
    ax.set_ylim(0, 1.0)
    ax.grid(True, alpha=0.3)

fig.suptitle("TC Wind Vulnerability Sensitivity: Damage Onset Threshold $V_{thresh}$ Variation",
             fontsize=13, y=1.01)
plt.tight_layout()
fig.savefig(f"{OUT_DIR}/sa_02_tc_vthresh_sensitivity.png", bbox_inches="tight", dpi=300)
plt.close()
print("  [OK] sa_02_tc_vthresh_sensitivity.png")


# ═══════════════════════════════════════════════════════════════════════
# Figure 3: SS Depth-Damage Sensitivity — SURGE_MDR_CALIBRATION_SCALE
# ═══════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, 2, figsize=(13, 10), sharex=True, sharey=True)
colors_ss = _sweep_colors(len(SURGE_SCALES))
panel_labels = ["(a)", "(b)", "(c)", "(d)"]

for idx, (surge_class, params) in enumerate(SURGE_DEPTH_DAMAGE.items()):
    ax = axes.flat[idx]
    depths_ext, mdr_raw_ext = extend_surge_curve(params["depths"], params["mdr"])
    curve_series = []

    for i, scale in enumerate(SURGE_SCALES):
        mdr_cal = mdr_raw_ext * scale
        lw = 2.5 if scale == 0.176 else 1.3
        ls = "-" if scale == 0.176 else "--"
        ax.plot(depths_ext, mdr_cal, color=colors_ss[i], linewidth=lw, linestyle=ls,
                label=f"scale={scale:.3f}")
        curve_series.append((colors_ss[i], mdr_cal))
    for color, mdr_cal in curve_series:
        add_ss_key_markers(ax, depths_ext, mdr_cal, color, size=28)
    ax.set_title(f"{panel_labels[idx]} {surge_class}")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 0.25)
    ax.grid(True, alpha=0.3)
    if idx >= 2:
        ax.set_xlabel("Inundation depth (m)")
    if idx % 2 == 0:
        ax.set_ylabel("Calibrated MDR")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)

fig.suptitle("Storm Surge Depth-Damage Sensitivity: MDR Calibration Scale Variation", fontsize=13, y=1.01)
plt.tight_layout()
fig.savefig(f"{OUT_DIR}/sa_03_ss_mdr_sensitivity.png", bbox_inches="tight", dpi=300)
plt.close()
print("  [OK] sa_03_ss_mdr_sensitivity.png")


# ═══════════════════════════════════════════════════════════════════════
# Figure 4: Combined overview — All 6 TC categories at baseline + band
# ═══════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

# Panel (a): All 6 TC categories at baseline
ax = axes[0]
for cat, adj in V_HALF_ADJ.items():
    v_half = V_HALF_WP3_BASE * adj
    mdr = emanuel_mdr(wind, V_THRESH_BASE, v_half)
    ax.plot(wind, mdr, color=CAT_COLORS[cat], linewidth=1.8, label=f"{cat} ($V_{{half}}$={v_half:.1f})")
ax.set_xlabel("Wind speed (m/s)")
ax.set_ylabel("Mean Damage Ratio (MDR)")
ax.set_title("(a) TC: all categories at baseline scale")
ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
ax.set_xlim(0, WIND_MAX)
ax.set_xticks(WIND_TICKS)
ax.set_ylim(0, 1.0)
ax.grid(True, alpha=0.3)

# Panel (b): All 4 surge classes at baseline + band from scale variation
ax = axes[1]
y_hi_max = 0.0
for surge_class, params in SURGE_DEPTH_DAMAGE.items():
    depths_ext, mdr_raw_ext = extend_surge_curve(params["depths"], params["mdr"])
    color = SS_CLASS_COLORS[surge_class]
    # Baseline
    mdr_baseline = mdr_raw_ext * 0.176
    ax.plot(depths_ext, mdr_baseline, color=color, linewidth=1.8,
            label=f"{surge_class} (x0.176)")
    add_ss_key_markers(ax, depths_ext, mdr_baseline, color)
    # Band from min/max scale
    mdr_lo = mdr_raw_ext * min(SURGE_SCALES)
    mdr_hi = mdr_raw_ext * max(SURGE_SCALES)
    y_hi_max = max(y_hi_max, float(mdr_hi.max()))
    ax.fill_between(depths_ext, mdr_lo, mdr_hi, color=color, alpha=0.15)

ax.set_xlabel("Inundation depth (m)")
ax.set_ylabel("Calibrated MDR")
ax.set_title("(b) SS: all classes at baseline, bands show scale range [0.10, 0.30]")
ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
ax.set_xlim(0, 10)
ax.set_ylim(0, max(0.24, y_hi_max * 1.05))
ax.grid(True, alpha=0.3)

fig.suptitle("Vulnerability Function Overview: Baseline Curves and Sensitivity Ranges", fontsize=13, y=1.01)
plt.tight_layout()
fig.savefig(f"{OUT_DIR}/sa_04_vulnerability_overview.png", bbox_inches="tight", dpi=300)
plt.close()
print("  [OK] sa_04_vulnerability_overview.png")

print("\nAll sensitivity figures generated successfully.")
