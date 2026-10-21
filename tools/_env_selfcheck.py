"""Gate G3 self-check for the packaged environment.

Run through the packaged entry point::

    env\\run.ps1 tools\\_env_selfcheck.py

It exercises exactly what every pipeline step does at start-up:
  * the entry point's environment variables are present
  * the SSL shim was imported (via PYTHONPATH -> sitecustomize)
  * climada / geopandas / rasterio import with no CRSError and no SSLError
  * Climate/00_config.py loads, init_environment() runs, and the configured
    administrative boundary layer resolves to an existing file

Exits non-zero on any failure. It computes nothing and writes nothing.
"""

import importlib.util
import os
import ssl
import sys
from pathlib import Path

FAILURES = []


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{': ' + str(detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)


def main() -> int:
    here = Path(__file__).resolve()
    package_root = here.parent.parent
    print("=" * 72)
    print("G3 environment self-check")
    print("=" * 72)
    print(f"  sys.executable   : {sys.executable}")
    print(f"  __file__         : {here}")
    print(f"  cwd              : {os.getcwd()}")
    print(f"  package root     : {package_root}")
    print()

    print("-- entry-point environment --")
    check("CONDA_PREFIX set", bool(os.environ.get("CONDA_PREFIX")), os.environ.get("CONDA_PREFIX", ""))
    check("python is the conda interpreter",
          Path(sys.executable).parent == Path(os.environ.get("CONDA_PREFIX", "/nonexistent")))
    for var in ("GDAL_DATA", "PROJ_DATA", "PROJ_LIB", "SSL_CERT_FILE"):
        val = os.environ.get(var, "")
        check(f"{var} set", bool(val), val)
    check("PYTHONPATH includes env\\",
          any("env" == Path(p).name for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p))

    print()
    print("-- SSL shim --")
    check("sitecustomize shim active", bool(getattr(ssl.SSLContext, "_v8_ssl_shim_installed", False)))

    print()
    print("-- third-party imports --")
    try:
        import climada  # noqa: F401
        check("import climada", True)
    except Exception as exc:  # noqa: BLE001
        check("import climada", False, f"{type(exc).__name__}: {exc}")
    try:
        import geopandas as gpd
        check("import geopandas", True, gpd.__version__)
    except Exception as exc:  # noqa: BLE001
        check("import geopandas", False, f"{type(exc).__name__}: {exc}")
    try:
        import rasterio
        from rasterio.crs import CRS
        check("import rasterio", True, rasterio.__version__)
        check("CRS.from_epsg(32651)", str(CRS.from_epsg(32651)) == "EPSG:32651",
              CRS.from_epsg(32651))
    except Exception as exc:  # noqa: BLE001
        check("import rasterio / CRS", False, f"{type(exc).__name__}: {exc}")

    print()
    print("-- Climate/00_config.py --")
    cfg_path = package_root / "Climate" / "00_config.py"
    try:
        spec = importlib.util.spec_from_file_location("_cfg_selfcheck", cfg_path)
        cfg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cfg)
        check("config loads", True)
        cfg.init_environment()
        check("init_environment() ran", True)
        check("ADMIN_BOUNDARY_SHP exists", Path(cfg.ADMIN_BOUNDARY_SHP).exists(),
              cfg.ADMIN_BOUNDARY_SHP)
        check("ADMIN_BOUNDARY_LEGACY_SHP exists", Path(cfg.ADMIN_BOUNDARY_LEGACY_SHP).exists(),
              cfg.ADMIN_BOUNDARY_LEGACY_SHP)
        check("DATA_DIR resolves inside package",
              Path(cfg.DATA_DIR).resolve() == (package_root / "data").resolve(),
              cfg.DATA_DIR)
        check("official layer is the configured default",
              "_官方_天地图GS2024-0650" in str(cfg.ADMIN_BOUNDARY_SHP))
    except Exception as exc:  # noqa: BLE001
        check("config loads", False, f"{type(exc).__name__}: {exc}")

    print()
    print("=" * 72)
    verdict = "PASS" if not FAILURES else "FAIL"
    print(f"G3 SELF-CHECK = {verdict}" + (f"  ({len(FAILURES)} failures)" if FAILURES else ""))
    for f in FAILURES:
        print(f"  - {f}")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
