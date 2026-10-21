# === generate_figures.py ===
# Shanghai Finance Risk Index — Visualization
#
# Figures:
#   fi_01  FRI Main Index (raw + 12-mo smoothed, base-100)
#   fi_02  Sub-indicator Decomposition (stacked area, 3 drivers)
#   fi_03  Housing Price + HP Trend (gap highlighting)
#   fi_04  FRI vs CRI Overlay (dual-axis, correlation)

import importlib.util
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

# ── Load config ──────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "config", SCRIPT_DIR / "00_config.py")
config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config)

# ── Latin-safe font to avoid garbled CJK ─────────────────────────────
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


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", dpi=300)
    plt.close(fig)
    print(f"  [OK] {path.name}")


def _load_fri():
    df = pd.read_csv(config.FRI_OUTPUT_CSV)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _load_fri_proj():
    p = config.FRI_PROJECTION_CSV
    if p.exists():
        df = pd.read_csv(p)
        df["date"] = pd.to_datetime(df["date"])
        return df
    return None


def _load_cri():
    df = pd.read_csv(config.CLIMATE_HAZARD_CSV)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ═══════════════════════════════════════════════════════════════════════
# Color Palette (warm finance tones, contrasting with Climate blues)
# ═══════════════════════════════════════════════════════════════════════
C_FRI_MAIN  = "#1565C0"   # deep blue — main FRI
C_FRI_RAW   = "#90CAF9"   # light blue — raw monthly
C_FRI_FILL  = "#E3F2FD"   # very pale blue — fill
C_GAP       = "#E65100"   # orange — price gap driver
C_VOL       = "#2E7D32"   # green  — volatility driver
C_CVAR      = "#C62828"   # red    — CVaR driver
C_PRICE     = "#37474F"   # dark grey — price line
C_TREND     = "#D84315"   # warm red  — HP trend
C_CRI       = "#D35400"   # orange — CRI (matches Climate module)
C_GRID      = "#ECF0F1"


# ═══════════════════════════════════════════════════════════════════════
# Figure 1: FRI Main Index
# ═══════════════════════════════════════════════════════════════════════

def render_fri_index():
    """Base-100 FRI line chart with raw + smoothed + projection (2-panel)."""
    df = _load_fri()
    proj = _load_fri_proj()
    valid = df.dropna(subset=["fri_index"])

    # Compute raw index on same base
    first_valid_12m = df["fri_12m"].dropna().iloc[0]
    df["fri_raw_index"] = config.FRI_BASE_INDEX * df["fri_raw"] / first_valid_12m

    C_HIST_PROJ = "#1976D2"
    C_SSP245 = "#2E7D32"
    C_SSP585 = "#C62828"

    scenario_styles = {
        "Historical Baseline": {"color": C_HIST_PROJ, "ls": "--",
                                "lw": 2.2, "fill": "#BBDEFB",
                                "label": "Historical Baseline"},
        "SSP2-4.5":            {"color": C_SSP245,    "ls": "-.",
                                "lw": 2.2, "fill": "#C8E6C9",
                                "label": "SSP2-4.5"},
        "SSP5-8.5":            {"color": C_SSP585,    "ls": "-",
                                "lw": 2.2, "fill": "#FFCDD2",
                                "label": "SSP5-8.5"},
    }

    last_fri_val = valid["fri_index"].iloc[-1]

    # ── Two-panel figure ─────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(22, 8),
                                   gridspec_kw={"width_ratios": [1.15, 1],
                                                "wspace": 0.18})

    # ── Helper: draw historical portion ──────────────────────────────
    def _draw_hist(ax, show_raw=True, show_peak=True):
        ax.fill_between(valid["date"], 0, valid["fri_index"],
                        color=C_FRI_FILL, alpha=0.4, zorder=0)
        if show_raw:
            raw_valid = df.dropna(subset=["fri_raw_index"])
            clip_hi = np.nanpercentile(raw_valid["fri_raw_index"], 99.5)
            ax.plot(raw_valid["date"],
                    raw_valid["fri_raw_index"].clip(upper=clip_hi),
                    color=C_FRI_RAW, linewidth=0.5, alpha=0.4, zorder=1)
        ax.plot(valid["date"], valid["fri_index"],
                color=C_FRI_MAIN, linewidth=2.8, zorder=4,
                label="HSI")
        if show_peak:
            peak = valid.loc[valid["fri_index"].idxmax()]
            ax.annotate(
                f"Peak {peak['fri_index']:.0f}\n({peak['date'].strftime('%Y-%m')})",
                xy=(peak["date"], peak["fri_index"]),
                xytext=(0, 18), textcoords="offset points",
                fontsize=9, fontweight="bold", color=C_FRI_MAIN,
                ha="center", va="bottom",
                arrowprops=dict(arrowstyle="-|>", color=C_FRI_MAIN, lw=1.2))

    # ── Helper: style an axis ────────────────────────────────────────
    def _style_ax(ax, ylabel=True):
        if ylabel:
            ax.set_ylabel("HSI", fontsize=13, fontweight="bold")
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
    _draw_hist(ax1, show_raw=True, show_peak=True)

    end_vals_a = []
    if proj is not None:
        last_hist_date = valid["date"].max()
        ax1.axvline(last_hist_date, color="#95A5A6", linewidth=0.8,
                    linestyle=":", alpha=0.6, zorder=2)

        for scenario, style in scenario_styles.items():
            s_data = proj[proj["scenario"] == scenario].copy()
            if s_data.empty:
                continue

            dates_plot = pd.DatetimeIndex(
                [last_hist_date] + s_data["date"].tolist())
            vals_main = np.concatenate(
                [[last_fri_val], s_data["fri_index_p50"].values])

            if "fri_index_p10" in s_data.columns:
                vals_p10 = np.concatenate(
                    [[last_fri_val], s_data["fri_index_p10"].values])
                vals_p90 = np.concatenate(
                    [[last_fri_val], s_data["fri_index_p90"].values])
                ax1.fill_between(dates_plot, vals_p10, vals_p90,
                                 color=style["fill"], alpha=0.22, zorder=1)

            ax1.plot(dates_plot, vals_main,
                     color=style["color"], linewidth=style["lw"],
                     linestyle=style["ls"], label=style["label"], zorder=4)

            end_val = s_data["fri_index_p50"].iloc[-1]
            end_date = s_data["date"].iloc[-1]
            end_vals_a.append((end_val, end_date, style["color"]))

    ax1.legend(fontsize=8.5, loc="upper left", framealpha=0.9,
               edgecolor="#D5DBDB", fancybox=True, ncol=2)
    _style_ax(ax1)

    x_end = valid["date"].max()
    if proj is not None:
        x_end = proj["date"].max()
    ax1.set_xlim(valid["date"].min(), x_end + pd.Timedelta(days=180))

    y_max = valid["fri_index"].max()
    if proj is not None and "fri_index_p90" in proj.columns:
        y_max = max(y_max, proj["fri_index_p90"].max())
    ax1.set_ylim(0, y_max * 1.12)

    # Anti-overlap annotations for Panel A (needs y_max)
    if proj is not None and end_vals_a:
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

    y_start = valid["fri_index"].iloc[0]
    ax1.annotate(f"{y_start:.0f}",
                 xy=(valid["date"].iloc[0], y_start),
                 fontsize=9, color=C_FRI_MAIN, fontweight="bold",
                 xytext=(-30, 10), textcoords="offset points")

    ax1.set_title("A. Scenario Comparison (Median Projections)",
                  fontsize=12, fontweight="bold", pad=8)

    # ══════════════════════════════════════════════════════════════════
    # Panel B (right): Representative Pathways — all 3 scenarios
    # ══════════════════════════════════════════════════════════════════
    _draw_hist(ax2, show_raw=False, show_peak=False)

    if proj is not None:
        last_hist_date = valid["date"].max()
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
                [[last_fri_val], s_data["fri_index_rep"].values])
            ax2.plot(dates_plot, vals_rep,
                     color=style["color"], linewidth=2.2,
                     linestyle=style["ls"], label=style["label"],
                     zorder=4)

            end_val = s_data["fri_index_rep"].iloc[-1]
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

    ax2.set_xlim(valid["date"].min(), x_end + pd.Timedelta(days=180))
    ax2.set_ylim(0, y_max * 1.12)

    ax2.set_title("B. Representative Pathways (Characteristic MC Paths)",
                  fontsize=12, fontweight="bold", pad=8)

    # ── Suptitle & footnote ──────────────────────────────────────────
    end_year = config.FRI_PROJECTION_END_YEAR if proj is not None else 2025
    fig.suptitle("Housing Stress Index",
                 fontsize=16, fontweight="bold", y=0.98)
    fig.text(0.5, 0.01,
             "HSI: Sub-indicators derived from simulated price paths  |  "
             "Bands: 10th\u201390th percentile, N=500 MC paths",
             fontsize=7.5, color="#7F8C8D", ha="center", va="bottom",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                       edgecolor="#E5E7EB", alpha=0.9))

    _save(fig, FIGURES_DIR / "fi_01_finance_risk_index.png")


# ═══════════════════════════════════════════════════════════════════════
# Figure 2: Sub-indicator Decomposition
# ═══════════════════════════════════════════════════════════════════════

def render_sub_indicators():
    """Stacked area chart of 3 normalized sub-indicators."""
    df = _load_fri()
    valid = df.dropna(subset=["gap_norm", "vol_norm", "climate_norm"]).copy()

    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1, 1, 1.3],
                                          "hspace": 0.08})

    # Panel A: Price Gap (normalized)
    ax = axes[0]
    ax.fill_between(valid["date"], 0, valid["gap_norm"],
                    color=C_GAP, alpha=0.35, zorder=1)
    ax.plot(valid["date"], valid["gap_norm"],
            color=C_GAP, linewidth=1.5, zorder=2)
    ax.set_ylabel("Price Gap", fontsize=10, fontweight="bold", color=C_GAP)
    ax.set_ylim(0, 1.05)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.text(0.01, 0.88, "A. Price Gap (HP deviation)",
            transform=ax.transAxes, fontsize=9, fontweight="bold",
            color=C_GAP, va="top")

    # Panel B: Realized Volatility (normalized)
    ax = axes[1]
    ax.fill_between(valid["date"], 0, valid["vol_norm"],
                    color=C_VOL, alpha=0.35, zorder=1)
    ax.plot(valid["date"], valid["vol_norm"],
            color=C_VOL, linewidth=1.5, zorder=2)
    ax.set_ylabel("Realized Vol", fontsize=10, fontweight="bold", color=C_VOL)
    ax.set_ylim(0, 1.05)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.text(0.01, 0.88, "B. Realized Volatility (12-mo rolling)",
            transform=ax.transAxes, fontsize=9, fontweight="bold",
            color=C_VOL, va="top")

    # Panel C: Climate Risk Intensity (normalized)
    ax = axes[2]
    ax.fill_between(valid["date"], 0, valid["climate_norm"],
                    color=C_CVAR, alpha=0.35, zorder=1)
    ax.plot(valid["date"], valid["climate_norm"],
            color=C_CVAR, linewidth=1.5, zorder=2)
    ax.set_ylabel("Climate CVaR", fontsize=10, fontweight="bold", color=C_CVAR)
    ax.set_ylim(0, 1.05)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.text(0.01, 0.88, "C. Climate CVaR (Stochastic Event Set)",
            transform=ax.transAxes, fontsize=9, fontweight="bold",
            color=C_CVAR, va="top")

    # Panel D: Composite FRI (stacked)
    ax = axes[3]
    w = 1.0 / 3.0
    y1 = valid["gap_norm"] * w
    y2 = y1 + valid["vol_norm"] * w
    y3 = y2 + valid["climate_norm"] * w

    ax.fill_between(valid["date"], 0, y1,
                    color=C_GAP, alpha=0.5, label="Price Gap")
    ax.fill_between(valid["date"], y1, y2,
                    color=C_VOL, alpha=0.5, label="Realized Vol")
    ax.fill_between(valid["date"], y2, y3,
                    color=C_CVAR, alpha=0.5, label="Climate CVaR")

    # Overlay FRI raw line
    ax.plot(valid["date"], valid["fri_raw"],
            color=C_FRI_MAIN, linewidth=1.8, zorder=5,
            label="HSI (raw composite)")

    ax.set_ylabel("HSI Raw [0-1]", fontsize=10, fontweight="bold")
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylim(0, valid["fri_raw"].max() * 1.2)
    ax.legend(fontsize=8.5, loc="upper right", ncol=4, framealpha=0.9,
              edgecolor="#D5DBDB")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.text(0.01, 0.92, "D. Weighted Composite (equal 1/3)",
            transform=ax.transAxes, fontsize=9, fontweight="bold",
            color=C_FRI_MAIN, va="top")

    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_minor_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.suptitle("HSI Sub-indicator Decomposition",
                 fontsize=15, fontweight="bold", y=0.98)

    _save(fig, FIGURES_DIR / "fi_02_sub_indicator_decomposition.png")


# ═══════════════════════════════════════════════════════════════════════
# Figure 3: Housing Price + HP Trend
# ════════════════��══════════════════════════════════════════════════════

def render_price_trend():
    """Housing price vs HP trend with gap shading."""
    df = _load_fri()
    valid = df.dropna(subset=["price", "price_trend"]).copy()

    fig, ax1 = plt.subplots(figsize=(14, 6))

    # Gap shading: red when price above trend, blue when below
    above = valid["price"] >= valid["price_trend"]

    ax1.fill_between(valid["date"],
                     valid["price"], valid["price_trend"],
                     where=above, interpolate=True,
                     color="#FFCDD2", alpha=0.6, label="Price > Trend")
    ax1.fill_between(valid["date"],
                     valid["price"], valid["price_trend"],
                     where=~above, interpolate=True,
                     color="#BBDEFB", alpha=0.6, label="Price < Trend")

    # Price line
    ax1.plot(valid["date"], valid["price"],
             color=C_PRICE, linewidth=2.2, zorder=3,
             label="Housing Price (yuan/m\u00b2)")

    # HP trend line
    ax1.plot(valid["date"], valid["price_trend"],
             color=C_TREND, linewidth=2.2, linestyle="--", zorder=4,
             label="HP Trend (\u03bb=129,600)")

    # Gap % on right axis
    ax2 = ax1.twinx()
    gap_pct = (valid["price"] / valid["price_trend"] - 1.0) * 100
    ax2.bar(valid["date"], gap_pct, width=25, color="#78909C",
            alpha=0.3, zorder=1)
    ax2.set_ylabel("Price Gap (%)", fontsize=11, color="#78909C")
    ax2.tick_params(axis="y", labelcolor="#78909C")
    ax2.axhline(0, color="#78909C", linewidth=0.5, alpha=0.5)
    ax2.set_ylim(-max(abs(gap_pct.min()), gap_pct.max()) * 1.5,
                 max(abs(gap_pct.min()), gap_pct.max()) * 1.5)

    # Styling
    ax1.set_ylabel("Price (yuan/m\u00b2)", fontsize=13, fontweight="bold")
    ax1.set_xlabel("Date", fontsize=12)
    ax1.legend(fontsize=9, loc="upper left", framealpha=0.9,
               edgecolor="#D5DBDB", fancybox=True)
    ax1.spines["top"].set_visible(False)
    ax1.xaxis.set_major_locator(mdates.YearLocator(2))
    ax1.xaxis.set_minor_locator(mdates.YearLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax1.set_xlim(valid["date"].min() - pd.Timedelta(days=30),
                 valid["date"].max() + pd.Timedelta(days=30))
    ax1.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, p: f"{x:,.0f}"))

    fig.suptitle("Shanghai Housing Price vs. HP Trend",
                 fontsize=16, fontweight="bold", y=0.97)
    ax1.text(0.02, 0.02,
             "HP filter: \u03bb=129,600 (Ravn-Uhlig monthly)  |  "
             "Gap = (P / Trend \u2212 1)",
             transform=ax1.transAxes, fontsize=7.5, color="#7F8C8D",
             ha="left", va="bottom",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                       edgecolor="#E5E7EB", alpha=0.9))

    _save(fig, FIGURES_DIR / "fi_03_price_hp_trend.png")


# ═══════════════════════════════════════════════════════════════════════
# Figure 4: FRI vs CRI Dual-Axis Overlay
# ═══════════════════════════════════════════════════════════════════════

def render_fri_vs_cri():
    """Dual-axis overlay of FRI and CRI with correlation stat."""
    fri = _load_fri()
    cri = _load_cri()

    # CRI index — reconstruct if not present
    if "cri_index" not in cri.columns:
        cri["cri_raw"] = cri["hazard_index"]
        cri["cri_12m"] = cri["cri_raw"].rolling(12, min_periods=6).mean()
        first_v = cri["cri_12m"].first_valid_index()
        base = cri.loc[first_v, "cri_12m"] if first_v is not None else 1.0
        cri["cri_index"] = 100.0 * cri["cri_12m"] / max(base, 1e-12)

    cri_valid = cri.dropna(subset=["cri_index"])

    fig, ax1 = plt.subplots(figsize=(14, 6))
    ax2 = ax1.twinx()

    # FRI line (left axis)
    fri_valid = fri.dropna(subset=["fri_index"])
    ax1.plot(fri_valid["date"], fri_valid["fri_index"],
             color=C_FRI_MAIN, linewidth=2.5, zorder=3,
             label="HSI (Housing)")
    ax1.fill_between(fri_valid["date"], 0, fri_valid["fri_index"],
                     color=C_FRI_FILL, alpha=0.3, zorder=0)

    # CRI line (right axis)
    ax2.plot(cri_valid["date"], cri_valid["cri_index"],
             color=C_CRI, linewidth=2.5, linestyle="--", zorder=3,
             label="CRI (Climate)")

    # Overlapping region shading
    overlap_start = max(fri_valid["date"].min(), cri_valid["date"].min())
    overlap_end = min(fri_valid["date"].max(), cri_valid["date"].max())
    ax1.axvspan(overlap_start, overlap_end,
                color="#F5F5F5", alpha=0.3, zorder=-1)

    # Correlation stat
    merged = fri_valid[["date", "fri_index"]].merge(
        cri_valid[["date", "cri_index"]], on="date", how="inner")
    if len(merged) > 12:
        corr = merged["fri_index"].corr(merged["cri_index"])
        corr_text = f"Pearson r = {corr:.3f} (n={len(merged)} months)"
    else:
        corr_text = "Insufficient overlap for correlation"

    ax1.text(0.98, 0.95, corr_text,
             transform=ax1.transAxes, fontsize=10, fontweight="bold",
             ha="right", va="top", color="#424242",
             bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                       edgecolor="#BDBDBD", alpha=0.95))

    # Styling
    ax1.set_ylabel("HSI", fontsize=13,
                   fontweight="bold", color=C_FRI_MAIN)
    ax2.set_ylabel("CRI Level (Base 100)", fontsize=13,
                   fontweight="bold", color=C_CRI)
    ax1.set_xlabel("Date", fontsize=12)
    ax1.tick_params(axis="y", labelcolor=C_FRI_MAIN)
    ax2.tick_params(axis="y", labelcolor=C_CRI)

    # Merged legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2,
               fontsize=10, loc="upper left", framealpha=0.9,
               edgecolor="#D5DBDB", fancybox=True)

    ax1.spines["top"].set_visible(False)
    ax1.xaxis.set_major_locator(mdates.YearLocator(3))
    ax1.xaxis.set_minor_locator(mdates.YearLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # X range: union of both
    x_min = min(fri_valid["date"].min(), cri_valid["date"].min())
    x_max = max(fri_valid["date"].max(), cri_valid["date"].max())
    ax1.set_xlim(x_min - pd.Timedelta(days=60),
                 x_max + pd.Timedelta(days=60))
    ax1.set_ylim(0, fri_valid["fri_index"].max() * 1.15)
    ax2.set_ylim(0, cri_valid["cri_index"].max() * 1.15)

    fig.suptitle("Housing Stress Index vs. Climate Risk Index",
                 fontsize=16, fontweight="bold", y=0.97)
    ax1.text(0.02, 0.02,
             "HSI: price gap + vol + climate CVaR  |  "
             "CRI: H\u00d7E\u00d7V\u00d7(1+\u03ba\u00b7S)  |  "
             "Both base-100, 12-mo rolling",
             transform=ax1.transAxes, fontsize=7.5, color="#7F8C8D",
             ha="left", va="bottom",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                       edgecolor="#E5E7EB", alpha=0.9))

    _save(fig, FIGURES_DIR / "fi_04_fri_vs_cri_overlay.png")


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=str, default=None,
                        help="Render only one figure: index|sub|price|overlay")
    args = parser.parse_args()

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    dispatch = {
        "index":   render_fri_index,
        "sub":     render_sub_indicators,
        "price":   render_price_trend,
        "overlay": render_fri_vs_cri,
    }

    if args.only:
        fn = dispatch.get(args.only)
        if fn is None:
            print(f"Unknown: {args.only}. Choose from: {list(dispatch.keys())}")
            sys.exit(1)
        fn()
    else:
        print("=" * 60)
        print("Finance Risk Index — Generating All Figures")
        print("=" * 60)
        for name, fn in dispatch.items():
            print(f"\n[{name}]")
            fn()
        print("\n" + "=" * 60)
        print(f"Done. {len(dispatch)} figures saved to {FIGURES_DIR}")
        print("=" * 60)
