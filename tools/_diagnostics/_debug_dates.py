"""Ad-hoc debug: inspect the date column dtypes/values of the projection CSVs."""

from pathlib import Path

import pandas as pd

NEWROOT = Path(__file__).resolve().parent.parent
CLIMATE_RESULTS = NEWROOT / "Climate" / "output" / "results"
FINANCE_RESULTS = NEWROOT / "Finance" / "output" / "results"
COMPOSITE_RESULTS = NEWROOT / "Composite" / "output" / "results"

for rel in [
    r"Climate\output\results\shanghai_city_cri_projection.csv",
    r"Finance\output\results\shanghai_fri_projection.csv",
    r"Composite\output\results\shanghai_cfci_projection.csv",
    r"Composite\output\results\shanghai_cfci_historical.csv",
]:
    df = pd.read_csv(NEWROOT / rel)
    d = df["date"]
    print("=" * 70)
    print(rel)
    print(f"  dtype      : {d.dtype}")
    print(f"  first/last : {d.iloc[0]!r} / {d.iloc[-1]!r}")
    print(f"  last 3     : {list(d.tail(3))}")
    print(f"  == '2050-12-01' hits: {(d == '2050-12-01').sum()}")
    if "scenario" in df.columns:
        sub = df[df["scenario"] == "Historical Baseline"]
        print(f"  baseline last date: {sub['date'].iloc[-1]!r}")
