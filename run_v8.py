"""
v8 Full-Pipeline Orchestrator
==============================
Runs Climate → Finance → Composite in sequence with:
  - Step-level timing and profiling
  - Progress heartbeat to JSONL log
  - Skip-if-cached support (--skip-cached)
  - From/to/only step filtering
  - Post-run regression test (--strict-compare)
"""

import argparse, json, subprocess, sys, time
from datetime import datetime
from pathlib import Path

V8_ROOT = Path(__file__).resolve().parent
CLIMATE_DIR = V8_ROOT / "Climate"
FINANCE_DIR = V8_ROOT / "Finance"
COMPOSITE_DIR = V8_ROOT / "Composite"
LOG_DIR = V8_ROOT / "_v8_logs"

STEPS = [
    # (id, script_path, description)
    ("C01", CLIMATE_DIR / "01_hazard_tc.py",           "TC wind hazard"),
    ("C03", CLIMATE_DIR / "03_exposure.py",            "Building exposure"),
    ("C02", CLIMATE_DIR / "02_hazard_surge.py",        "Storm surge hazard"),
    ("C04", CLIMATE_DIR / "04_vulnerability.py",       "Vulnerability functions"),
    ("C05", CLIMATE_DIR / "05_risk.py",                "Compound risk calculation"),
    ("C06", CLIMATE_DIR / "06_defense_sensitivity.py", "Defense sensitivity"),
    ("C07", CLIMATE_DIR / "07_climate_index.py",       "Climate Risk Index"),
    ("F01", FINANCE_DIR / "01a_climate_cvar.py",       "Climate CVaR"),
    ("F02", FINANCE_DIR / "01_finance_risk_index.py",  "Finance Risk Index"),
    ("F03", FINANCE_DIR / "02_fri_projection.py",      "FRI MC projection"),
    ("X01", COMPOSITE_DIR / "01_composite_index.py",   "CFCI composite"),
]


def _fmt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else (f"{m}m{s:02d}s" if m else f"{s}s")


def run_step(step_id, script_path, description, python_exe, log_path):
    if not script_path.exists():
        print(f"  [SKIP] {script_path.name} not found")
        return None
    print(f"\n{'=' * 60}")
    print(f"  [{step_id}] {description}  ({script_path.name})")
    print(f"{'=' * 60}")

    t0 = time.time()
    result = subprocess.run(
        [python_exe, str(script_path)],
        cwd=str(script_path.parent),
        env=None,
    )
    elapsed = time.time() - t0

    record = {
        "step_id": step_id,
        "script": script_path.name,
        "description": description,
        "elapsed_s": round(elapsed, 2),
        "return_code": result.returncode,
        "ts": datetime.now().isoformat(),
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    if result.returncode != 0:
        print(f"  [FAIL] {script_path.name} (exit {result.returncode}, {_fmt(elapsed)})")
        return False
    print(f"  [OK] {script_path.name} ({_fmt(elapsed)})")
    return True


def main():
    parser = argparse.ArgumentParser(description="v8 full pipeline orchestrator")
    parser.add_argument("--from", dest="from_step", default=None)
    parser.add_argument("--to", dest="to_step", default=None)
    parser.add_argument("--only", default=None)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--strict-compare", action="store_true",
                        help="Run regression test after pipeline")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

    print(f"v8 Pipeline Orchestrator")
    print(f"Python: {args.python}")
    print(f"Log: {log_path}")

    step_ids = [s[0] for s in STEPS]

    if args.only:
        steps_to_run = [(sid, p, d) for sid, p, d in STEPS if sid == args.only]
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

    print(f"Steps: {[s[0] for s in steps_to_run]}")
    t_total = time.time()
    timings = {}
    failed = []

    for sid, path, desc in steps_to_run:
        ok = run_step(sid, path, desc, args.python, log_path)
        if ok is None:
            continue
        if not ok:
            failed.append(sid)
            print(f"\n[ABORT] Pipeline stopped at {sid}")
            break

    elapsed_total = time.time() - t_total
    print(f"\n{'=' * 60}")
    if failed:
        print(f"Pipeline FAILED at: {failed}")
    else:
        print(f"Pipeline COMPLETE ({_fmt(elapsed_total)})")
    print(f"{'=' * 60}")

    # Optional regression test
    if args.strict_compare and not failed:
        print("\n[Regression] Running strict v8 baseline comparison...")
        reg = subprocess.run(
            [args.python, str(V8_ROOT / "_regression_test.py")],
            cwd=str(V8_ROOT),
        )
        if reg.returncode != 0:
            print("[Regression] FAILED — v8 outputs differ from baseline")
            sys.exit(2)
        print("[Regression] PASSED")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
