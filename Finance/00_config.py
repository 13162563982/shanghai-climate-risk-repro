# === 00_config.py ===
# Shanghai Finance Risk Module — Configuration
# All parameters are either data-driven, literature constants,
# or structural symmetry choices.  ZERO subjective parameters.

import os
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
# Path Configuration
# ═══════════════════════════════════════════════════════════════════════

FINANCE_DIR = Path(__file__).resolve().parent           # Finance/
PROJECT_ROOT = FINANCE_DIR.parent                       # NEWROOT (self-contained package root)
CLIMATE_DIR = PROJECT_ROOT / "Climate"
DATA_DIR = PROJECT_ROOT / "data"

OUTPUT_DIR = FINANCE_DIR / "output"
RESULTS_DIR = OUTPUT_DIR / "results"
FIGURES_DIR = OUTPUT_DIR / "figures"
LOGS_DIR = OUTPUT_DIR / "logs"

# ═══════════════════════════════════════════════════════════════════════
# Input Data Paths
# ═══════════════════════════════════════════════════════════════════════

# City-level monthly housing price (2011-01 → 2025-12)
CITY_PRICE_EXCEL = (
    DATA_DIR / "Exposure_data" / "房屋"
    / "2011-2025年上海逐月二手房房价数据" / "excel格式的数据"
    / "上海全市二手房价.xlsx"
)

# Climate module hazard CSV (monthly, 1993-2023)
CLIMATE_HAZARD_CSV = CLIMATE_DIR / "output" / "results" / "shanghai_city_monthly_climate_hazard.csv"

# Climate CRI projection CSV (monthly, 2024-2050)
CLIMATE_PROJECTION_CSV = CLIMATE_DIR / "output" / "results" / "shanghai_city_cri_projection.csv"

# Climate CVaR from stochastic event set (monthly, 1993-2023)
CLIMATE_CVAR_CSV = RESULTS_DIR / "shanghai_climate_cvar_monthly.csv"

# ═══════════════════════════════════════════════════════════════════════
# Output Paths
# ═══════════════════════════════════════════════════════════════════════

FRI_OUTPUT_CSV = RESULTS_DIR / "shanghai_finance_risk_index.csv"

# ═══════════════════════════════════════════════════════════════════════
# FRI Parameters — ALL data-driven or convention-based
# ═══════════════════════════════════════════════════════════════════════

# HP filter smoothing: Ravn-Uhlig (2002) monthly convention
# λ = 1600 × (frequency ratio)^4 = 1600 × (12/4)^4 = 129,600
# This is the standard empirical choice for monthly data;
# sensitivity band: ±25% around convention (·1 RU step).
HP_LAMBDA = 129_600

# Rolling window for realized volatility (months)
# ── structural symmetry with CRI's 12-month rolling mean
VOLATILITY_WINDOW = 12

# Sub-indicator weights: equal-weight (1/3 each)
# Maximum-entropy choice when no prior information exists (OECD, 2008).
# Combined with mean-division normalisation, the FRI level is robust
# to modest weight reallocation (±0.07 per component).
FRI_WEIGHTS = (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)

# FRI base index level (same convention as CRI)
FRI_BASE_INDEX = 100.0

# ═════════════════════════════════════════════════════════════════════
# FRI Projection Parameters
# ═════════════════════════════════════════════════════════════════════

FRI_PROJECTION_END_YEAR = 2050
FRI_N_SIM = 500

# Output
FRI_PROJECTION_CSV = RESULTS_DIR / "shanghai_fri_projection.csv"


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

# Normalize FRI_WEIGHTS to sum to 1.0 (guards against JSON truncation, e.g. 0.333*3=0.999)
_ws = FRI_WEIGHTS
_wsum = sum(_ws)
if abs(_wsum - 1.0) > 1e-9:
    FRI_WEIGHTS = tuple(w / _wsum for w in _ws)
