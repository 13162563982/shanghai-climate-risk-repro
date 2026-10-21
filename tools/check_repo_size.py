# -*- coding: utf-8 -*-
"""Pre-upload gate for this repository.

Run from the repository root:      python tools/check_repo_size.py
Exit code 0 = ready to push, 1 = something must be fixed.

GitHub's hard rules enforced here
  * a single file larger than 100 MiB is REJECTED by GitHub (not a warning)
  * a single release asset must be below 2 GiB
  * a push larger than 2 GiB is rejected, and repos are expected to stay
    well under 5 GiB

The eight oversized inputs/artefacts of this project live in a GitHub Release
and are described by RELEASE_ASSETS.md.  Their absence from git is expected;
everything else must be present and match manifest.json exactly.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_FILE_MIB = 100
MAX_RELEASE_GIB = 2.0
MAX_REPO_GIB = 5.0

FORBIDDEN_SUBSTRINGS = [
    "2005-2025年我国逐日平均气温",   # D08 — never read by the model, 10.9 GB
    "output_archive",                 # historical snapshot copies
    "PAPER_MANUSCRIPT",               # manuscript, not needed for reproduction
    "__pycache__",
]
FORBIDDEN_SUFFIXES = [".pyc", ".pyo"]

REQUIRED_FILES = [
    "README.md", "REPRODUCE.md", "DATA_SOURCES.md", "RELEASE_ASSETS.md",
    "LICENSE", "CITATION.cff", "SHA256SUMS.txt", "manifest.json",
    "provenance/README.md",
]


def sha256(path: Path, chunk: int = 4 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main() -> int:
    problems: list[str] = []
    warnings: list[str] = []

    manifest_path = ROOT / "manifest.json"
    if not manifest_path.exists():
        print("FAIL  manifest.json missing at repository root")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest["files"]
    expected_repo = {f["repo_path"]: f for f in files if f["zone"] == "repo"}

    # ---- 1. collect what is actually on disk ------------------------------
    on_disk = {}
    biggest = []
    self_files = {"manifest.json", "SHA256SUMS.txt", "SHA256SUMS.csv"}
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if rel.startswith(".git/") or rel in self_files:
            continue
        size = p.stat().st_size
        on_disk[rel] = size
        biggest.append((size, rel))

    # ---- 2. per-file limit ------------------------------------------------
    too_big = [(s, r) for s, r in biggest if s > MAX_FILE_MIB * 2**20]
    for s, r in too_big:
        problems.append(f"file exceeds {MAX_FILE_MIB} MiB (GitHub rejects): {r} = {s/2**20:.1f} MiB")
    biggest.sort(reverse=True)

    # ---- 3. forbidden content --------------------------------------------
    for rel in on_disk:
        low = rel.lower()
        for bad in FORBIDDEN_SUBSTRINGS:
            if bad.lower() in low:
                problems.append(f"forbidden path present: {rel}")
        if any(low.endswith(suf) for suf in FORBIDDEN_SUFFIXES):
            problems.append(f"byte-code file present: {rel}")

    # ---- 4. required docs -------------------------------------------------
    for req in REQUIRED_FILES:
        if not (ROOT / req).exists():
            problems.append(f"required file missing: {req}")

    # ---- 5. totals --------------------------------------------------------
    repo_bytes = sum(on_disk.values())
    if repo_bytes > MAX_REPO_GIB * 2**30:
        problems.append(f"repository is {repo_bytes/2**30:.2f} GiB (> {MAX_REPO_GIB} GiB)")

    # ---- 6. manifest <-> disk agreement ----------------------------------
    missing = sorted(set(expected_repo) - set(on_disk))
    extra = sorted(set(on_disk) - set(expected_repo))
    for m in missing[:30]:
        problems.append(f"in manifest but missing on disk: {m}")
    for e in extra[:30]:
        problems.append(f"on disk but not in manifest: {e}")

    # ---- 7. release assets described -------------------------------------
    release = [f for f in files if f["zone"] == "release"]
    rel_md = (ROOT / "RELEASE_ASSETS.md")
    if rel_md.exists():
        body = rel_md.read_text(encoding="utf-8")
        for f in release:
            if f["asset_name"] not in body:
                problems.append(f"release asset not documented in RELEASE_ASSETS.md: {f['asset_name']}")
    rel_bytes = sum(f["bytes"] for f in release)
    for f in release:
        if f["bytes"] >= MAX_RELEASE_GIB * 2**30:
            problems.append(f"release asset >= {MAX_RELEASE_GIB} GiB: {f['asset_name']}")

    # ---- 8. checksum spot-check (largest 25 files) -----------------------
    verified = 0
    for size, rel in biggest[:25]:
        if rel in ("manifest.json", "SHA256SUMS.txt"):
            continue
        want = expected_repo.get(rel, {}).get("sha256")
        if not want:
            continue
        got = sha256(ROOT / rel)
        verified += 1
        if got != want:
            problems.append(f"sha256 mismatch: {rel}")

    # ---------------------------------------------------------------- report
    print("=" * 72)
    print("REPOSITORY READY-GATE")
    print("=" * 72)
    print(f"root                : {ROOT}")
    print(f"files on disk       : {len(on_disk):,}")
    print(f"files in manifest   : {len(expected_repo):,} (repo) + {len(release)} (release)")
    print(f"repository size     : {repo_bytes/2**30:.3f} GiB")
    print(f"release assets      : {len(release)} files / {rel_bytes/2**30:.3f} GiB")
    print(f"largest 5 files     :")
    for s, r in biggest[:5]:
        print(f"    {s/2**20:8.1f} MiB  {r}")
    print(f"spot-verified       : {verified} files")
    print()
    if warnings:
        for w in warnings:
            print(f"WARN  {w}")
    if problems:
        print(f"RESULT: FAIL  ({len(problems)} problems)")
        for p in problems[:40]:
            print(f"  - {p}")
        if len(problems) > 40:
            print(f"  ... and {len(problems)-40} more")
        return 1
    print("RESULT: PASS — safe to git add / commit / push")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
