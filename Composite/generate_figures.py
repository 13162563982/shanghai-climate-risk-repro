# === generate_figures.py ===
# Shanghai CFCI Composite Index — Visualization
#
# Figures:
#   cf_01  CFCI Main Index (historical + projection, 3 scenarios)
#   cf_02  Triple Index Comparison (CRI, FRI, CFCI side by side)
#   cf_03  CFCI Decomposition (CRI vs FRI contribution)

import importlib.util
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

# ── Load config ──────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "config", SCRIPT_DIR / "00_config.py")
config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config)

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "axes.unicode_minus": False,
    "figure.dpi": 100,
    "savefig.dpi": 300,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "-",
})

FIGURES_DIR = config.FIGURES_DIR

# ── Colors ───────────────────────────────────────────────────────────
C_CFCI  = "#6A1B9A"  # purple — composite
C_CRI   = "#D35400"  # orange — climate
C_FRI   = "#1565C0"  # blue   — finance
C_FILL  = "#E8DAEF"  # light purple
C_GRID  = "#ECF0F1"
C_HIST  = "#7B1FA2"  # darker purple for baseline projection
C_SSP245 = "#2E7D32"
C_SSP585 = "#C62828"


def _save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", dpi=300)
    plt.close(fig)
    print(f"  [OK] {path.name}")


# ═══════════════════════════════════════════════════════════════════════
# Figure 1: CFCI Main Index with Projection
# ═══════════════════════════════════════════════════════════════════════

def render_cfci_index():
    """Main CFCI chart: historical + projection with 3 scenarios (2-panel)."""
    hist = pd.read_csv(config.CFCI_HISTORICAL_CSV)
    hist["date"] = pd.to_datetime(hist["date"])

    proj = pd.read_csv(config.CFCI_PROJECTION_CSV)
    proj["date"] = pd.to_datetime(proj["date"])

    scenario_styles = {
        "Historical Baseline": {"color": C_HIST,   "ls": "--", "lw": 2.2,
                                "fill": "#D1C4E9", "label": "Historical Baseline"},
        "SSP2-4.5":            {"color": C_SSP245, "ls": "-.", "lw": 2.2,
                                "fill": "#C8E6C9", "label": "SSP2-4.5"},
        "SSP5-8.5":            {"color": C_SSP585, "ls": "-",  "lw": 2.2,
                                "fill": "#FFCDD2", "label": "SSP5-8.5"},
    }

    last_hist_date = hist["date"].max()
    last_cfci = hist["cfci"].iloc[-1]

    # ── Two-panel figure ─────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(22, 8),
                                   gridspec_kw={"width_ratios": [1.15, 1],
                                                "wspace": 0.18})

    # ── Helper: draw historical portion ──────────────────────────────
    def _draw_hist(ax):
        ax.fill_between(hist["date"], 0, hist["cfci"],
                        color=C_FILL, alpha=0.4, zorder=0)
        ax.plot(hist["date"], hist["cfci"],
                color=C_CFCI, linewidth=2.8, zorder=4,
                label="CCHI (historical)")

    # ── Helper: style an axis ────────────────────────────────────────
    def _style_ax(ax, ylabel=True):
        if ylabel:
            ax.set_ylabel("CCHI Level (Base 100)", fontsize=13, fontweight="bold")
        ax.set_xlabel("Date", fontsize=12)
        ax.grid(True, alpha=0.3, linestyle="-", color=C_GRID, zorder=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.xaxis.set_major_locator(mdates.YearLocator(5))
        ax.xaxis.set_minor_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    x_end = proj["date"].max()
    y_max = max(hist["cfci"].max(),
                proj["cfci_p90"].max() if "cfci_p90" in proj.columns else 0)

    # ══════════════════════════════════════════════════════════════════
    # Panel A (left): Scenario Comparison — p50 median lines
    # ══════════════════════════════════════════════════════════════════
    _draw_hist(ax1)

    ax1.annotate(f"{hist['cfci'].iloc[0]:.0f}",
                 xy=(hist["date"].iloc[0], hist["cfci"].iloc[0]),
                 fontsize=9, fontweight="bold", color=C_CFCI,
                 xytext=(-30, 10), textcoords="offset points")

    ax1.axvline(last_hist_date, color="#95A5A6", linewidth=0.8,
                linestyle=":", alpha=0.6, zorder=2)

    end_vals_a = []  # collect for anti-overlap
    for scenario, style in scenario_styles.items():
        s_data = proj[proj["scenario"] == scenario].copy()
        if s_data.empty:
            continue

        dates_plot = pd.DatetimeIndex([last_hist_date] + s_data["date"].tolist())

        if "cfci_p10" in s_data.columns:
            vals_p10 = np.concatenate([[last_cfci], s_data["cfci_p10"].values])
            vals_p90 = np.concatenate([[last_cfci], s_data["cfci_p90"].values])
            ax1.fill_between(dates_plot, vals_p10, vals_p90,
                             color=style["fill"], alpha=0.22, zorder=1)

        # Use p50 (median) for monotonic main line
        vals_main = np.concatenate([[last_cfci], s_data["cfci_p50"].values])
        ax1.plot(dates_plot, vals_main,
                 color=style["color"], linewidth=style["lw"],
                 linestyle=style["ls"], label=style["label"], zorder=4)

        end_val = s_data["cfci_p50"].iloc[-1]
        end_date = s_data["date"].iloc[-1]
        end_vals_a.append((end_val, end_date, style["color"]))

    # Anti-overlap annotations for Panel A
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

    ax1.legend(fontsize=8.5, loc="upper left", framealpha=0.9,
               edgecolor="#D5DBDB", fancybox=True, ncol=2)
    _style_ax(ax1)

    ax1.set_xlim(hist["date"].min(), x_end + pd.Timedelta(days=180))
    ax1.set_ylim(0, y_max * 1.12)

    ax1.set_title("A. Scenario Comparison (Median Projections)",
                  fontsize=12, fontweight="bold", pad=8)

    # ══════════════════════════════════════════════════════════════════
    # Panel B (right): Representative Pathways — all 3 scenarios
    # ══════════════════════════════════════════════════════════════════
    _draw_hist(ax2)

    ax2.axvline(last_hist_date, color="#95A5A6", linewidth=0.8,
                linestyle=":", alpha=0.6, zorder=2)

    end_vals = []  # collect (end_val, end_date, color) for anti-overlap
    for scenario, style in scenario_styles.items():
        s_data = proj[proj["scenario"] == scenario].copy()
        if s_data.empty:
            continue

        dates_plot = pd.DatetimeIndex([last_hist_date] + s_data["date"].tolist())

        # Representative characteristic path
        vals_rep = np.concatenate([[last_cfci], s_data["cfci_rep"].values])
        ax2.plot(dates_plot, vals_rep,
                 color=style["color"], linewidth=2.2,
                 linestyle=style["ls"], label=style["label"],
                 zorder=4)

        end_val = s_data["cfci_rep"].iloc[-1]
        end_date = s_data["date"].iloc[-1]
        end_vals.append((end_val, end_date, style["color"]))

    # Anti-overlap annotation: sort by value, nudge if too close
    end_vals.sort(key=lambda x: x[0])
    min_gap = y_max * 0.04
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

    ax2.set_xlim(hist["date"].min(), x_end + pd.Timedelta(days=180))
    ax2.set_ylim(0, y_max * 1.12)

    ax2.set_title("B. Representative Pathways (Characteristic MC Paths)",
                  fontsize=12, fontweight="bold", pad=8)

    # ── Suptitle & footnote ──────────────────────────────────────────
    fig.suptitle("Composite Climate-Housing Index",
                 fontsize=16, fontweight="bold", y=0.98)
    fig.text(0.5, 0.01,
             "CCHI = \u221a(CRI \u00d7 HSI)  |  Geometric mean, parameter-free  |  "
             "Line: Characteristic MC path  |  Bands: 10th\u201390th percentile (Iman-Conover)",
             fontsize=7.5, color="#7F8C8D", ha="center", va="bottom",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                       edgecolor="#E5E7EB", alpha=0.9))

    _save(fig, FIGURES_DIR / "cf_01_composite_index.png")


# ═══════════════════════════════════════════════════════════════════════
# Figure 2: Triple Index Comparison
# ═══════════════════════════════════════════════════════════════════════

def render_triple_comparison():
    """CRI, FRI, CFCI on same axes for comparison."""
    hist = pd.read_csv(config.CFCI_HISTORICAL_CSV)
    hist["date"] = pd.to_datetime(hist["date"])

    # Also load full CRI for longer history
    cri_full = pd.read_csv(config.CRI_HISTORICAL_CSV)
    cri_full["date"] = pd.to_datetime(cri_full["date"])
    cri_full = cri_full[["date", "cri_index"]].dropna()

    fig, ax = plt.subplots(figsize=(16, 7))

    # Full CRI (extends before FRI starts)
    ax.plot(cri_full["date"], cri_full["cri_index"],
            color=C_CRI, linewidth=2.0, alpha=0.7, zorder=3,
            label="CRI (Climate)")

    # FRI (shorter period)
    fri_full = pd.read_csv(config.FRI_HISTORICAL_CSV)
    fri_full["date"] = pd.to_datetime(fri_full["date"])
    fri_valid = fri_full.dropna(subset=["fri_index"])
    ax.plot(fri_valid["date"], fri_valid["fri_index"],
            color=C_FRI, linewidth=2.0, alpha=0.7, zorder=3,
            label="HSI (Housing)")

    # CFCI (overlap period, thicker)
    ax.plot(hist["date"], hist["cfci"],
            color=C_CFCI, linewidth=3.0, zorder=5,
            label="CCHI")

    # Highlight overlap period
    ax.axvspan(hist["date"].min(), hist["date"].max(),
               color=C_FILL, alpha=0.1, zorder=0)

    # Reference line at 100
    ax.axhline(100, color="#BDBDBD", linewidth=0.8, linestyle="--",
               alpha=0.5, zorder=1)

    # End value annotations
    # NOTE: `name` selects the CSV column and must keep the short keys
    # (CRI/FRI/CFCI). `label` is display-only and carries the renamed indices.
    for series, color, name, label in [
        (cri_full, C_CRI, "CRI", "CRI"),
        (fri_valid, C_FRI, "FRI", "HSI"),
        (hist, C_CFCI, "CFCI", "CCHI"),
    ]:
        last = series.iloc[-1]
        col = "cri_index" if name == "CRI" else ("fri_index" if name == "FRI" else "cfci")
        ax.annotate(f"{label}: {last[col]:.0f}",
                    xy=(last["date"], last[col]),
                    fontsize=9, fontweight="bold", color=color,
                    xytext=(8, 0), textcoords="offset points", va="center")

    # Styling
    ax.set_ylabel("Index Level (Base 100)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Date", fontsize=12)
    ax.legend(fontsize=10, loc="upper left", framealpha=0.9,
              edgecolor="#D5DBDB", fancybox=True)
    ax.grid(True, alpha=0.3, linestyle="-", color=C_GRID, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.set_major_locator(mdates.YearLocator(3))
    ax.xaxis.set_minor_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_xlim(cri_full["date"].min() - pd.Timedelta(days=60),
                max(cri_full["date"].max(), fri_valid["date"].max())
                + pd.Timedelta(days=60))
    ax.set_ylim(0, max(cri_full["cri_index"].max(),
                       fri_valid["fri_index"].max(),
                       hist["cfci"].max()) * 1.15)

    fig.suptitle("CRI vs. HSI vs. CCHI — Triple Index Comparison",
                 fontsize=16, fontweight="bold", y=0.97)
    ax.text(0.02, 0.02,
            "CRI = H\u00d7E\u00d7V\u00d7(1+\u03ba\u00b7S)  |  "
            "HSI = PriceGap + Vol + ClimateCVaR  |  "
            "CCHI = \u221a(CRI\u00d7HSI)  |  All base-100",
            transform=ax.transAxes, fontsize=7.5, color="#7F8C8D",
            ha="left", va="bottom",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="#E5E7EB", alpha=0.9))

    _save(fig, FIGURES_DIR / "cf_02_triple_comparison.png")


# ═══════════════════════════════════════════════════════════════════════
# Figure 3: CFCI Component Decomposition
# ═══════════════════════════════════════════════════════════════════════

def render_decomposition():
    """Show how CRI and FRI contribute to CFCI over time."""
    hist = pd.read_csv(config.CFCI_HISTORICAL_CSV)
    hist["date"] = pd.to_datetime(hist["date"])

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1, 1.3],
                                          "hspace": 0.08})

    # Panel A: CRI
    ax = axes[0]
    ax.fill_between(hist["date"], 0, hist["cri_index"],
                    color=C_CRI, alpha=0.3)
    ax.plot(hist["date"], hist["cri_index"],
            color=C_CRI, linewidth=2.0)
    ax.set_ylabel("CRI", fontsize=11, fontweight="bold", color=C_CRI)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.text(0.01, 0.88, "A. Climate Risk Index (CRI)",
            transform=ax.transAxes, fontsize=9, fontweight="bold",
            color=C_CRI, va="top")

    # Panel B: FRI
    ax = axes[1]
    ax.fill_between(hist["date"], 0, hist["fri_index"],
                    color=C_FRI, alpha=0.3)
    ax.plot(hist["date"], hist["fri_index"],
            color=C_FRI, linewidth=2.0)
    ax.set_ylabel("HSI", fontsize=11, fontweight="bold", color=C_FRI)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.text(0.01, 0.88, "B. Housing Stress Index (HSI)",
            transform=ax.transAxes, fontsize=9, fontweight="bold",
            color=C_FRI, va="top")

    # Panel C: CFCI
    ax = axes[2]
    ax.fill_between(hist["date"], 0, hist["cfci"],
                    color=C_CFCI, alpha=0.3)
    ax.plot(hist["date"], hist["cfci"],
            color=C_CFCI, linewidth=2.5)
    ax.set_ylabel("CCHI", fontsize=11, fontweight="bold", color=C_CFCI)
    ax.set_xlabel("Date", fontsize=11)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.text(0.01, 0.88,
            "C. Composite = \u221a(CRI \u00d7 HSI)",
            transform=ax.transAxes, fontsize=9, fontweight="bold",
            color=C_CFCI, va="top")

    # Correlation annotation
    corr = hist["cri_index"].corr(hist["fri_index"])
    ax.text(0.98, 0.88, f"CRI-HSI r = {corr:.3f}",
            transform=ax.transAxes, fontsize=9, fontweight="bold",
            ha="right", va="top", color="#424242",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="#BDBDBD", alpha=0.9))

    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_minor_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.suptitle("CCHI Component Decomposition",
                 fontsize=15, fontweight="bold", y=0.98)

    _save(fig, FIGURES_DIR / "cf_03_decomposition.png")


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=str, default=None,
                        help="Render one: index|triple|decomp")
    args = parser.parse_args()

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    dispatch = {
        "index":  render_cfci_index,
        "triple": render_triple_comparison,
        "decomp": render_decomposition,
    }

    if args.only:
        fn = dispatch.get(args.only)
        if fn is None:
            print(f"Unknown: {args.only}. Choose from: {list(dispatch.keys())}")
            sys.exit(1)
        fn()
    else:
        print("=" * 60)
        print("Composite Index — Generating All Figures")
        print("=" * 60)
        for name, fn in dispatch.items():
            print(f"\n[{name}]")
            fn()
        print(f"\nDone. {len(dispatch)} figures saved to {FIGURES_DIR}")
