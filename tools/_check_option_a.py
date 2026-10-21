"""Static verification of option A (coastline decoupled from the official boundary).

Run through the packaged entry point::

    env\\run.ps1 tools\\_check_option_a.py

Option A keeps the official GS(2024)0650 layer for district assignment, area /
density and the basemap, and pins ONLY the storm-surge shoreline back onto the
fine township layer via config.COASTLINE_BOUNDARY_SHP.

This script proves, without computing anything or writing any output, that:
  1. Climate/00_config.py and Climate/climate_functions.py are syntactically valid
     and config exposes COASTLINE_BOUNDARY_SHP == ADMIN_BOUNDARY_LEGACY_SHP
     (an existing file);
  2. the four boundary consumers resolve as intended: three still read
     ADMIN_BOUNDARY_SHP (official layer), and exactly one - the shoreline in
     compute_east_sea_coast_distance() - reads COASTLINE_BOUNDARY_SHP;
  3. nothing else in the package reads COASTLINE_BOUNDARY_SHP;
  4. the resolved shoreline path, under a clean V8_PARAM_OVERRIDES, is the fine
     township layer.

Exits non-zero on any failure.
"""

import hashlib
import importlib.util
import os
import sys
from pathlib import Path

FAILURES = []
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
CLIMATE = PACKAGE_ROOT / "Climate"

# Wiring invariants (substring, not line numbers - robust to comment insertion).
# Official layer  -> district assignment / area-density / basemap
# Fine layer      -> storm-surge shoreline only
WIRING = [
    ("Climate/03_exposure.py",
     ["gpd.read_file(config.ADMIN_BOUNDARY_SHP)"],
     ["COASTLINE_BOUNDARY_SHP"]),
    ("Climate/04_vulnerability.py",
     ["gpd.read_file(config.ADMIN_BOUNDARY_SHP)"],
     ["COASTLINE_BOUNDARY_SHP"]),
    ("Climate/visualization/maps.py",
     ["str(config.ADMIN_BOUNDARY_SHP)"],
     ["COASTLINE_BOUNDARY_SHP"]),
    ("Climate/climate_functions.py",
     ['_coast_shp = getattr(config, "COASTLINE_BOUNDARY_SHP", config.ADMIN_BOUNDARY_SHP)',
      "admin_raw = gpd.read_file(_coast_shp)"],
     []),
]


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{': ' + str(detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)
    return ok


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def main() -> int:
    print("=" * 72)
    print("Option A static check (coastline decoupling)")
    print("=" * 72)
    print(f"  package root : {PACKAGE_ROOT}")
    print(f"  cwd          : {os.getcwd()}")
    print()

    print("-- 1. syntax --")
    for rel in ("Climate/00_config.py", "Climate/climate_functions.py"):
        p = PACKAGE_ROOT / rel
        try:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
            check(f"compiles: {rel}", True)
        except SyntaxError as exc:
            check(f"compiles: {rel}", False, f"line {exc.lineno}: {exc.msg}")

    print()
    print("-- 2. config constants --")
    cfg = None
    try:
        spec = importlib.util.spec_from_file_location("_cfg_option_a", CLIMATE / "00_config.py")
        cfg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cfg)
        check("config loads", True)
    except Exception as exc:  # noqa: BLE001
        check("config loads", False, f"{type(exc).__name__}: {exc}")
        cfg = None

    if cfg is not None:
        coast = getattr(cfg, "COASTLINE_BOUNDARY_SHP", None)
        check("COASTLINE_BOUNDARY_SHP defined", coast is not None)
        check("COASTLINE_BOUNDARY_SHP == ADMIN_BOUNDARY_LEGACY_SHP",
              str(coast) == str(cfg.ADMIN_BOUNDARY_LEGACY_SHP), coast)
        check("COASTLINE_BOUNDARY_SHP exists on disk", bool(coast) and Path(coast).exists(), coast)
        check("ADMIN_BOUNDARY_SHP is still the official layer",
              "_官方_天地图GS2024-0650" in str(cfg.ADMIN_BOUNDARY_SHP), cfg.ADMIN_BOUNDARY_SHP)
        check("COASTLINE_BOUNDARY_SHP is NOT the official layer",
              "_官方_天地图GS2024-0650" not in str(coast), coast)
        check("legacy file is the 2021 township layer",
              "2021年我国乡镇（街道）边界数据.shp" in str(coast), Path(coast).name)

        print()
        print("-- 3. pinned layer identity --")
        for label, p in (("ADMIN_BOUNDARY_SHP (official)", cfg.ADMIN_BOUNDARY_SHP),
                         ("COASTLINE_BOUNDARY_SHP (fine)", coast)):
            p = Path(p)
            if p.exists():
                print(f"    {label:<34} {p.stat().st_size:>12,} B  {sha256(p)}")
            else:
                print(f"    {label:<34} MISSING")

    print()
    print("-- 4. consumer wiring (substring invariants) --")
    for rel, must_have, must_not_have in WIRING:
        p = PACKAGE_ROOT / rel
        if not p.exists():
            check(f"{rel} wiring", False, "file missing")
            continue
        text = p.read_text(encoding="utf-8")
        missing = [s for s in must_have if s not in text]
        present = [s for s in must_not_have if s in text]
        ok = not missing and not present
        detail = []
        if missing:
            detail.append("missing: " + " | ".join(missing))
        if present:
            detail.append("unexpected: " + " | ".join(present))
        check(f"{rel} wiring", ok, "; ".join(detail))

    print()
    print("-- 5. no other PIPELINE consumer of COASTLINE_BOUNDARY_SHP --")
    # Only the pipeline counts here. tools\ is verification code and is expected
    # to reference the constant (option-A checks, result verification).
    hits = []
    pipeline_dirs = ("Climate", "Finance", "Composite")
    for p in sorted(PACKAGE_ROOT.rglob("*.py")):
        parts = p.relative_to(PACKAGE_ROOT).parts
        if any(part in {"output_archive", ".git", "__pycache__", "env", "tools", "docs"}
               for part in parts):
            continue
        if parts[0] not in pipeline_dirs and len(parts) > 1:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "COASTLINE_BOUNDARY_SHP" in text:
            hits.append(p.relative_to(PACKAGE_ROOT).as_posix())
    expected_hits = {"Climate/00_config.py", "Climate/climate_functions.py"}
    check("COASTLINE_BOUNDARY_SHP appears only in config + its one pipeline consumer",
          set(hits) == expected_hits, "; ".join(hits) or "(none)")

    print()
    print("-- 6. effective resolution under a clean override env --")
    ov = os.environ.get("V8_PARAM_OVERRIDES", "")
    check("V8_PARAM_OVERRIDES does not pin ADMIN_BOUNDARY_SHP", "ADMIN_BOUNDARY_SHP" not in ov,
          ov if ov else "(unset)")
    check("V8_PARAM_OVERRIDES does not pin COASTLINE_BOUNDARY_SHP",
          "COASTLINE_BOUNDARY_SHP" not in ov)
    if cfg is not None:
        check("shoreline resolves to the fine layer",
              str(getattr(cfg, "COASTLINE_BOUNDARY_SHP", "")) ==
              str(cfg.DATA_DIR / "我国乡镇（街道）行政区划数据" / "2021年我国乡镇（街道）边界数据.shp"),
              getattr(cfg, "COASTLINE_BOUNDARY_SHP", None))

    print()
    print("=" * 72)
    verdict = "PASS" if not FAILURES else "FAIL"
    print(f"OPTION-A STATIC CHECK = {verdict}" + (f"  ({len(FAILURES)} failures)" if FAILURES else ""))
    for f in FAILURES:
        print(f"  - {f}")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
