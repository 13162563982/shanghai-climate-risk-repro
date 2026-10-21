"""Ad-hoc, read-only schema dump of the pipeline result CSVs.

Used to pin down column names before writing the G4 comparison.
Writes nothing.

    env\\run.ps1 tools\\_inspect_outputs.py
"""

import os
from pathlib import Path

import pandas as pd

NEWROOT = Path(__file__).resolve().parent.parent

TARGETS = [
    r"Climate\output\results\defense_sensitivity\defense_profile_eal.csv",
    r"Climate\output\results\shanghai_city_cri_projection.csv",
    r"Climate\output\results\shanghai_city_monthly_climate_hazard.csv",
    r"Finance\output\results\shanghai_finance_risk_index.csv",
    r"Finance\output\results\shanghai_fri_projection.csv",
    r"Composite\output\results\shanghai_cfci_historical.csv",
    r"Composite\output\results\shanghai_cfci_projection.csv",
]

for rel in TARGETS:
    p = NEWROOT / rel
    if not p.exists():
        print("=" * 72)
        print(f"MISSING {rel}")
        continue
    df = pd.read_csv(p)
    print("=" * 72)
    print(f"{rel}  | rows={len(df)}")
    print(f"  cols: {list(df.columns)}")
    print(df.head(2).to_string(index=False)[:500])
    if "date" in df.columns:
        print(f"  date range: {df['date'].min()} .. {df['date'].max()}")
    if "scenario" in df.columns:
        print(f"  scenarios: {sorted(df['scenario'].unique())}")
    if "defense_profile" in df.columns:
        print(f"  profiles: {sorted(df['defense_profile'].unique())}  districts={df['district'].nunique() if 'district' in df.columns else 'n/a'}")
    print()
