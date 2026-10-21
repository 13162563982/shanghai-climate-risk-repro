"""WP5.4 - rename figure labels in the SOURCE (FRI -> HSI, CFCI -> CCHI).

Background
----------
The v9 manuscript's HSI/CCHI renaming was done as a PIXEL operation on six PNGs
(`_figure_relabel/relabel.py`, 33 text changes). The generating source was never
touched, so re-running the figure scripts would revert the labels. This tool
moves the rename into the source, as required by plan WP5.4 / acceptance A4.

Design notes
------------
* Pure ASCII: the source files spell non-ASCII as Python escapes (e.g. the
  en-dash is the six characters ``\\u2013``). Every pattern below is a raw string,
  so what you read here is byte-for-byte what must be in the file.
* Every replacement declares an expected occurrence count. A mismatch aborts
  the whole run before anything is written.
* The one real logic hazard (`Composite\\generate_figures.py`, the end-value
  annotation loop where "FRI"/"CFCI" are used BOTH as a legend label and as the
  switch that picks the CSV column) is handled by introducing a separate display
  label so the column key is never touched.

Usage
-----
    env\\run.ps1 tools\\_wp5_rename_figure_labels.py            # dry run (default)
    env\\run.ps1 tools\\_wp5_rename_figure_labels.py --apply
"""

import argparse
import hashlib
import shutil
import sys
from datetime import datetime
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent

FIN = r"Finance\generate_figures.py"
CMP = r"Composite\generate_figures.py"

# (relpath, old, new, expected_count)
REPLACEMENTS = [
    # ── Finance: fi_01 (HSI main index) ────────────────────────────────
    (FIN,
     '''fig.suptitle(f"Shanghai Finance Risk Index (2011 \\u2013 {end_year})",''',
     '''fig.suptitle("Housing Stress Index",''', 1),
    (FIN,
     '''             "FRI: Merton Jump-Diffusion  |  Sub-indicators derived "
             "from simulated price paths  |  "
             "Bands: 10th\\u201390th percentile, N=500 MC paths",''',
     '''             "HSI: Sub-indicators derived from simulated price paths  |  "
             "Bands: 10th\\u201390th percentile, N=500 MC paths",''', 1),
    (FIN, '''label="Shanghai FRI (12-mo mean)")''', '''label="HSI")''', 1),
    (FIN,
     '''ax.set_ylabel("FRI Level (Base 100)", fontsize=13, fontweight="bold")''',
     '''ax.set_ylabel("HSI", fontsize=13, fontweight="bold")''', 1),

    # ── Finance: fi_02 (sub-indicator decomposition) ───────────────────
    (FIN, '''label="FRI (raw composite)")''', '''label="HSI (raw composite)")''', 1),
    (FIN,
     '''ax.set_ylabel("FRI Raw [0-1]", fontsize=10, fontweight="bold")''',
     '''ax.set_ylabel("HSI Raw [0-1]", fontsize=10, fontweight="bold")''', 1),
    (FIN,
     '''fig.suptitle("FRI Sub-indicator Decomposition",''',
     '''fig.suptitle("HSI Sub-indicator Decomposition",''', 1),

    # ── Finance: fi_04 (HSI vs CRI overlay) ────────────────────────────
    (FIN, '''label="FRI (Finance)")''', '''label="HSI (Housing)")''', 1),
    (FIN,
     '''    ax1.set_ylabel("FRI Level (Base 100)", fontsize=13,
                   fontweight="bold", color=C_FRI_MAIN)''',
     '''    ax1.set_ylabel("HSI", fontsize=13,
                   fontweight="bold", color=C_FRI_MAIN)''', 1),
    (FIN,
     '''fig.suptitle("Finance Risk Index vs. Climate Risk Index",''',
     '''fig.suptitle("Housing Stress Index vs. Climate Risk Index",''', 1),
    (FIN,
     '''             "FRI: price gap + vol + climate CVaR  |  "''',
     '''             "HSI: price gap + vol + climate CVaR  |  "''', 1),

    # ── Composite: cf_01 (CCHI main index) ─────────────────────────────
    (CMP, '''label="Shanghai CFCI (historical)")''',
     '''label="CCHI (historical)")''', 1),
    (CMP,
     '''ax.set_ylabel("CFCI Level (Base 100)", fontsize=13, fontweight="bold")''',
     '''ax.set_ylabel("CCHI Level (Base 100)", fontsize=13, fontweight="bold")''', 1),
    (CMP,
     '''fig.suptitle(f"Shanghai Climate-Finance Composite Index "
                 f"(2012 \\u2013 {config.CFCI_PROJECTION_END_YEAR})",''',
     '''fig.suptitle("Composite Climate-Housing Index",''', 1),
    (CMP,
     '''             "CFCI = \\u221a(CRI \\u00d7 FRI)  |  Geometric mean, parameter-free  |  "''',
     '''             "CCHI = \\u221a(CRI \\u00d7 HSI)  |  Geometric mean, parameter-free  |  "''', 1),

    # ── Composite: cf_02 (triple comparison) ───────────────────────────
    (CMP, '''label="FRI (Finance)")''', '''label="HSI (Housing)")''', 1),
    (CMP, '''label="CFCI (Composite)")''', '''label="CCHI")''', 1),
    # >>> the logic hazard: keep the column keys, change only the display text
    (CMP,
     '''    for series, color, name in [
        (cri_full, C_CRI, "CRI"),
        (fri_valid, C_FRI, "FRI"),
        (hist, C_CFCI, "CFCI"),
    ]:
        last = series.iloc[-1]
        col = "cri_index" if name == "CRI" else ("fri_index" if name == "FRI" else "cfci")
        ax.annotate(f"{name}: {last[col]:.0f}",''',
     '''    # NOTE: `name` selects the CSV column and must keep the short keys
    # (CRI/FRI/CFCI). `label` is display-only and carries the renamed indices.
    for series, color, name, label in [
        (cri_full, C_CRI, "CRI", "CRI"),
        (fri_valid, C_FRI, "FRI", "HSI"),
        (hist, C_CFCI, "CFCI", "CCHI"),
    ]:
        last = series.iloc[-1]
        col = "cri_index" if name == "CRI" else ("fri_index" if name == "FRI" else "cfci")
        ax.annotate(f"{label}: {last[col]:.0f}",''', 1),
    (CMP,
     '''fig.suptitle("CRI vs. FRI vs. CFCI \u2014 Triple Index Comparison",''',
     '''fig.suptitle("CRI vs. HSI vs. CCHI \u2014 Triple Index Comparison",''', 1),
    (CMP,
     '''            "FRI = PriceGap + Vol + ClimateCVaR  |  "
            "CFCI = \\u221a(CRI\\u00d7FRI)  |  All base-100",''',
     '''            "HSI = PriceGap + Vol + ClimateCVaR  |  "
            "CCHI = \\u221a(CRI\\u00d7HSI)  |  All base-100",''', 1),

    # ── Composite: cf_03 (CCHI decomposition) ──────────────────────────
    (CMP,
     '''ax.set_ylabel("FRI", fontsize=11, fontweight="bold", color=C_FRI)''',
     '''ax.set_ylabel("HSI", fontsize=11, fontweight="bold", color=C_FRI)''', 1),
    (CMP, '''"B. Finance Risk Index (FRI)",''',
     '''"B. Housing Stress Index (HSI)",''', 1),
    (CMP,
     '''ax.set_ylabel("CFCI", fontsize=11, fontweight="bold", color=C_CFCI)''',
     '''ax.set_ylabel("CCHI", fontsize=11, fontweight="bold", color=C_CFCI)''', 1),
    (CMP, '''"C. Composite = \\u221a(CRI \\u00d7 FRI)",''',
     '''"C. Composite = \\u221a(CRI \\u00d7 HSI)",''', 1),
    (CMP, '''f"CRI-FRI r = {corr:.3f}",''', '''f"CRI-HSI r = {corr:.3f}",''', 1),
    (CMP, '''fig.suptitle("CFCI Component Decomposition",''',
     '''fig.suptitle("CCHI Component Decomposition",''', 1),
]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = ap.parse_args()

    texts = {}
    for rel in (FIN, CMP):
        p = NEWROOT / rel
        if not p.exists():
            print(f"FAIL: missing {p}")
            return 1
        texts[rel] = p.read_text(encoding="utf-8")

    problems = []
    print("=" * 78)
    print(f"WP5.4 figure-label rename  ({'APPLY' if args.apply else 'DRY RUN'})")
    print("=" * 78)

    for i, (rel, old, new, expected) in enumerate(REPLACEMENTS, 1):
        got = texts[rel].count(old)
        status = "ok" if got == expected else "MISMATCH"
        if got != expected:
            problems.append((rel, i, expected, got, old.splitlines()[0][:70]))
        print(f"  [{status:>8}] #{i:>2} {rel:<28} found={got} expected={expected}"
              f"  {old.strip().splitlines()[0][:58]}")
        if args.apply and got == expected:
            texts[rel] = texts[rel].replace(old, new)

    if problems:
        print("\nABORT - occurrence-count mismatch; nothing written.")
        for rel, i, exp, got, snippet in problems:
            print(f"  #{i} {rel}: expected {exp}, found {got} :: {snippet}")
        return 1

    if not args.apply:
        print(f"\nDry run OK: all {len(REPLACEMENTS)} replacements match exactly once. "
              f"Re-run with --apply.")
        return 0

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = NEWROOT / "output_archive" / f"_wp5_src_backup_{ts}"
    backup.mkdir(parents=True, exist_ok=True)
    for rel in (FIN, CMP):
        p = NEWROOT / rel
        shutil.copy2(p, backup / Path(rel).name)
        before = sha256(p)
        p.write_text(texts[rel], encoding="utf-8")
        print(f"  WROTE {rel}\n        sha256 {before[:16]}... -> {sha256(p)[:16]}...")
    print(f"\n  backups: {backup}")

    # verify no stale index names remain in RENDERED text (docstrings and the
    # deliberate CSV-column keys are expected and reported separately)
    print("\n-- residual check (string literals only) --")
    import re
    RENDER = re.compile(r"suptitle|set_title|set_ylabel|set_xlabel|label=|ax\.text|ax1\.text|ax\.annotate")
    bad = expected = 0
    for rel in (FIN, CMP):
        src = (NEWROOT / rel).read_text(encoding="utf-8")
        lines = src.splitlines()
        for m in re.finditer(r'"[^"\n]*"', src):
            lit = m.group(0)
            if not (re.search(r"\b(FRI|CFCI)\b", lit) or "Finance Risk Index" in lit):
                continue
            line_no = src[:m.start()].count("\n") + 1
            line = lines[line_no - 1] if line_no <= len(lines) else ""
            if RENDER.search(line):
                print(f"  !! RENDERED TEXT STILL STALE {rel}:{line_no}: {lit[:80]}")
                bad += 1
            else:
                print(f"  [ok-expected] {rel}:{line_no} (docstring/comment or CSV key): {lit[:60]}")
                expected += 1
    print(f"  stale rendered literals: {bad}   expected non-rendered: {expected}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
