"""Prove that V8ROOT was not modified after WP0 recorded its manifest.

Re-hashes every file listed in
``V8ROOT\\_snapshot_before_<ts>\\_SHA256SUMS_before.csv`` and compares
sha256 + byte count. Also lists files *added* under the scoped directories
since the snapshot (designed to be pure-additive: new logs are expected and
harmless, changed/removed files are not).

Usage:
    env\\run.ps1 tools\\_verify_v8root_untouched.py
"""

import csv
import hashlib
import os
import sys
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
# Default location of the authoritative source tree. Override with argv[1] if the
# package has been moved away from its original parent.
V8ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else NEWROOT.parent.parent.parent
SCOPE_DIRS = [
    "Climate",
    "Finance",
    "Composite",
    "config",
    r"data\我国乡镇（街道）行政区划数据",
    r"data\Hazard_data\WP台风数据",
]
SCOPE_FILES = ["run_v8.py", "run_sensitivity.py"]


def sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def main() -> int:
    snaps = sorted([p for p in V8ROOT.glob("_snapshot_before_*") if p.is_dir()])
    if not snaps:
        print(f"FAIL: no _snapshot_before_* under {V8ROOT}")
        return 1
    snap = snaps[-1]
    manifest = snap / "_SHA256SUMS_before.csv"
    print(f"V8ROOT  = {V8ROOT}")
    print(f"snapshot= {snap.name}")
    print(f"manifest= {manifest.name}\n")

    rows = list(csv.DictReader(open(manifest, encoding="utf-8-sig")))
    modified, missing = [], []
    for r in rows:
        p = V8ROOT / r["rel_path"]
        if not p.exists():
            missing.append(r["rel_path"])
            continue
        if p.stat().st_size != int(r["bytes"]) or sha256_file(p) != r["sha256"]:
            modified.append(r["rel_path"])

    # files added since the snapshot (excluding __pycache__ noise)
    known = {r["rel_path"] for r in rows}
    added = []
    for rel in SCOPE_DIRS:
        base = V8ROOT / rel
        if not base.exists():
            continue
        for dp, dns, fns in os.walk(base):
            dns[:] = [d for d in dns if d != "__pycache__"]
            for fn in fns:
                rp = str((Path(dp) / fn).relative_to(V8ROOT))
                if rp not in known:
                    added.append(rp)

    print(f"  files in manifest      : {len(rows):,}")
    print(f"  content modified       : {len(modified)}")
    print(f"  deleted / missing      : {len(missing)}")
    print(f"  added since snapshot   : {len(added)}")
    for tag, items in (("MODIFIED", modified), ("MISSING", missing), ("ADDED", added)):
        for it in items[:25]:
            print(f"    {tag}: {it}")
        if len(items) > 25:
            print(f"    {tag}: ... (+{len(items) - 25} more)")

    ok = not modified and not missing
    print(f"\nV8ROOT UNTOUCHED = {'PASS' if ok else 'FAIL'}")
    if added:
        print("  (added files are expected to be new timestamped logs only -- verify above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
