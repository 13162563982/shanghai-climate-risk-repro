# === 00_config.py ===
# Shanghai Climate-Finance Composite Index (CFCI) — Configuration

import os
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
# Path Configuration
# ═══════════════════════════════════════════════════════════════════════

COMPOSITE_DIR = Path(__file__).resolve().parent         # Composite/
PROJECT_ROOT = COMPOSITE_DIR.parent                     # NEWROOT (self-contained package root)
CLIMATE_DIR = PROJECT_ROOT / "Climate"
FINANCE_DIR = PROJECT_ROOT / "Finance"

OUTPUT_DIR = COMPOSITE_DIR / "output"
RESULTS_DIR = OUTPUT_DIR / "results"
FIGURES_DIR = OUTPUT_DIR / "figures"

# ═══════════════════════════════════════════════════════════════════════
# Input Paths — from Climate and Finance modules
# ═══════════════════════════════════════════════════════════════════════

# Historical indices
CRI_HISTORICAL_CSV = CLIMATE_DIR / "output" / "results" / "shanghai_city_monthly_climate_hazard.csv"
FRI_HISTORICAL_CSV = FINANCE_DIR / "output" / "results" / "shanghai_finance_risk_index.csv"

# Projections
CRI_PROJECTION_CSV = CLIMATE_DIR / "output" / "results" / "shanghai_city_cri_projection.csv"
FRI_PROJECTION_CSV = FINANCE_DIR / "output" / "results" / "shanghai_fri_projection.csv"

# ═══════════════════════════════════════════════════════════════════════
# Output Paths
# ═══════════════════════════════════════════════════════════════════════

CFCI_HISTORICAL_CSV = RESULTS_DIR / "shanghai_cfci_historical.csv"
CFCI_PROJECTION_CSV = RESULTS_DIR / "shanghai_cfci_projection.csv"

# ═══════════════════════════════════════════════════════════════════════
# CFCI Parameters — ZERO subjective parameters
# ═══════════════════════════════════════════════════════════════════════

# Aggregation: geometric mean
# CFCI = sqrt(CRI × FRI)
# - Parameter-free (no weights to tune)
# - Scale-invariant (base-100 preserved: sqrt(100×100) = 100)
# - Multiplicative risk logic: both channels high → disproportionate risk
# - Standard in composite index literature (HDI, UNDP)
CFCI_METHOD = "geometric_mean"

# Base index level (inherited from both modules)
CFCI_BASE_INDEX = 100.0

# Projection end year (inherited)
CFCI_PROJECTION_END_YEAR = 2050

# ═══════════════════════════════════════════════════════════════════════
# Path-level MC propagation (Iman-Conover rank reordering)
# ═══════════════════════════════════════════════════════════════════════

# MC path NPZ files (written by CRI and FRI projection modules)
_SCENARIO_KEYS = ["baseline", "ssp245", "ssp585"]
_SCENARIO_LABELS = ["Historical Baseline", "SSP2-4.5", "SSP5-8.5"]

CRI_MC_PATHS = {
    lbl: CLIMATE_DIR / "output" / "results" / f"cri_mc_paths_{key}.npz"
    for key, lbl in zip(_SCENARIO_KEYS, _SCENARIO_LABELS)
}
FRI_MC_PATHS = {
    lbl: FINANCE_DIR / "output" / "results" / f"fri_mc_paths_{key}.npz"
    for key, lbl in zip(_SCENARIO_KEYS, _SCENARIO_LABELS)
}

# Target Spearman correlation for Iman-Conover pairing
# Estimated from historical CRI-FRI overlap (2011-12 → 2023-12)
CFCI_TARGET_RHO = 0.358


def _apply_overrides():
    import json as _json
    raw = os.environ.get("V8_PARAM_OVERRIDES", "")
    if not raw:
        return
    overrides = _json.loads(raw)
    g = globals()
    for key, val in overrides.items():
        if "." in key:
            parent_key, sub_key = key.split(".", 1)
            if parent_key in g and isinstance(g[parent_key], dict):
                g[parent_key][sub_key] = val
        elif key in g:
            g[key] = val

_apply_overrides()
