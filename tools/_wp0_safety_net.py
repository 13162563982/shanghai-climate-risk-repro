"""
WP0 · Safety net (pure additive -- does NOT modify any existing V8ROOT file).

Produces exactly three new things:
  1. V8ROOT\\_snapshot_before_<ts>\\_SHA256SUMS_before.csv   (attack surface manifest)
  2. V8ROOT\\_snapshot_before_<ts>\\{Climate,Finance,Composite,_sensitivity_results}\\  (whole-dir snapshots)
  3. NEWROOT\\manuscript\\_frozen\\PAPER_MANUSCRIPT_FINAL.docx (frozen manuscript)

Gate G0:
  - snapshot file counts == recorded counts
  - frozen docx SHA256 == 39240D38FCF71ADB72BEA285249AFE5757E0327F26253D48BE45FA899C772F14
  - IBTrACS.WP.v04r01_old_202510.nc SHA256 == DA05013357E6ADFC11DAE72C5830BED602A6C2AAFC3F3C228653850BA8DEF91D

Usage:
  python _wp0_safety_net.py [--v8root DIR] [--newroot DIR] [--verify-only]
"""

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

V8ROOT_DEFAULT = Path(r"D:\桌面real\陈剑老师研究工作\Shanghai_Climate_Risk_Analysis\复现公报台风研究结果\model_房地产风险_v8")
NEWROOT_DEFAULT = V8ROOT_DEFAULT / "期刊投稿" / "Nature-JF投稿" / "Nature npj Natural Hazards"

DOCX_EXPECT_SHA = "39240D38FCF71ADB72BEA285249AFE5757E0327F26253D48BE45FA899C772F14"
OLD_NC_REL = r"data\Hazard_data\WP台风数据\IBTrACS.WP.v04r01_old_202510.nc"
OLD_NC_EXPECT_SHA = "DA05013357E6ADFC11DAE72C5830BED602A6C2AAFC3F3C228653850BA8DEF91D"
OLD_NC_EXPECT_BYTES = 8904634

# Directories whose SHA256 sums are recorded (relative to V8ROOT).
HASH_SCOPE_DIRS = [
    "Climate",
    "Finance",
    "Composite",
    "config",
    r"data\我国乡镇（街道）行政区划数据",
    r"data\Hazard_data\WP台风数据",
]
HASH_SCOPE_FILES = ["run_v8.py", "run_sensitivity.py"]

# Whole-directory snapshots (relative to V8ROOT).
SNAPSHOT_DIRS = [
    r"Climate\output",
    r"Finance\output",
    r"Composite\output",
    "_sensitivity_results",
]

SNAPSHOT_META = "_snapshot_meta.json"


def sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            yield Path(dirpath) / name


def build_manifest(v8root: Path, out_csv: Path) -> list:
    rows = []
    targets = []
    for rel in HASH_SCOPE_DIRS:
        p = v8root / rel
        if not p.exists():
            print(f"  [WARN] scope dir missing: {rel}")
            continue
        targets.extend(sorted(iter_files(p)))
    for rel in HASH_SCOPE_FILES:
        p = v8root / rel
        if p.exists():
            targets.append(p)
        else:
            print(f"  [WARN] scope file missing: {rel}")

    print(f"  hashing {len(targets)} files ...")
    t0 = time.time()
    for i, p in enumerate(targets, 1):
        rel = str(p.relative_to(v8root))
        st = p.stat()
        rows.append({
            "rel_path": rel,
            "bytes": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "sha256": sha256_file(p),
            "critical": "YES" if rel == OLD_NC_REL else "",
        })
        if i % 250 == 0:
            print(f"    {i}/{len(targets)}  ({time.time() - t0:.0f}s)")

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["rel_path", "bytes", "mtime", "sha256", "critical"])
        w.writeheader()
        w.writerows(rows)
    print(f"  manifest rows={len(rows)}  -> {out_csv}  ({time.time() - t0:.0f}s)")
    return rows


def snapshot(v8root: Path, snaproot: Path) -> dict:
    counts = {}
    for rel in SNAPSHOT_DIRS:
        src = v8root / rel
        if not src.exists():
            print(f"  [WARN] snapshot source missing: {rel}")
            counts[rel] = {"files": 0, "bytes": 0, "status": "MISSING"}
            continue
        dst = snaproot / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            shutil.rmtree(dst)
        t0 = time.time()
        shutil.copytree(src, dst)
        n = 0
        b = 0
        for p in iter_files(src):
            n += 1
            b += p.stat().st_size
        n2 = 0
        b2 = 0
        for p in iter_files(dst):
            n2 += 1
            b2 += p.stat().st_size
        counts[rel] = {
            "files": n, "bytes": b, "files_copied": n2, "bytes_copied": b2,
            "match": (n == n2 and b == b2), "elapsed_s": round(time.time() - t0, 1),
        }
        flag = "OK " if (n == n2 and b == b2) else "MISMATCH"
        print(f"  [{flag}] {rel}: {n} files / {b} B -> {n2} / {b2}  ({time.time() - t0:.0f}s)")
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v8root", default=str(V8ROOT_DEFAULT))
    ap.add_argument("--newroot", default=str(NEWROOT_DEFAULT))
    ap.add_argument("--ts", default=None)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    v8root = Path(args.v8root)
    newroot = Path(args.newroot)
    ts = args.ts or datetime.now().strftime("%Y%m%d_%H%M%S")
    snaproot = v8root / f"_snapshot_before_{ts}"

    print("=" * 72)
    print("WP0 · safety net")
    print(f"V8ROOT  = {v8root}")
    print(f"NEWROOT = {newroot}")
    print(f"SNAP    = {snaproot}")
    print(f"ts      = {ts}")
    print("=" * 72)

    results = {"ts": ts, "v8root": str(v8root), "newroot": str(newroot), "snaproot": str(snaproot)}

    if not args.verify_only:
        # --- 1. SHA256SUMS_before.csv -------------------------------------
        print("\n[1/3] SHA256SUMS_before.csv")
        rows = build_manifest(v8root, snaproot / "_SHA256SUMS_before.csv")
        results["manifest_rows"] = len(rows)

        # --- 2. whole-directory snapshots ---------------------------------
        print("\n[2/3] whole-directory snapshots")
        results["snapshots"] = snapshot(v8root, snaproot)

        # --- 3. frozen manuscript -----------------------------------------
        print("\n[3/3] frozen manuscript")
        frozen_dir = newroot / "manuscript" / "_frozen"
        frozen_dir.mkdir(parents=True, exist_ok=True)
        src_docx = newroot / "PAPER_MANUSCRIPT_FINAL.docx"
        dst_docx = frozen_dir / "PAPER_MANUSCRIPT_FINAL.docx"
        if src_docx.exists() and not dst_docx.exists():
            shutil.copy2(src_docx, dst_docx)
            action = "copied"
        elif dst_docx.exists():
            action = "kept (already frozen)"
        else:
            raise SystemExit(f"FATAL: manuscript not found: {src_docx}")
        docx_sha = sha256_file(dst_docx)
        results["frozen_docx"] = {
            "path": str(dst_docx), "action": action,
            "bytes": dst_docx.stat().st_size, "sha256": docx_sha,
        }
        print(f"  {action}: {dst_docx}  bytes={dst_docx.stat().st_size}")
        print(f"  sha256={docx_sha}")

        with open(snaproot / SNAPSHOT_META, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    # --- G0 verification --------------------------------------------------
    print("\n" + "=" * 72)
    print("GATE G0")
    print("=" * 72)
    gates = []

    # docx
    dst_docx = newroot / "manuscript" / "_frozen" / "PAPER_MANUSCRIPT_FINAL.docx"
    if not dst_docx.exists():
        gates.append(("frozen docx exists", False, "missing"))
    else:
        s = sha256_file(dst_docx)
        gates.append(("frozen docx SHA256", s.upper() == DOCX_EXPECT_SHA.upper(), s.upper()))

    # old nc (in V8ROOT and in NEWROOT if already copied)
    for tag, base in (("V8ROOT", v8root), ("NEWROOT", newroot)):
        p = base / OLD_NC_REL
        if p.exists():
            s = sha256_file(p)
            ok = (s.upper() == OLD_NC_EXPECT_SHA.upper() and p.stat().st_size == OLD_NC_EXPECT_BYTES)
            gates.append((f"{tag} _old_202510.nc SHA256+bytes", ok, f"{p.stat().st_size} B {s.upper()}"))
        else:
            # NEWROOT copy lands in WP2; report as PENDING (None) rather than FAIL.
            gates.append((f"{tag} _old_202510.nc present", None, f"PENDING (WP2): {p}"))

    # snapshot counts vs live sources
    if (snaproot / SNAPSHOT_META).exists():
        meta = json.loads((snaproot / SNAPSHOT_META).read_text(encoding="utf-8"))
        for rel, rec in meta.get("snapshots", {}).items():
            gates.append((f"snapshot {rel} file/byte match", bool(rec.get("match")),
                          f"{rec.get('files')} files / {rec.get('bytes')} B"))
        gates.append(("manifest rows > 0", meta.get("manifest_rows", 0) > 0,
                      str(meta.get("manifest_rows"))))
        results = meta

    for name, ok, detail in gates:
        label = "PASS" if ok else ("PEND" if ok is None else "FAIL")
        print(f"  [{label}] {name}: {detail}")

    failed = [n for n, ok, _ in gates if ok is False]
    pending = [n for n, ok, _ in gates if ok is None]
    print(f"\nG0 = {'PASS' if not failed else 'FAIL'}  (fail={len(failed)}, pending={len(pending)})")
    if pending:
        print("  pending (resolved later): " + "; ".join(pending))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
