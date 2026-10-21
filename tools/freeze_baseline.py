"""
Freeze v8 baseline manifest.
Records file hashes, shapes, column names, date ranges, and key statistics
for all authoritative output products. This manifest is the single source
of truth for strict numerical equivalence verification in future runs.
"""

import hashlib, json, os, sys, time
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
NEWROOT = Path(__file__).resolve().parent.parent
CLIMATE_RESULTS = NEWROOT / "Climate" / "output" / "results"
CLIMATE_INTERMEDIATE = NEWROOT / "Climate" / "output" / "intermediate"
FINANCE_RESULTS = NEWROOT / "Finance" / "output" / "results"
FINANCE_INTERMEDIATE = NEWROOT / "Finance" / "output" / "intermediate"
COMPOSITE_RESULTS = NEWROOT / "Composite" / "output" / "results"

# Default manifest location; override with --out (WP4 archives it under
# output_archive/baseline_legacy_<ts>/MANIFEST.json).
MANIFEST_PATH = NEWROOT / "docs" / "_基线清单.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def csv_summary(path: Path) -> dict:
    df = pd.read_csv(path)
    info = {
        "sha256": sha256_file(path),
        "rows": len(df),
        "columns": list(df.columns),
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "size_bytes": path.stat().st_size,
    }
    # Date range detection
    for col in ("date", "Date", "month", "year_month"):
        if col in df.columns:
            vals = df[col].dropna()
            if len(vals) > 0:
                info["date_min"] = str(vals.min())
                info["date_max"] = str(vals.max())
            break
    # Numeric summary for all float columns
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if num_cols:
        desc = df[num_cols].describe().to_dict()
        # Convert numpy types for JSON serialization
        info["numeric_summary"] = {
            col: {k: float(v) for k, v in stats.items()}
            for col, stats in desc.items()
        }
    return info


def npz_summary(path: Path) -> dict:
    info = {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}
    data = np.load(path)
    arrays = {}
    for key in data.files:
        arr = data[key]
        entry = {
            "shape": list(arr.shape),
            "dtype": str(arr.dtype),
        }
        if np.issubdtype(arr.dtype, np.number) and arr.size > 0:
            entry["min"] = float(np.nanmin(arr))
            entry["max"] = float(np.nanmax(arr))
            entry["mean"] = float(np.nanmean(arr))
            entry["std"] = float(np.nanstd(arr))
        elif arr.size > 0 and arr.dtype.kind in ("U", "S", "O"):
            entry["first"] = str(arr.flat[0])
            entry["last"] = str(arr.flat[-1])
            entry["n_unique"] = int(len(set(arr.flat)))
        arrays[key] = entry
    info["arrays"] = arrays
    return info


def hdf5_summary(path: Path) -> dict:
    """Basic HDF5 metadata. h5py may fail on non-ASCII paths on Windows."""
    info = {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}
    try:
        import h5py
        # On Windows, h5py's C layer may choke on non-ASCII paths.
        # Copy to a temp file with an ASCII name as a workaround.
        import tempfile, shutil
        with tempfile.NamedTemporaryFile(suffix=".hdf5", delete=False) as tmp:
            tmp_path = tmp.name
        shutil.copy2(str(path), tmp_path)
        try:
            with h5py.File(tmp_path, "r") as f:
                info["keys"] = list(f.keys())
                for key in f.keys():
                    ds = f[key]
                    if hasattr(ds, "shape"):
                        info[f"{key}_shape"] = list(ds.shape)
                        info[f"{key}_dtype"] = str(ds.dtype)
        finally:
            os.unlink(tmp_path)
    except Exception as exc:
        info["_hdf5_inspect_error"] = str(exc)
    return info


def npy_summary(path: Path) -> dict:
    info = {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}
    arr = np.load(path)
    info["shape"] = list(arr.shape)
    info["dtype"] = str(arr.dtype)
    info["min"] = float(np.nanmin(arr)) if arr.size > 0 else None
    info["max"] = float(np.nanmax(arr)) if arr.size > 0 else None
    info["mean"] = float(np.nanmean(arr)) if arr.size > 0 else None
    return info


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Freeze a numerical manifest of key output products")
    ap.add_argument("--out", default=str(MANIFEST_PATH),
                    help="manifest JSON path (default: <NEWROOT>/docs/_基线清单.json)")
    args = ap.parse_args()
    # Relative --out is resolved against the PACKAGE ROOT, not the process CWD:
    # env\bootstrap.py chdirs into the target script's directory, so a relative
    # path given on the command line would otherwise land under tools\.
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = NEWROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    manifest = {
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "newroot": str(NEWROOT),
        "products": {},
    }

    # ── Climate CSV results ──
    climate_csvs = [
        "risk_panel_all_scenarios_high_confidence.csv",
        "risk_panel_high_confidence.csv",
        "shanghai_city_monthly_climate_hazard.csv",
        "shanghai_city_cri_projection.csv",
        "tc_date_alignment_audit.csv",
    ]
    for name in climate_csvs:
        p = CLIMATE_RESULTS / name
        if p.exists():
            print(f"  CSV  {name} ... ", end="", flush=True)
            manifest["products"][f"Climate/results/{name}"] = csv_summary(p)
            print("OK")

    # Defense sensitivity CSV
    def_eal = CLIMATE_RESULTS / "defense_sensitivity" / "defense_profile_eal.csv"
    if def_eal.exists():
        print(f"  CSV  defense_profile_eal.csv ... ", end="", flush=True)
        manifest["products"]["Climate/results/defense_sensitivity/defense_profile_eal.csv"] = csv_summary(def_eal)
        print("OK")

    # ── Climate NPZ results (MC paths) ──
    for name in ["cri_mc_paths_baseline.npz", "cri_mc_paths_ssp245.npz", "cri_mc_paths_ssp585.npz"]:
        p = CLIMATE_RESULTS / name
        if p.exists():
            print(f"  NPZ  {name} ... ", end="", flush=True)
            manifest["products"][f"Climate/results/{name}"] = npz_summary(p)
            print("OK")

    # ── Climate HDF5 intermediates ──
    hdf5_files = [
        "haz_TC_hist.hdf5", "haz_TC_synth.hdf5", "haz_TC_ssp245.hdf5", "haz_TC_ssp585.hdf5",
        "haz_SS_hist.hdf5", "haz_SS_synth.hdf5", "haz_SS_ssp245.hdf5", "haz_SS_ssp585.hdf5",
    ]
    for name in hdf5_files:
        p = CLIMATE_INTERMEDIATE / name
        if p.exists():
            print(f"  HDF5 {name} ... ", end="", flush=True)
            manifest["products"][f"Climate/intermediate/{name}"] = hdf5_summary(p)
            print("OK")

    # ── Climate NPY intermediates ──
    npy_files = [
        "twl_vec_hist.npy", "twl_vec_synth.npy",
        "building_elevation.npy", "building_coast_distance_m.npy",
        "building_huangpu_overbank_template_m.npy",
    ]
    for name in npy_files:
        p = CLIMATE_INTERMEDIATE / name
        if p.exists():
            print(f"  NPY  {name} ... ", end="", flush=True)
            manifest["products"][f"Climate/intermediate/{name}"] = npy_summary(p)
            print("OK")

    # ── Finance CSV results ──
    finance_csvs = [
        "shanghai_climate_cvar_monthly.csv",
        "shanghai_finance_risk_index.csv",
        "shanghai_fri_projection.csv",
    ]
    for name in finance_csvs:
        p = FINANCE_RESULTS / name
        if p.exists():
            print(f"  CSV  {name} ... ", end="", flush=True)
            manifest["products"][f"Finance/results/{name}"] = csv_summary(p)
            print("OK")

    # ── Finance NPZ results (MC paths) ──
    for name in ["fri_mc_paths_baseline.npz", "fri_mc_paths_ssp245.npz", "fri_mc_paths_ssp585.npz"]:
        p = FINANCE_RESULTS / name
        if p.exists():
            print(f"  NPZ  {name} ... ", end="", flush=True)
            manifest["products"][f"Finance/results/{name}"] = npz_summary(p)
            print("OK")

    # ── Finance HDF5 intermediates ──
    cvar_hdf5 = FINANCE_INTERMEDIATE / "haz_TC_cvar_N100.hdf5"
    if cvar_hdf5.exists():
        print(f"  HDF5 haz_TC_cvar_N100.hdf5 ... ", end="", flush=True)
        manifest["products"]["Finance/intermediate/haz_TC_cvar_N100.hdf5"] = hdf5_summary(cvar_hdf5)
        print("OK")

    # ── Composite CSV results ──
    composite_csvs = [
        "shanghai_cfci_historical.csv",
        "shanghai_cfci_projection.csv",
    ]
    for name in composite_csvs:
        p = COMPOSITE_RESULTS / name
        if p.exists():
            print(f"  CSV  {name} ... ", end="", flush=True)
            manifest["products"][f"Composite/results/{name}"] = csv_summary(p)
            print("OK")

    # ── Key config parameters (frozen snapshot) ──
    manifest["config_snapshot"] = {
        "RANDOM_SEED": 42,
        "NB_SYNTH_TRACKS": 10,
        "TC_WIND_MODEL": "H10",
        "MODEL_RESOLUTION_DEG": 0.01,
        "KAPPA": {"low_rise": 0.60, "mid_rise": 0.40, "high_rise": 0.25, "commercial": 0.50},
        "SURGE_MDR_CALIBRATION_SCALE": 0.176,
        "TC_V_HALF_BASE_SCALE": 1.0,
        "TC_IMPACT_V_THRESH": 25.7,
        "V_HALF_ADJUSTMENT": {"A_old": 0.80, "A_new": 0.90, "B_old": 0.95, "B_new": 1.00, "C": 1.05, "D": 1.10},
        "GAMMA_SVI": 0.15,
        "CRI_EWMA_ALPHA": 0.85,
        "CRI_DAMAGE_KAPPA": 0.5,
        "CRI_N_SIM": 500,
        "CRI_SSP_H_DRIFT_MULT": {"Historical Baseline": 1.0, "SSP2-4.5": 1.5, "SSP5-8.5": 2.0},
        "HP_LAMBDA": 129600,
        "VOLATILITY_WINDOW": 12,
        "FRI_WEIGHTS": [1/3, 1/3, 1/3],
        "FRI_N_SIM": 500,
        "CFCI_TARGET_RHO": 0.411,
        "CFCI_METHOD": "geometric_mean",
        "DEFENSE_PROFILES": ["baseline_nodef(0m)", "current_def_gap(6m)"],
    }

    elapsed = time.time() - t0
    manifest["elapsed_seconds"] = round(elapsed, 1)
    print(f"\nTotal products catalogued: {len(manifest['products'])}")
    print(f"Elapsed: {elapsed:.1f}s")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"Manifest written to {out_path}")


if __name__ == "__main__":
    main()
