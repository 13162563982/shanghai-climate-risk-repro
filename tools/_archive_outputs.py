"""Archive the model output trees into output_archive/<label>/ (write-once).

Copies Climate\\output, Finance\\output, Composite\\output and (optionally)
_sensitivity_results into a timestamped archive directory, then writes a
freeze manifest beside them.

Usage:
    env\\run.ps1 tools\\_archive_outputs.py baseline_legacy_20261016_212711
    env\\run.ps1 tools\\_archive_outputs.py boundary_official_20261016_2230 --with-sensitivity
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
TREES = [r"Climate\output", r"Finance\output", r"Composite\output"]


def count(root: Path):
    n = b = 0
    for dp, _dn, fns in os.walk(root):
        for f in fns:
            n += 1
            b += (Path(dp) / f).stat().st_size
    return n, b


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("label", help="archive subdirectory name under output_archive/")
    ap.add_argument("--with-sensitivity", action="store_true")
    args = ap.parse_args()

    dest = NEWROOT / "output_archive" / args.label
    if dest.exists():
        print(f"FAIL: {dest} already exists (archives are write-once)")
        return 1
    dest.mkdir(parents=True)

    trees = list(TREES) + ([r"_sensitivity_results"] if args.with_sensitivity else [])
    summary = {"label": args.label, "created": datetime.now().isoformat(timespec="seconds"),
               "trees": {}}
    for rel in trees:
        src = NEWROOT / rel
        if not src.exists():
            print(f"  [WARN] missing {rel}")
            continue
        dst = dest / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        n_s, b_s = count(src)
        n_d, b_d = count(dst)
        ok = (n_s, b_s) == (n_d, b_d)
        summary["trees"][rel] = {"files": n_s, "bytes": b_s, "match": ok}
        print(f"  [{'OK ' if ok else 'MISMATCH'}] {rel:<22} {n_s:>5} files / {b_s:>15,} B")

    # run the freeze manifest into the archive
    man = dest / "MANIFEST.json"
    r = subprocess.run([sys.executable, str(NEWROOT / "tools" / "freeze_baseline.py"),
                        "--out", str(man)], cwd=str(NEWROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = (r.stdout or "").strip().splitlines()[-3:]
    print("  manifest rc=%d" % r.returncode)
    for line in tail:
        print(f"    {line}")
    summary["manifest_rc"] = r.returncode
    summary["manifest_bytes"] = man.stat().st_size if man.exists() else 0

    (dest / "_ARCHIVE_META.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  archive: {dest}")
    return 0 if all(v["match"] for v in summary["trees"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
