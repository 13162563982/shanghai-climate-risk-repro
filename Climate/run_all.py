# === run_all.py ===
# ⚠️ NON-AUTHORITATIVE ENTRY POINT — Climate module only (no Finance/Composite).
#    The authoritative orchestrator for the full 11-step pipeline is
#    run_v8.py at the package root. Use that for anything that will be reported.
# Pipeline orchestrator — runs all computation steps in dependency order
# Usage: python run_all.py [--from STEP] [--to STEP] [--only STEP]
#
# Execution order:
#   01_hazard_tc  → 03_exposure → 02_hazard_surge → 04_vulnerability
#   → 05_risk → 06_defense_sensitivity → 07_climate_index
#   → generate_figures_new

import argparse
import importlib.util
import subprocess
import sys
import time
from pathlib import Path

CLIMATE_DIR = Path(__file__).resolve().parent

STEPS = [
    ("01", "01_hazard_tc.py",          "TC wind hazard"),
    ("03", "03_exposure.py",           "Building exposure"),
    ("02", "02_hazard_surge.py",       "Storm surge hazard"),
    ("04", "04_vulnerability.py",      "Vulnerability functions"),
    ("05", "05_risk.py",               "Compound risk calculation"),
    ("06", "06_defense_sensitivity.py","Defense sensitivity analysis"),
    ("07", "07_climate_index.py",      "Climate hazard index"),
    ("fig","generate_figures_new.py",  "Figure generation"),
]


def run_step(script_name, description, python_exe):
    script_path = CLIMATE_DIR / script_name
    if not script_path.exists():
        print(f"  [SKIP] {script_name} not found")
        return False
    print(f"\n{'='*60}")
    print(f"  Running: {description} ({script_name})")
    print(f"{'='*60}")
    t0 = time.time()
    result = subprocess.run(
        [python_exe, str(script_path)],
        cwd=str(CLIMATE_DIR),
        env=None,  # inherit environment
    )
    elapsed = time.time() - t0
    if result.returncode != 0:
        print(f"  [FAIL] {script_name} exited with code {result.returncode} ({elapsed:.0f}s)")
        return False
    print(f"  [OK] {script_name} ({elapsed:.0f}s)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Run v8 computation pipeline")
    parser.add_argument("--from", dest="from_step", default=None,
                        help="Start from this step (e.g. 02, 05, fig)")
    parser.add_argument("--to", dest="to_step", default=None,
                        help="Stop after this step")
    parser.add_argument("--only", default=None,
                        help="Run only this step")
    parser.add_argument("--python", default=sys.executable,
                        help="Python executable to use")
    args = parser.parse_args()

    print(f"Python: {args.python}")
    print(f"Working dir: {CLIMATE_DIR}")

    step_ids = [s[0] for s in STEPS]

    if args.only:
        steps_to_run = [(sid, name, desc) for sid, name, desc in STEPS if sid == args.only]
        if not steps_to_run:
            print(f"Unknown step: {args.only}. Available: {step_ids}")
            sys.exit(1)
    else:
        start_idx = 0
        end_idx = len(STEPS)
        if args.from_step:
            try:
                start_idx = step_ids.index(args.from_step)
            except ValueError:
                print(f"Unknown step: {args.from_step}. Available: {step_ids}")
                sys.exit(1)
        if args.to_step:
            try:
                end_idx = step_ids.index(args.to_step) + 1
            except ValueError:
                print(f"Unknown step: {args.to_step}. Available: {step_ids}")
                sys.exit(1)
        steps_to_run = STEPS[start_idx:end_idx]

    print(f"\nSteps: {[s[0] for s in steps_to_run]}")
    t_total = time.time()
    failed = []

    for sid, name, desc in steps_to_run:
        ok = run_step(name, desc, args.python)
        if not ok:
            failed.append(name)
            print(f"\n[ABORT] Pipeline stopped at {name}")
            break

    elapsed_total = time.time() - t_total
    print(f"\n{'='*60}")
    if failed:
        print(f"Pipeline FAILED at: {failed}")
    else:
        print(f"Pipeline COMPLETE ({elapsed_total:.0f}s)")
    print(f"{'='*60}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
