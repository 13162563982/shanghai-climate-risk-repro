"""WP9: path-independence check for the C03 -> C04 slice (acceptance A3).

Idea
----
``subst X: <NEWROOT>`` makes the very same files reachable under a different
absolute path string.  Running ``run_v8.py --from C03 --to C04`` from ``X:\\``
therefore exercises the pipeline with a different ``__file__`` root, and any
hard-coded absolute path would surface as an error or as different output.

Because X: and D: are the same physical directory, "X: vs D:" is only
meaningful against a snapshot taken before the run.  This tool does exactly
that:

    # 1) take the snapshot (before the run)
    & ".\\env\\run.ps1" tools\\_verify_path_independence.py snapshot ^
        --root "<NEWROOT>" --out-dir "<NEWROOT>\\output_archive\\wp9_ref"

    # ... subst X: / run C03-C04 from X:\\ / subst X: /D ...

    # 2) compare the post-run files against the snapshot
    & ".\\env\\run.ps1" tools\\_verify_path_independence.py compare ^
        --root "<NEWROOT>" --ref-dir "<NEWROOT>\\output_archive\\wp9_ref"

Exit codes: 0 = PASS, 1 = FAIL, 2 = usage/IO error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

# the two artefacts named in the acceptance criterion, plus two cheap extras
TARGETS = [
    r"Climate\output\intermediate\building_skeleton.parquet",
    r"Climate\output\intermediate\svi_by_district.csv",
    r"Climate\output\intermediate\isr_panel.csv",
    r"Climate\output\intermediate\delta_isr_by_district.csv",
]


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(root: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {}
    for rel in TARGETS:
        src = root / rel
        if not src.exists():
            print("  [skip] %s (absent)" % rel)
            continue
        dst = out_dir / Path(rel).name
        shutil.copy2(src, dst)
        meta[rel] = {"sha256": sha_file(src), "bytes": src.stat().st_size}
        print("  [snap] %-58s %10d B  %s" % (Path(rel).name, src.stat().st_size,
                                             meta[rel]["sha256"][:16]))
    (out_dir / "_snapshot_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("snapshot -> %s (%d files)" % (out_dir, len(meta)))
    return 0 if meta else 2


def _compare_csv(a: Path, b: Path):
    import csv as _csv
    ra = list(_csv.DictReader(a.open("r", encoding="utf-8-sig", newline="")))
    rb = list(_csv.DictReader(b.open("r", encoding="utf-8-sig", newline="")))
    if len(ra) != len(rb):
        return False, "row count %d vs %d" % (len(ra), len(rb))
    if ra and list(ra[0].keys()) != list(rb[0].keys()):
        return False, "column names differ"
    worst = 0.0
    nnum = 0
    for i, (x, y) in enumerate(zip(ra, rb)):
        for k in x:
            vx, vy = x[k], y[k]
            try:
                fx, fy = float(vx), float(vy)
                nnum += 1
                d = abs(fx - fy)
                worst = max(worst, d)
                if d > 1e-12:
                    return False, "row %d col %s: %r vs %r" % (i, k, vx, vy)
            except (TypeError, ValueError):
                if vx != vy:
                    return False, "row %d col %s: %r vs %r" % (i, k, vx, vy)
    return True, "%d rows, %d numeric cells, max |diff| %.3g" % (len(ra), nnum, worst)


def _compare_parquet(a: Path, b: Path):
    try:
        import pandas as pd
    except Exception as exc:  # noqa: BLE001
        return None, "pandas unavailable (%s)" % exc
    da = pd.read_parquet(a)
    db = pd.read_parquet(b)
    if da.shape != db.shape:
        return False, "shape %s vs %s" % (da.shape, db.shape)
    if list(da.columns) != list(db.columns):
        return False, "columns differ"
    worst, bad_col = 0.0, None
    for col in da.columns:
        sa, sb = da[col], db[col]
        if str(sa.dtype) != str(sb.dtype):
            return False, "dtype of %s: %s vs %s" % (col, sa.dtype, sb.dtype)
        if pd.api.types.is_numeric_dtype(sa):
            d = (sa.astype("float64") - sb.astype("float64")).abs()
            na_mismatch = int((sa.isna() != sb.isna()).sum())
            if na_mismatch:
                return False, "%s: NaN pattern differs in %d cells" % (col, na_mismatch)
            m = float(d.max(skipna=True)) if len(d) else 0.0
            if m > worst:
                worst, bad_col = m, col
        else:
            if not sa.astype(str).equals(sb.astype(str)):
                return False, "non-numeric column %s differs" % col
    if worst > 1e-9:
        return False, "max |diff| %.3g in %s" % (worst, bad_col)
    return True, "%d rows x %d cols, max |diff| %.3g" % (da.shape[0], da.shape[1], worst)


def compare(root: Path, ref_dir: Path) -> int:
    meta_path = ref_dir / "_snapshot_meta.json"
    if not meta_path.exists():
        print("ERROR snapshot meta not found: %s" % meta_path)
        return 2
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    fails = 0
    for rel, rec in meta.items():
        live = root / rel
        ref = ref_dir / Path(rel).name
        if not live.exists():
            print("  [FAIL] %s regenerated file missing" % Path(rel).name)
            fails += 1
            continue
        s_live = sha_file(live)
        s_ref = rec["sha256"]
        bytes_equal = (s_live == s_ref)
        if rel.lower().endswith(".parquet"):
            ok, detail = _compare_parquet(live, ref)
        else:
            ok, detail = _compare_csv(live, ref)
        tag = "PASS" if ok else ("SKIP" if ok is None else "FAIL")
        print("  [%s] %-34s bytes_equal=%-5s %s" %
              (tag, Path(rel).name, bytes_equal, detail))
        if ok is False:
            fails += 1
    print("")
    if fails:
        print("RESULT: FAIL (%d artefact(s))" % fails)
        return 1
    print("RESULT: PATH-INDEPENDENT-PASS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="WP9 path-independence check")
    ap.add_argument("mode", choices=["snapshot", "compare"])
    ap.add_argument("--root", required=True)
    ap.add_argument("--out-dir", default=None, help="snapshot dir (mode=snapshot)")
    ap.add_argument("--ref-dir", default=None, help="snapshot dir (mode=compare)")
    args = ap.parse_args()
    root = Path(args.root)
    if not root.is_dir():
        print("ERROR root not a directory: %s" % root)
        return 2
    if args.mode == "snapshot":
        if not args.out_dir:
            print("ERROR --out-dir required for snapshot")
            return 2
        return snapshot(root, Path(args.out_dir))
    if not args.ref_dir:
        print("ERROR --ref-dir required for compare")
        return 2
    return compare(root, Path(args.ref_dir))


if __name__ == "__main__":
    sys.exit(main())
