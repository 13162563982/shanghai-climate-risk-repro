# === 00_config.py ===
# Shanghai Real-Estate Climate Risk Model v8 — Performance-Optimized
# All computation and visualization parameters. Based on v7 baseline.

import os
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
# Path Configuration (fully self-contained)
# ═══════════════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).resolve().parent.parent          # NEWROOT (self-contained package root)
CLIMATE_DIR = Path(__file__).resolve().parent                  # Climate/
DATA_DIR = PROJECT_ROOT / "data"

HAZARD_DATA_DIR = DATA_DIR / "Hazard_data"
EXPOSURE_DATA_DIR = DATA_DIR / "Exposure_data"
ADMIN_BOUNDARY_DIR = DATA_DIR / "我国乡镇（街道）行政区划数据"

# Output directories (all inside NEWROOT)
OUTPUT_DIR = CLIMATE_DIR / "output"
INTERMEDIATE_DIR = OUTPUT_DIR / "intermediate"
RESULTS_DIR = OUTPUT_DIR / "results"
FIGURES_DIR = OUTPUT_DIR / "figures"
LOGS_DIR = OUTPUT_DIR / "logs"

# ═══════════════════════════════════════════════════════════════════════
# Raw Data Paths
# ═══════════════════════════════════════════════════════════════════════

# Administrative boundary layer used for all reported results.
# Source: Tianditu (天地图) GS(2024)0650 county-level divisions, pre-processed by
#         Climate/build_admin_boundary.py; provenance and SHA256 in
#         data/我国乡镇（街道）行政区划数据/_官方_天地图GS2024-0650/_SOURCE.txt
ADMIN_BOUNDARY_SHP = (
    ADMIN_BOUNDARY_DIR / "_官方_天地图GS2024-0650" / "上海_区级_GS2024-0650.shp"
)
# Legacy township/street layer (provenance untraceable). Kept ONLY for the A1
# baseline regression and historical archiving; NOT used for reported results.
# Override ADMIN_BOUNDARY_SHP with this path (via V8_PARAM_OVERRIDES) to
# reproduce the pre-2026-10 baseline.
ADMIN_BOUNDARY_LEGACY_SHP = ADMIN_BOUNDARY_DIR / "2021年我国乡镇（街道）边界数据.shp"

# Coastline source for the storm-surge channel
# (climate_functions.compute_east_sea_coast_distance).
# The official GS(2024)0650 layer is a GENERALISED product: its union boundary
# intersected with the DEM ocean mask yields only 96.2 km of shoreline versus
# 347.9 km from the fine township layer, which suppresses surge inundation by
# ~13.7% (see docs/_潮损偏移复核报告.md). District assignment, area/density and
# the basemap keep using ADMIN_BOUNDARY_SHP; ONLY the shoreline uses this layer.
COASTLINE_BOUNDARY_SHP = ADMIN_BOUNDARY_LEGACY_SHP

# Hazard data
IBTRACS_FILE = HAZARD_DATA_DIR / "WP台风数据" / "IBTrACS.WP.v04r01.nc"
FABDEM_DIR = HAZARD_DATA_DIR / "N30E120-N40E130_FABDEM_V1-2"
FABDEM_TILES_SHANGHAI = [
    FABDEM_DIR / "N30E121_FABDEM_V1-2.tif",
    FABDEM_DIR / "N31E120_FABDEM_V1-2.tif",
    FABDEM_DIR / "N31E121_FABDEM_V1-2.tif",
]
FABDEM_NODATA_VALUE = -9999.0
SLA_DIR = HAZARD_DATA_DIR / "1993-2023年上海逐月海平面高度数据"
ISR_DIR = HAZARD_DATA_DIR / "1985-2020年上海逐年不透水面栅格数据"
WIND_RASTER_DIR = HAZARD_DATA_DIR / "1951-2024年上海逐月全风速栅格数据"
PRECIP_RASTER_DIR = HAZARD_DATA_DIR / "1960-2024年上海逐月降水栅格数据"
TMIN_RASTER_DIR = HAZARD_DATA_DIR / "1981-2024年上海逐月最低气温栅格数据"
TMAX_RASTER_DIR = HAZARD_DATA_DIR / "1981-2024年上海逐月最高气温栅格数据"

# Exposure data
BUILDING_VECTOR_DIR = EXPOSURE_DATA_DIR / "房屋" / "2024年上海多属性建筑矢量数据"
LIANJIA_POI_DIR = EXPOSURE_DATA_DIR / "房屋" / "上海小区数据（链家）"
DISTRICT_PRICE_DIR = EXPOSURE_DATA_DIR / "房屋" / "2015-2025年上海逐月区县二手房房价数据"
DISTRICT_PRICE_EXCEL = DISTRICT_PRICE_DIR / "excel格式的数据" / "上海区县二手房价.xlsx"
CITY_PRICE_DIR = EXPOSURE_DATA_DIR / "房屋" / "2011-2025年上海逐月二手房房价数据"
CITY_PRICE_EXCEL = CITY_PRICE_DIR / "excel格式的数据" / "上海全市二手房价.xlsx"
BUILT_UP_AREA_DIR = EXPOSURE_DATA_DIR / "房屋" / "1975-2020年上海城市建成区矢量数据"
POPULATION_DIR = EXPOSURE_DATA_DIR / "人口"
LANDSCAN_DIR = POPULATION_DIR / "2000-2024年上海1km精度人口分布栅格数据"
LANDSCAN_REFERENCE_YEAR = 2024
TOWNSHIP_POP_DIR = POPULATION_DIR / "2000-2024年上海逐年乡镇人口数量数据"
CENSUS_7TH_DIR = POPULATION_DIR / "上海第七次人口普查街道数据"
CENSUS_6TH_DIR = POPULATION_DIR / "上海第六次人口普查街道数据"
CENSUS_5TH_DIR = POPULATION_DIR / "上海第五次人口普查街道数据"
FACILITY_DIR = EXPOSURE_DATA_DIR / "公共设施"

# ═══════════════════════════════════════════════════════════════════════
# Intermediate File Paths (computed by pipeline steps)
# ═══════════════════════════════════════════════════════════════════════

# Step 01: TC Wind Hazard
TC_TRACKS_PKL = INTERMEDIATE_DIR / "tc_tracks_shanghai.pkl"
TC_TRACKS_ALL_PKL = INTERMEDIATE_DIR / "tc_tracks_all.pkl"
HAZ_TC_HIST_HDF5 = INTERMEDIATE_DIR / "haz_TC_hist.hdf5"
HAZ_TC_SYNTH_HDF5 = INTERMEDIATE_DIR / "haz_TC_synth.hdf5"
HAZ_TC_SSP245_HDF5 = INTERMEDIATE_DIR / "haz_TC_ssp245.hdf5"
HAZ_TC_SSP585_HDF5 = INTERMEDIATE_DIR / "haz_TC_ssp585.hdf5"
ALPHA_TEMP_CSV = INTERMEDIATE_DIR / "alpha_temp_series.csv"

# Step 02: Storm Surge Hazard
DEM_SHANGHAI_TIF = INTERMEDIATE_DIR / "dem_shanghai.tif"
SLA_MONTHLY_CSV = INTERMEDIATE_DIR / "sla_monthly.csv"
SURGE_HEIGHTS_CSV = INTERMEDIATE_DIR / "surge_heights_hist.csv"
HAZ_SS_HIST_HDF5 = INTERMEDIATE_DIR / "haz_SS_hist.hdf5"
HAZ_SS_SYNTH_HDF5 = INTERMEDIATE_DIR / "haz_SS_synth.hdf5"
HAZ_SS_SSP245_HDF5 = INTERMEDIATE_DIR / "haz_SS_ssp245.hdf5"
HAZ_SS_SSP585_HDF5 = INTERMEDIATE_DIR / "haz_SS_ssp585.hdf5"
TWL_VEC_HIST_NPY = INTERMEDIATE_DIR / "twl_vec_hist.npy"
TWL_VEC_SYNTH_NPY = INTERMEDIATE_DIR / "twl_vec_synth.npy"
BUILDING_ELEVATION_NPY = INTERMEDIATE_DIR / "building_elevation.npy"
BUILDING_COAST_DISTANCE_NPY = INTERMEDIATE_DIR / "building_coast_distance_m.npy"
BUILDING_HUANGPU_OVERBANK_TEMPLATE_NPY = INTERMEDIATE_DIR / "building_huangpu_overbank_template_m.npy"

# Step 03: Exposure
BUILDING_SKELETON_PARQUET = INTERMEDIATE_DIR / "building_skeleton.parquet"
POPULATION_LANDSCAN_CLIPPED_TIF = INTERMEDIATE_DIR / "population_landscan_2024_shanghai.tif"

# Step 04: Vulnerability
IMPF_SET_TC_PKL = INTERMEDIATE_DIR / "impf_set_TC.pkl"
IMPF_SET_SS_PKL = INTERMEDIATE_DIR / "impf_set_SS.pkl"
SVI_CSV = INTERMEDIATE_DIR / "svi_by_district.csv"
ISR_PANEL_CSV = INTERMEDIATE_DIR / "isr_panel.csv"
DELTA_ISR_CSV = INTERMEDIATE_DIR / "delta_isr_by_district.csv"

# ═══════════════════════════════════════════════════════════════════════
# Results File Paths (produced by pipeline)
# ═══════════════════════════════════════════════════════════════════════

RISK_PANEL_HIGH_CONF_CSV = RESULTS_DIR / "risk_panel_high_confidence.csv"
RISK_PANEL_ALL_SCENARIOS_HIGH_CONF_CSV = RESULTS_DIR / "risk_panel_all_scenarios_high_confidence.csv"
TC_DATE_ALIGNMENT_CSV = RESULTS_DIR / "tc_date_alignment_audit.csv"

DEFENSE_SENSITIVITY_DIR = RESULTS_DIR / "defense_sensitivity"
DEFENSE_PROFILE_EAL_CSV = DEFENSE_SENSITIVITY_DIR / "defense_profile_eal.csv"
DEFENSE_HAZARD_METRICS_DIR = DEFENSE_SENSITIVITY_DIR / "hazard_metrics"

CFI_HAZARD_CITY_CSV = RESULTS_DIR / "shanghai_city_monthly_climate_hazard.csv"

# ═══════════════════════════════════════════════════════════════════════
# Spatial & Geographic Parameters
# ═══════════════════════════════════════════════════════════════════════

SHANGHAI_BBOX = (120.85, 30.65, 122.00, 31.90)
CRS_STANDARD = "EPSG:4326"
MODEL_RESOLUTION_DEG = 0.01
SHANGHAI_CENTER_LON = 121.47
SHANGHAI_CENTER_LAT = 31.23
TC_FILTER_RADIUS_DEG = 3.0

SHANGHAI_DISTRICTS = [
    "黄浦区", "徐汇区", "长宁区", "静安区", "普陀区", "虹口区", "杨浦区",
    "闵行区", "宝山区", "嘉定区", "浦东新区", "金山区", "松江区", "青浦区",
    "奉贤区", "崇明区",
]
# District-name normalisation. No-op for the official GS(2024)0650 layer (it
# already uses 崇明区); retained for the legacy township layer.
ADMIN_DISTRICT_RENAME = {"崇明县": "崇明区", "闸北区": "静安区"}

# ═══════════════════════════════════════════════════════════════════════
# TC Wind Hazard Parameters
# ═══════════════════════════════════════════════════════════════════════

TC_WIND_MODEL = "H10"                  # Holland 2010
NB_SYNTH_TRACKS = 10
RANDOM_SEED = 42
N_WORKERS = max(1, min((os.cpu_count() or 4) // 2, 4))
MAX_MEMORY_GB = 4.0
IO_WORKERS = min(8, os.cpu_count() or 4)

SSP_TC_INTENSITY_FACTOR_2050 = {"SSP2-4.5": 1.05, "SSP5-8.5": 1.10}

# ═══════════════════════════════════════════════════════════════════════
# Storm Surge Physical Constants
# ═══════════════════════════════════════════════════════════════════════

RHO_AIR = 1.225
RHO_WATER = 1025.0
G = 9.81
P_ENV_DEFAULT_HPA = 1013.25
CD_MAX = 2.5e-3

# Continental shelf geometry (ETOPO-derived, East China Sea off Shanghai)
L_SHELF_M = 550_000.0              # ~550 km shelf width
H_SHELF_M = 55.0                   # ~55 m average shelf depth
HOLLAND_B_DEFAULT = 1.5
RMAX_DEFAULT_KM = 50.0
FETCH_RMAX_FACTOR = 3.0

SSP_SEA_LEVEL_RISE_2050 = {"SSP2-4.5": 0.3, "SSP5-8.5": 0.5}

# Coastal propagation (bathtub)
COASTAL_DEFENSE_CREST_M = 0.0
COASTAL_MIN_REACH_M = 500.0
COASTAL_OVERLAND_ATTENUATION_RATE = 1e-4
COASTAL_ATTENUATION_EXPONENT = 3.0
COASTAL_MIN_INUNDATION_DEPTH_M = 0.10

# Huangpu river hybrid overbank
HYBRID_HUANGPU_OVERBANK_ENABLED = True
HYBRID_HUANGPU_EVENT_DRIVEN_ENABLED = True
HYBRID_HUANGPU_RESPONSE_MODE = "smoothstep"
HYBRID_HUANGPU_TRIGGER_TWL_M = 2.86
HYBRID_HUANGPU_REFERENCE_TWL_M = 3.11
HYBRID_HUANGPU_FULL_RESPONSE_TWL_M = 4.03
HYBRID_HUANGPU_MAX_SCALE = 1.0
HYBRID_HUANGPU_BANKFULL_DEPTH_M = 2.0
HYBRID_HUANGPU_DECAY_DISTANCE_M = 1500.0
HYBRID_HUANGPU_MAX_REACH_M = 5000.0
HYBRID_HUANGPU_MIN_RIVER_DEPTH_M = 0.05
HYBRID_HUANGPU_NODEF_TRIGGER_TWL_M = 0.0
HYBRID_HUANGPU_NODEF_REFERENCE_TWL_M = 0.0
HYBRID_HUANGPU_NODEF_FULL_RESPONSE_TWL_M = 0.0
HYBRID_HUANGPU_NODEF_DECAY_DISTANCE_M = 900.0
HYBRID_HUANGPU_NODEF_MAX_REACH_M = 2500.0
HYBRID_HUANGPU_OPEN_BOUNDARY_REFERENCE_TWL_M = 4.03
HYBRID_HUANGPU_PRIORITY_DISTRICTS = [
    "黄浦区", "徐汇区", "静安区", "虹口区", "杨浦区", "浦东新区",
]

# Hybrid zone segmentation
HYBRID_ZONE_COASTAL_FRINGE_MAX_DISTANCE_M = 15000.0
HYBRID_ZONE_COASTAL_DISTRICTS = [
    "浦东新区", "金山区", "奉贤区", "崇明区", "宝山区",
]

# Defense profiles
DEFENSE_PROFILES = [
    {
        "profile_name": "baseline_nodef",
        "coastal_defense_enabled": False,
        "coastal_defense_crest_m": 0.0,
        "huangpu_template_scenario_tag": "90m_nodef",
        "huangpu_overbank_enabled": True,
        "huangpu_event_driven_enabled": True,
        "huangpu_trigger_twl_m": 0.0,
        "huangpu_reference_twl_m": 0.0,
        "huangpu_full_response_twl_m": 0.0,
    },
    {
        "profile_name": "current_def_gap",
        "coastal_defense_enabled": True,
        "coastal_defense_crest_m": 6.0,
        "huangpu_template_scenario_tag": "90m_def_gap",
        "huangpu_overbank_enabled": True,
        "huangpu_event_driven_enabled": True,
        "huangpu_trigger_twl_m": 2.86,
        "huangpu_reference_twl_m": 3.11,
        "huangpu_full_response_twl_m": 4.03,
    },
]

# ═══════════════════════════════════════════════════════════════════════
# Building Classification & Exposure Parameters
# ═══════════════════════════════════════════════════════════════════════

BUILDING_FLOOR_HEIGHT_M = 3.0
MATCH_DISTANCE_MAX_M = 1000

BUILDING_CATEGORIES = {
    "A_old": {"floors_max": 6,  "age_before": 1990, "function": "residential"},
    "A_new": {"floors_max": 6,  "age_after": 2002,  "function": "residential"},
    "B_old": {"floors_min": 7,  "floors_max": 30, "age_before": 2001, "function": "residential"},
    "B_new": {"floors_min": 7,  "floors_max": 30, "age_after": 2002,  "function": "residential"},
    "C":     {"floors_min": 31, "function": "residential"},
    "D":     {"function": "commercial"},
}

CATEGORY_TO_SURGE_CLASS = {
    "A_old": "low_rise", "A_new": "low_rise",
    "B_old": "mid_rise", "B_new": "mid_rise",
    "C": "high_rise", "D": "commercial",
}

# ═══════════════════════════════════════════════════════════════════════
# Vulnerability Parameters
# ═══════════════════════════════════════════════════════════════════════

# TC wind — Emanuel sigmoid, per-category v_half
TC_IMPACT_V_THRESH = 25.7
TC_IMPACT_INTENSITY_MAX = 180.0
TC_IMPACT_INTENSITY_STEP = 1.0
TC_V_HALF_BASE_SCALE = 1.0  # WP3 regional calibration baseline (Eberenz et al. 2021, TDR).
# Period-matched validation (v6 04b): AAL pred/obs = 0.9999 for 1995-2023.
# Sensitivity band: ±5% around calibrated value (observational uncertainty).
V_HALF_ADJUSTMENT = {
    "A_old": 0.80, "A_new": 0.90, "B_old": 0.95,
    "B_new": 1.00, "C": 1.05, "D": 1.10,
}
IMPF_TC_IDS = {"A_old": 1, "A_new": 2, "B_old": 3, "B_new": 4, "C": 5, "D": 6}

# SS depth-damage — raw HAZUS-MH reference nodes; SURGE_MDR_CALIBRATION_SCALE
# is applied at runtime in 04_vulnerability.py to calibrate for Shanghai RC stock.
# Source: HAZUS-MH Flood Technical Manual depth-damage tables.
SURGE_MDR_CALIBRATION_SCALE = 0.176  # raw HAZUS EAL 88.2B → Shanghai RC 15.5B
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
IMPF_SS_IDS = {"low_rise": 11, "mid_rise": 12, "high_rise": 13, "commercial": 14}

# Wind→surge coupling (per-class kappa dictionary is the active mechanism)
KAPPA = {"low_rise": 0.60, "mid_rise": 0.40, "high_rise": 0.25, "commercial": 0.50}

# Surge value-exposure fractions
SURGE_EXPOSED_FLOOR_EQUIV = {"mid_rise": 1.5, "high_rise": 1.2, "commercial": 2.0}
SURGE_EXPOSED_VALUE_MIN_RATIO = {"mid_rise": 0.08, "high_rise": 0.05, "commercial": 0.12}
SURGE_EXPOSED_VALUE_MAX_RATIO = {"mid_rise": 0.30, "high_rise": 0.20, "commercial": 0.40}

# ═══════════════════════════════════════════════════════════════════════
# Risk & Socio-Economic Modifiers
# ═══════════════════════════════════════════════════════════════════════

GAMMA_SVI = 0.15
TEMP_RISK_ELASTICITY = 0.05
DISTRICT_TC_EVENT_COUNT_WIND_THRESHOLD_MPS = 25.7
DISTRICT_SURGE_EVENT_COUNT_DEPTH_THRESHOLD_M = 0.05

# ═══════════════════════════════════════════════════════════════════════
# Climate Risk Index Parameters
# ═══════════════════════════════════════════════════════════════════════

CLIMATE_INDEX_TREND_WINDOW_MONTHS = 12
CLIMATE_INDEX_WINSORIZE_LOWER = 0.01
CLIMATE_INDEX_WINSORIZE_UPPER = 0.99
CLIMATE_INDEX_COMPONENT_WEIGHTS = {
    "loss_pressure": 0.50, "loss_burden": 0.30, "compound_amplification": 0.20,
}

# Climate-Finance Index
CFI_TREND_YEAR_START = 1993
CFI_TREND_YEAR_END = 2023
CFI_PRICE_YEAR_START = 2015
CFI_PRICE_YEAR_END = 2023
CFI_WEIGHT_PRECIP = 0.25
CFI_WEIGHT_WIND = 0.25
CFI_WEIGHT_HEAT = 0.25
CFI_WEIGHT_SLA = 0.25
CFI_HEAT_BASE_TEMP = 28.0

# CRI (Climate Risk Index) = H × E × V × (1 + κ·S)
CRI_EWMA_ALPHA = 0.85           # EWMA decay for damage signal (half-life ≈ 4 months)
CRI_DAMAGE_KAPPA = 0.5          # max boost from damage channel (+50%)
CRI_EXPOSURE_FLOOR = 0.5        # E_norm lower bound (year with min pop → 0.5)
CRI_VULNERABILITY_FLOOR = 0.5   # V_norm lower bound (year with min ISR → 0.5)
CRI_BASE_INDEX = 100.0          # starting level for the index

# CRI Forward Projection (SDE Monte Carlo, 2024 → 2050)
CRI_PROJECTION_END_YEAR = 2050
CRI_N_SIM = 500
CRI_PROJECTION_CSV = RESULTS_DIR / "shanghai_city_cri_projection.csv"

# SSP scenario drift multipliers on H-trend
# Grounded in IPCC AR6 WG1 Table SPM.1 warming rate ratios:
#   Historical dT ~0.2°C/decade → baseline
#   SSP2-4.5  dT ~0.3°C/decade → 1.5× historical
#   SSP5-8.5  dT ~0.4°C/decade → 2.0× historical
CRI_SSP_H_DRIFT_MULT = {
    "Historical Baseline": 1.0,
    "SSP2-4.5":            1.5,
    "SSP5-8.5":            2.0,
}
# SSP damage adjustments: (λ multiplier, log-severity additive shift)
# Grounded in Knutson et al. 2020 (BAMS):
#   TC frequency: global -14% but WNP +5-25% per 2°C
#   TC intensity: +5% per 2°C warming → PDI +15% (cubed wind)
#   SSP2-4.5 → +0.9°C by 2050: λ×1.05, severity +ln(1.07) ≈ 0.068
#   SSP5-8.5 → +1.3°C by 2050: λ×1.08, severity +ln(1.10) ≈ 0.095
CRI_SSP_DAMAGE_ADJ = {
    "Historical Baseline": (1.00, 0.000),
    "SSP2-4.5":            (1.05, 0.068),
    "SSP5-8.5":            (1.08, 0.095),
}

# ═══════════════════════════════════════════════════════════════════════
# Runtime Environment Setup
# ═══════════════════════════════════════════════════════════════════════

def init_environment():
    """Auto-detect and set GDAL/PROJ env vars. No hardcoded paths."""
    import sys, shutil
    # Try to find GDAL_DATA and PROJ_DATA from conda env.
    # Prefer CONDA_PREFIX; if it is unset (e.g. the interpreter was invoked by
    # absolute path rather than via `conda activate`), infer the environment
    # root from the running interpreter: <env>/python.exe -> <env>.
    conda_prefix = os.environ.get("CONDA_PREFIX", "")
    if not conda_prefix:
        conda_prefix = str(Path(sys.executable).resolve().parent)
    if conda_prefix:
        gdal_path = os.path.join(conda_prefix, "Library", "share", "gdal")
        proj_path = os.path.join(conda_prefix, "Library", "share", "proj")
        if os.path.isdir(gdal_path):
            os.environ.setdefault("GDAL_DATA", gdal_path)
        if os.path.isdir(proj_path):
            os.environ.setdefault("PROJ_DATA", proj_path)
            os.environ.setdefault("PROJ_LIB", proj_path)
    # Ensure output directories
    for d in [OUTPUT_DIR, INTERMEDIATE_DIR, RESULTS_DIR, FIGURES_DIR, LOGS_DIR,
              DEFENSE_SENSITIVITY_DIR, DEFENSE_HAZARD_METRICS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    # Ensure output directories
    for d in [OUTPUT_DIR, INTERMEDIATE_DIR, RESULTS_DIR, FIGURES_DIR, LOGS_DIR,
              DEFENSE_SENSITIVITY_DIR, DEFENSE_HAZARD_METRICS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def apply_sensitivity_overrides():
    """Apply parameter overrides from V8_PARAM_OVERRIDES env var (JSON dict).
    Called by sensitivity runner to vary one parameter at a time."""
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

apply_sensitivity_overrides()
