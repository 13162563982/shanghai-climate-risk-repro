"""
v8 One-Way Sensitivity Analysis Runner
=======================================
Reads sweep config, runs pipeline steps with parameter overrides,
and records output metrics for each variation.

Usage:
    python run_sensitivity.py [--fast-only] [--param PARAM_ID]
    
    --fast-only   Skip sweeps that require C05/C06 (saves ~800s/variation)
    --param X     Only run sweep for parameter X
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

V8_ROOT = Path(__file__).resolve().parent
SWEEP_CONFIG = V8_ROOT / "config" / "sensitivity_sweep.json"
RESULTS_DIR = V8_ROOT / "_sensitivity_results"

CLIMATE_DIR = V8_ROOT / "Climate"
FINANCE_DIR = V8_ROOT / "Finance"
COMPOSITE_DIR = V8_ROOT / "Composite"

# Step → script mapping (must match run_v8.py)
STEP_SCRIPTS = {
    "C04": CLIMATE_DIR / "04_vulnerability.py",
    "C05": CLIMATE_DIR / "05_risk.py",
    "C06": CLIMATE_DIR / "06_defense_sensitivity.py",
    "C07": CLIMATE_DIR / "07_climate_index.py",
    "F01": FINANCE_DIR / "01a_climate_cvar.py",
    "F02": FINANCE_DIR / "01_finance_risk_index.py",
    "F03": FINANCE_DIR / "02_fri_projection.py",
    "X01": COMPOSITE_DIR / "01_composite_index.py",
}

SLOW_STEPS = {"C04", "C05", "C06", "F01"}

# Full ordered pipeline — used for global baseline restore between sweeps
# to prevent cross-sweep contamination (e.g. FRI_WEIGHT_GAP leaves F02/F03
# outputs polluted when a subsequent sweep only restores C05-X01).
FULL_PIPELINE_STEPS = ["C04", "C05", "C06", "C07", "F01", "F02", "F03", "X01"]


def _detect_python():
    """Resolve the interpreter to use.

    Order: V8_PYTHON env var (set by env\\run.ps1) -> the current interpreter.
    No hardcoded environment path: the package must work from any location.
    """
    forced = os.environ.get("V8_PYTHON", "")
    if forced and Path(forced).exists():
        return str(forced)
    return sys.executable


def _require_conda_prefix():
    """Return CONDA_PREFIX, or abort with an actionable message."""
    prefix = os.environ.get("CONDA_PREFIX", "")
    if not prefix or not os.path.isdir(prefix):
        raise SystemExit(
            "CONDA_PREFIX is not set (or does not exist).\n"
            "Run the sensitivity sweep through the packaged entry point instead:\n"
            "    env\\run.ps1 run_sensitivity.py\n"
            "which sets CONDA_PREFIX, PATH, GDAL_DATA/PROJ_DATA and SSL_CERT_FILE."
        )
    return prefix


def _fmt(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else (f"{m}m{s:02d}s" if m else f"{s}s")


def run_steps(steps, overrides, python_exe):
    """Run pipeline steps with parameter overrides. Returns True if all succeed."""
    env = os.environ.copy()
    # Ensure GDAL/PROJ env vars and DLL path are set (conda activation bug)
    conda_prefix = _require_conda_prefix()
    lib_bin = os.path.join(conda_prefix, "Library", "bin")
    lib_share = os.path.join(conda_prefix, "Library", "share")
    env["PATH"] = lib_bin + os.pathsep + env.get("PATH", "")
    env["GDAL_DATA"] = os.path.join(lib_share, "gdal")
    env["PROJ_DATA"] = os.path.join(lib_share, "proj")
    env["PROJ_LIB"] = os.path.join(lib_share, "proj")
    # Fix Windows cert store corruption (#26) — skip broken Windows store,
    # use certifi CA bundle instead (required for C04 TC data fetch).
    env["SSL_CERT_FILE"] = os.path.join(
        conda_prefix, "Lib", "site-packages", "certifi", "cacert.pem"
    )

    if overrides:
        env["V8_PARAM_OVERRIDES"] = json.dumps(overrides)

    # Pre-load GDAL + Arrow DLLs via full path.
    # We intentionally avoid os.add_dll_directory() because it switches Python
    # into secure DLL-search mode, which prevents packages (h5py, rasterio,
    # fiona) from loading their bundled DLLs from sub-package directories.
    _preload_dlls = [
        # These DLLs live in Library/bin and are needed by packages
        # that don't bundle their own copies (fiona, pyarrow).
        'gdal.dll', 'arrow.dll', 'arrow_dataset.dll', 'arrow_acero.dll',
        'arrow_compute.dll', 'arrow_substrait.dll',
        # NOTE: Do NOT preload hdf5.dll — h5py bundles its own version.
        #       Do NOT preload netcdf.dll — netCDF4 bundles its own.
    ]
    _preload_lines = [
        "import ctypes",
        # Monkey-patch: skip broken Windows certificate store
        "import ssl",
        "ssl.SSLContext._load_windows_store_certs = lambda *a, **kw: None",
    ]
    for _dll in _preload_dlls:
        _dll_path = os.path.join(lib_bin, _dll)
        if os.path.exists(_dll_path):
            _preload_lines.append(f"ctypes.CDLL(r'{_dll_path}')")
    gdal_preload = ";".join(_preload_lines) + ";"

    for step_id in steps:
        script = STEP_SCRIPTS.get(step_id)
        if script is None or not script.exists():
            print(f"    [SKIP] {step_id} — script not found")
            continue
        # Run with GDAL DLL preload and proper __file__ for the script
        script_str = str(script).replace('\\', '\\\\')
        full_cmd = (
            f'"{python_exe}" -c "'
            f'{gdal_preload}'
            f'__file__ = r\'{script_str}\';'
            f'exec(open(__file__, encoding=\'utf-8\').read())"'
        )
        result = subprocess.run(
            full_cmd,
            cwd=str(script.parent),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=True,
        )
        if result.returncode != 0:
            print(f"    [FAIL] {step_id}: {result.stderr[-200:] if result.stderr else 'unknown error'}")
            return False
    return True


def extract_metrics():
    """Extract key output metrics from current v8 outputs."""
    metrics = {}

    # CRI projection — p50 at 2050
    cri_csv = CLIMATE_DIR / "output" / "results" / "shanghai_city_cri_projection.csv"
    if cri_csv.exists():
        df = pd.read_csv(cri_csv)
        for sc in df["scenario"].unique():
            sub = df[df["scenario"] == sc]
            last = sub.iloc[-1]
            metrics[f"CRI_2050_p50_{sc}"] = float(last.get("cri_index_p50", np.nan))
            metrics[f"CRI_2050_rep_{sc}"] = float(last.get("cri_index_rep", np.nan))

    # FRI projection — p50 at 2050
    fri_csv = FINANCE_DIR / "output" / "results" / "shanghai_fri_projection.csv"
    if fri_csv.exists():
        df = pd.read_csv(fri_csv)
        for sc in df["scenario"].unique():
            sub = df[df["scenario"] == sc]
            last = sub.iloc[-1]
            metrics[f"FRI_2050_p50_{sc}"] = float(last.get("fri_index_p50", np.nan))

    # CFCI projection — p50 at 2050
    cfci_csv = COMPOSITE_DIR / "output" / "results" / "shanghai_cfci_projection.csv"
    if cfci_csv.exists():
        df = pd.read_csv(cfci_csv)
        for sc in df["scenario"].unique():
            sub = df[df["scenario"] == sc]
            last = sub.iloc[-1]
            metrics[f"CFCI_2050_p50_{sc}"] = float(last.get("cfci_p50", np.nan))

    # Risk panel — total city EAL (baseline scenario)
    risk_csv = CLIMATE_DIR / "output" / "results" / "risk_panel_all_scenarios_high_confidence.csv"
    if risk_csv.exists():
        df = pd.read_csv(risk_csv)
        eal_col = "EAL_compound" if "EAL_compound" in df.columns else "risk_total"
        for sc in df["scenario"].unique():
            sub = df[df["scenario"] == sc]
            eal = float(sub[eal_col].sum())
            metrics[f"EAL_total_{sc}"] = eal
            # Wind/surge channel breakdown
            if "risk_wind_channel" in df.columns:
                metrics[f"EAL_wind_{sc}"] = float(sub["risk_wind_channel"].sum())
            if "risk_surge_channel" in df.columns:
                metrics[f"EAL_surge_{sc}"] = float(sub["risk_surge_channel"].sum())
            if "wind_share" in df.columns:
                metrics[f"wind_share_mean_{sc}"] = float(sub["wind_share"].mean())
            if "surge_share" in df.columns:
                metrics[f"surge_share_mean_{sc}"] = float(sub["surge_share"].mean())

    # Climate CVaR — for TC vulnerability propagation check
    cvar_csv = FINANCE_DIR / "output" / "results" / "shanghai_climate_cvar_monthly.csv"
    if cvar_csv.exists():
        df = pd.read_csv(cvar_csv)
        if "cvar_5pct" in df.columns:
            metrics["CVaR_mean"] = float(df["cvar_5pct"].mean())
            metrics["CVaR_max"] = float(df["cvar_5pct"].max())

    # Defense EAL
    def_csv = CLIMATE_DIR / "output" / "results" / "defense_sensitivity" / "defense_profile_eal.csv"
    if def_csv.exists():
        df = pd.read_csv(def_csv)
        eal_col = "EAL_compound" if "EAL_compound" in df.columns else "risk_total"
        for sc in df["scenario"].unique():
            for prof in df["defense_profile"].unique():
                sub = df[(df["scenario"] == sc) & (df["defense_profile"] == prof)]
                metrics[f"DEF_EAL_{sc}_{prof}"] = float(sub[eal_col].sum())

    return metrics


def main():
    parser = argparse.ArgumentParser(description="v8 sensitivity sweep runner")
    parser.add_argument("--fast-only", action="store_true",
                        help="Skip sweeps requiring C05/C06")
    parser.add_argument("--param", default=None,
                        help="Only run sweep for this parameter ID")
    parser.add_argument("--python", default=_detect_python())
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    with open(SWEEP_CONFIG, "r", encoding="utf-8") as f:
        config = json.load(f)

    sweeps = config["sweeps"]
    if args.param:
        sweeps = [s for s in sweeps if s["id"] == args.param]
        if not sweeps:
            print(f"Unknown param: {args.param}")
            sys.exit(1)

    if args.fast_only:
        sweeps = [s for s in sweeps if not any(st in SLOW_STEPS for st in s["steps"])]

    print(f"v8 Sensitivity Analysis")
    print(f"Python: {args.python}")
    print(f"Sweeps: {len(sweeps)} parameters")
    print(f"Output: {RESULTS_DIR}")
    print()

    all_records = []
    t_total = time.time()

    # Extract baseline metrics first (no overrides)
    print("─── Baseline metrics ───")
    baseline_metrics = extract_metrics()
    for k, v in sorted(baseline_metrics.items()):
        if "p50" in k or "EAL_total" in k:
            print(f"  {k}: {v:.2f}")
    print()

    # Restore baseline state before each sweep to prevent cross-contamination.
    # Always run the FULL pipeline with no overrides so that outputs from a
    # prior sweep (e.g. F02/F03 from FRI_WEIGHT_GAP) do not leak into the
    # current sweep's metrics.
    def restore_baseline():
        """Re-run full pipeline with no overrides to reset ALL outputs."""
        return run_steps(FULL_PIPELINE_STEPS, {}, args.python)

    try:
        for sweep in sweeps:
            sweep_id = sweep["id"]
            attr = sweep["config_attr"]
            steps = sweep["steps"]
            desc = sweep.get("description", "")
            is_slow = any(st in SLOW_STEPS for st in steps)

            # Reset ALL intermediate outputs to baseline before this sweep
            print(f"  Restoring full baseline (all steps)...")
            restore_baseline()

            print(f"{'=' * 60}")
            print(f"  {sweep_id}: {desc}")
            print(f"  Steps: {steps} {'(SLOW)' if is_slow else '(fast)'}")
            print(f"{'=' * 60}")

            # Determine values to test
            if "values_tuples" in sweep:
                # Tuple parameter (e.g., FRI_WEIGHTS)
                variations = sweep["values_tuples"]
                labels = [str(v) for v in variations]
            else:
                variations = sweep["values"]
                labels = [str(v) for v in variations]

            for i, (val, label) in enumerate(zip(variations, labels)):
                is_baseline = (val == sweep.get("baseline"))
                tag = " (baseline)" if is_baseline else ""

                print(f"\n  [{i+1}/{len(variations)}] {attr} = {label}{tag}")
                t0 = time.time()

                if "values_tuples" in sweep:
                    overrides = {attr: tuple(val)}
                else:
                    overrides = {attr: val}

                ok = run_steps(steps, overrides, args.python)
                elapsed = time.time() - t0

                if not ok:
                    print(f"    FAILED ({_fmt(elapsed)})")
                    continue

                metrics = extract_metrics()
                print(f"    OK ({_fmt(elapsed)})")

                # Record
                record = {
                    "sweep_id": sweep_id,
                    "config_attr": attr,
                    "value": label,
                    "is_baseline": is_baseline,
                    "elapsed_s": round(elapsed, 1),
                }
                record.update(metrics)
                all_records.append(record)

                # Show key metrics vs baseline
                for key in ["CRI_2050_p50_Historical Baseline",
                            "FRI_2050_p50_Historical Baseline",
                            "CFCI_2050_p50_Historical Baseline"]:
                    if key in metrics and key in baseline_metrics:
                        bv = baseline_metrics[key]
                        mv = metrics[key]
                        pct = 100.0 * (mv - bv) / bv if bv != 0 else 0
                        print(f"    {key.split('_')[0]} p50: {mv:.1f} ({pct:+.1f}%)")

            print()
    finally:
        if sweeps:
            print("Restoring full baseline after all sweeps...")
            if not restore_baseline():
                print("WARNING: final baseline restore failed; output files may remain contaminated")

    # Save results
    elapsed_total = time.time() - t_total
    results_df = pd.DataFrame(all_records)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = RESULTS_DIR / f"sensitivity_results_{ts}.csv"
    results_df.to_csv(str(out_csv), index=False, encoding="utf-8-sig")
    print(f"\n{'=' * 60}")
    print(f"Sensitivity sweep complete ({_fmt(elapsed_total)})")
    print(f"Results: {out_csv}")
    print(f"Records: {len(results_df)}")
    print(f"{'=' * 60}")

    # Also save latest
    results_df.to_csv(str(RESULTS_DIR / "sensitivity_latest.csv"), index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
