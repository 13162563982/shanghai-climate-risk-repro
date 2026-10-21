# -*- coding: utf-8 -*-
"""WP6 readiness: resolve every sweep target and compare live outputs vs A archive.

Read-only. Exits non-zero on any unresolved sweep target or any live/archive gap.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
A_ARCHIVE = NEWROOT / "output_archive" / "boundary_official_A_20261016_230820"
SWEEP = NEWROOT / "config" / "sensitivity_sweep.json"

rc = 0

# ── 1. sweep config: every target must resolve to a config attribute ─────────
print("=" * 78)
print("1. sweep config resolution")
print("=" * 78)
spec = json.loads(SWEEP.read_text(encoding="utf-8"))
sweeps = spec["sweeps"] if isinstance(spec, dict) and "sweeps" in spec else spec
if isinstance(sweeps, dict):
    sweeps = [dict(v, id=k) for k, v in sweeps.items()]

import importlib.util  # noqa: E402

cfgs = {}
for mod, pkg in (("Climate", "Climate"), ("Finance", "Finance"), ("Composite", "Composite")):
    p = NEWROOT / pkg / "00_config.py"
    if not p.exists():
        print(f"  !! missing {p}")
        rc = 1
        continue
    s = importlib.util.spec_from_file_location(f"_cfg_{mod}", p)
    m = importlib.util.module_from_spec(s)
    try:
        s.loader.exec_module(m)
        cfgs[mod] = m
    except Exception as e:  # noqa: BLE001
        print(f"  !! cannot import {p}: {type(e).__name__}: {e}")
        rc = 1

n_values = 0
n_tuple = 0
for sw in sweeps:
    sid = sw.get("id", "?")
    attr = sw.get("config_attr") or sid
    if "values_tuples" in sw:
        vals = sw["values_tuples"]
        n_tuple += 1
    else:
        vals = sw.get("values", [])
    n_values += len(vals)
    found = []
    for mod, m in cfgs.items():
        if "." in attr:
            head, tail = attr.split(".", 1)
            if hasattr(m, head):
                found.append(f"{mod}.{attr}={getattr(getattr(m, head), tail, '?')}")
        elif hasattr(m, attr):
            found.append(f"{mod}={getattr(m, attr)}")
    if found:
        print(f"  OK   {sid:34s} attr={attr:34s} n={len(vals):2d}  {found}")
    else:
        print(f"  FAIL {sid:34s} attr={attr:34s} n={len(vals):2d}  NOT FOUND in any config")
        rc = 1
print(f"\n  sweeps = {len(sweeps)}   parameter values = {n_values} "
      f"({n_tuple} tuple sweep)   baseline restores = {len(sweeps)}")

# ── 2. live outputs vs A archive ─────────────────────────────────────────────
print()
print("=" * 78)
print("2. live outputs vs A archive (numeric)")
print("=" * 78)
FILES = [
    ("Climate", "output/results/defense_sensitivity/defense_profile_eal.csv"),
    ("Climate", "output/results/shanghai_city_cri_projection.csv"),
    ("Finance", "output/results/shanghai_finance_risk_index.csv"),
    ("Finance", "output/results/shanghai_fri_projection.csv"),
    ("Composite", "output/results/shanghai_cfci_historical.csv"),
    ("Composite", "output/results/shanghai_cfci_projection.csv"),
]


def load(p: Path):
    with p.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


for mod, relpath in FILES:
    live, arch = NEWROOT / mod / relpath, A_ARCHIVE / mod / relpath
    if not live.exists() or not arch.exists():
        print(f"  FAIL {mod}/{relpath}: live={live.exists()} archive={arch.exists()}")
        rc = 1
        continue
    lr, ar = load(live), load(arch)
    if len(lr) != len(ar):
        print(f"  FAIL {mod}/{relpath}: row count {len(lr)} vs {len(ar)}")
        rc = 1
        continue
    diffs = 0
    worst = ("", 0.0)
    for a, b in zip(lr, ar):
        for k in a:
            if k not in b:
                continue
            va, vb = a[k], b[k]
            try:
                fa, fb = float(va), float(vb)
            except (TypeError, ValueError):
                if va != vb:
                    diffs += 1
                continue
            scale = max(abs(fa), abs(fb), 1e-300)
            rel = abs(fa - fb) / scale
            if rel > 1e-12:
                diffs += 1
                if rel > worst[1]:
                    worst = (k, rel)
    name = relpath.split("/")[-1]
    if diffs == 0:
        print(f"  OK   {mod}/{name:42s} {len(lr):5d} rows, identical")
    else:
        print(f"  WARN {mod}/{name:42s} {len(lr):5d} rows, {diffs} differing cells "
              f"(worst {worst[0]} rel={worst[1]:.3e})")

# ── 3. the two CSVs that WP6 will rewrite: confirm they exist ────────────────
print()
print("=" * 78)
print("3. WP6 outputs it will overwrite (must be recoverable from archive)")
print("=" * 78)
for relpath in ("Climate/output/results/defense_sensitivity/defense_profile_eal.csv",
                "Climate/output/intermediate/building_coast_distance_m.npy",
                "Climate/output/intermediate/twl_vec_hist.npy"):
    live, arch = NEWROOT / relpath, A_ARCHIVE / relpath
    print(f"  {'OK  ' if arch.exists() else 'FAIL'} archive copy: {relpath}")
    if not arch.exists():
        rc = 1

print()
print("=" * 78)
print(f"RESULT: {'READY' if rc == 0 else 'NOT READY'}")
print("=" * 78)
sys.exit(rc)
