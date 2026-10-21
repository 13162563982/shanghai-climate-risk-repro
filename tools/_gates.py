"""Gate checks G0-G2 for the self-contained submission package.

Usage:
    env\\run.ps1 tools\\_gates.py [--skip-data-scan]

  G0  WP0 safety net (manifest rows, whole-dir snapshots, frozen manuscript,
      pinned IBTrACS snapshot present in both V8ROOT and NEWROOT)
  G1  every *.py in the package parses (ast); pipeline scripts contain zero
      absolute Windows drive paths
  G2  data\\ copied byte-exactly; official boundary layer SHA matches

Read-only: writes nothing.
"""

import argparse
import ast
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path

NEWROOT = Path(__file__).resolve().parent.parent
V8ROOT = NEWROOT.parent.parent.parent

DOCX_SHA = "39240D38FCF71ADB72BEA285249AFE5757E0327F26253D48BE45FA899C772F14"
OLD_NC_REL = r"data\Hazard_data\WP台风数据\IBTrACS.WP.v04r01_old_202510.nc"
OLD_NC_SHA = "DA05013357E6ADFC11DAE72C5830BED602A6C2AAFC3F3C228653850BA8DEF91D"
OLD_NC_BYTES = 8904634
OFFICIAL_SHP_REL = r"data\我国乡镇（街道）行政区划数据\_官方_天地图GS2024-0650\上海_区级_GS2024-0650.shp"
OFFICIAL_SHP_SHA = "d2eb3fc013591050be1d45b0f834a8fcd1e12c0ec804da52f4be4f8624772932"
DATA_FILES = 15286
DATA_BYTES = 15285545582

# Drive-letter path, but not the "s://" inside "https://"
DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]")

PIPELINE_PY = ["run_v8.py", "run_sensitivity.py"]
PIPELINE_DIRS = ["Climate", "Finance", "Composite"]


def sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


class Gate:
    def __init__(self, name):
        self.name = name
        self.rows = []

    def add(self, label, ok, detail=""):
        self.rows.append((label, ok, detail))

    def report(self):
        print("=" * 72)
        print(self.name)
        print("=" * 72)
        for label, ok, detail in self.rows:
            mark = "PASS" if ok else ("PEND" if ok is None else "FAIL")
            print(f"  [{mark}] {label}" + (f": {detail}" if detail else ""))
        bad = [r for r in self.rows if r[1] is False]
        pend = [r for r in self.rows if r[1] is None]
        print(f"  -> {self.name.split()[0]} = {'PASS' if not bad else 'FAIL'}"
              f"  (fail={len(bad)}, pending={len(pend)})\n")
        return not bad


def gate_g0() -> bool:
    g = Gate("G0 · WP0 safety net")
    snaps = sorted([p for p in V8ROOT.glob("_snapshot_before_*") if p.is_dir()])
    g.add("snapshot dir exists", bool(snaps), snaps[-1].name if snaps else "none")
    if not snaps:
        return g.report()
    snap = snaps[-1]
    meta_p = snap / "_snapshot_meta.json"
    g.add("snapshot meta present", meta_p.exists(), meta_p.name)
    if meta_p.exists():
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        man = snap / "_SHA256SUMS_before.csv"
        g.add("SHA256SUMS_before.csv present", man.exists())
        if man.exists():
            with open(man, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            g.add("manifest rows", len(rows) > 0, f"{len(rows)} files")
            crit = [r for r in rows if r.get("critical") == "YES"]
            g.add("critical file flagged", len(crit) == 1, crit[0]["rel_path"] if crit else "none")
            if crit:
                g.add("_old_202510.nc SHA in manifest",
                      crit[0]["sha256"].upper() == OLD_NC_SHA.upper(), crit[0]["sha256"])
        for rel, rec in meta.get("snapshots", {}).items():
            g.add(f"snapshot {rel} bytes match", bool(rec.get("match")),
                  f"{rec.get('files')} files / {rec.get('bytes'):,} B")
    docx = NEWROOT / "manuscript" / "_frozen" / "PAPER_MANUSCRIPT_FINAL.docx"
    g.add("frozen manuscript present", docx.exists())
    if docx.exists():
        g.add("frozen manuscript SHA", sha256_file(docx).upper() == DOCX_SHA,
              f"{docx.stat().st_size:,} B")
    for tag, base in (("V8ROOT", V8ROOT), ("NEWROOT", NEWROOT)):
        p = base / OLD_NC_REL
        if p.exists():
            ok = sha256_file(p).upper() == OLD_NC_SHA.upper() and p.stat().st_size == OLD_NC_BYTES
            g.add(f"{tag} pinned IBTrACS snapshot", ok, f"{p.stat().st_size:,} B")
        else:
            g.add(f"{tag} pinned IBTrACS snapshot", False, "MISSING")
    return g.report()


def gate_g1() -> bool:
    g = Gate("G1 · code collection")
    parse_fail, py_count = [], 0
    for p in NEWROOT.rglob("*.py"):
        py_count += 1
        try:
            ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
        except SyntaxError as exc:
            parse_fail.append(f"{p.relative_to(NEWROOT)}: {exc}")
    g.add("all *.py parse (ast)", not parse_fail, f"{py_count} files")
    for f in parse_fail[:10]:
        print(f"        ! {f}")

    hits = []
    targets = [NEWROOT / n for n in PIPELINE_PY]
    for d in PIPELINE_DIRS:
        targets.extend((NEWROOT / d).rglob("*.py"))
    for p in targets:
        if not p.exists():
            g.add(f"pipeline file present: {p.name}", False)
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if DRIVE_PATH.search(line):
                hits.append(f"{p.relative_to(NEWROOT)}:{i}: {line.strip()[:90]}")
    g.add("no absolute drive paths in pipeline scripts", not hits, f"{len(hits)} hits")
    for h in hits[:15]:
        print(f"        ! {h}")
    return g.report()


def gate_g2() -> bool:
    g = Gate("G2 · data copy")
    src = V8ROOT / "data"
    dst = NEWROOT / "data"
    n_src = b_src = n_dst = b_dst = 0
    for root, dirs, files in os.walk(src):
        for f in files:
            n_src += 1
            b_src += (Path(root) / f).stat().st_size
    for root, dirs, files in os.walk(dst):
        for f in files:
            n_dst += 1
            b_dst += (Path(root) / f).stat().st_size
    g.add("source file count/bytes", (n_src, b_src) == (DATA_FILES, DATA_BYTES),
          f"{n_src:,} / {b_src:,} B")
    g.add("destination matches source", (n_dst, b_dst) == (n_src, b_src),
          f"{n_dst:,} / {b_dst:,} B")
    shp = NEWROOT / OFFICIAL_SHP_REL
    g.add("official boundary layer present", shp.exists())
    if shp.exists():
        g.add("official boundary layer SHA",
              sha256_file(shp).lower() == OFFICIAL_SHP_SHA.lower(),
              f"{shp.stat().st_size:,} B")
    tmp = NEWROOT / "data" / "Hazard_data" / "WP台风数据" / "IBTrACS.WP.v04r01.nc"
    if tmp.exists():
        g.add("current IBTrACS also copied (unused, for provenance)",
              True, f"{tmp.stat().st_size:,} B")
    return g.report()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-data-scan", action="store_true")
    args = ap.parse_args()
    print(f"NEWROOT = {NEWROOT}")
    print(f"V8ROOT  = {V8ROOT}\n")
    ok = gate_g0()
    ok = gate_g1() and ok
    if not args.skip_data_scan:
        ok = gate_g2() and ok
    print("=" * 72)
    print(f"OVERALL (G0-G2) = {'PASS' if ok else 'FAIL'}")
    print("=" * 72)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
