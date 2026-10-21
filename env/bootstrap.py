"""Packaged entry point: preload conda DLLs, then run a pipeline script.

Normally invoked through ``env\\run.ps1``::

    env\\run.ps1 run_v8.py
    env\\run.ps1 Climate\\generate_figures_new.py --only basic_facts

Equivalently, with the environment already set up::

    python env\\bootstrap.py run_v8.py

Responsibilities
----------------
1. Preload the shared DLLs that live in ``<CONDA_PREFIX>\\Library\\bin`` so that
   fiona and pyarrow can resolve them.
2. Put the target script's directory and the package root on ``sys.path`` and
   change into the script's directory, reproducing the behaviour of the original
   direct invocation (``cd Climate && python 01_hazard_tc.py``).
3. Dispatch with ``runpy.run_path(..., run_name="__main__")`` so ``__file__``
   and ``__name__`` look exactly like a normal script run.

Why ``ctypes.CDLL`` instead of ``os.add_dll_directory``
------------------------------------------------------
``os.add_dll_directory()`` switches the process into secure DLL-search mode,
which prevents packages (h5py, rasterio, fiona) from finding the DLLs they
bundle inside their own sub-package directories. Loading the shared
``Library\\bin`` DLLs by absolute path achieves the same resolution without
that side effect. This mirrors the empirically validated behaviour of the
original ``run_sensitivity.py``.

Deliberately NOT preloaded: ``hdf5.dll`` (h5py bundles its own) and
``netcdf.dll`` (netCDF4 bundles its own).
"""

import ctypes
import os
import runpy
import sys
from pathlib import Path

PRELOAD_DLLS = [
    "gdal.dll",
    "arrow.dll",
    "arrow_dataset.dll",
    "arrow_acero.dll",
    "arrow_compute.dll",
    "arrow_substrait.dll",
]

CONDA_PREFIX = os.environ.get("CONDA_PREFIX", "")
LIB_BIN = Path(CONDA_PREFIX) / "Library" / "bin" if CONDA_PREFIX else None
ENV_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = ENV_DIR.parent


def preload_dlls(verbose: bool = False) -> None:
    if LIB_BIN is None or not LIB_BIN.is_dir():
        print(
            "[bootstrap] WARN CONDA_PREFIX is not set - skipping DLL preload.\n"
            "            Launch through env\\run.ps1 instead of invoking python directly.",
            file=sys.stderr,
        )
        return
    for name in PRELOAD_DLLS:
        path = LIB_BIN / name
        if not path.exists():
            continue
        try:
            ctypes.CDLL(str(path))
            if verbose:
                print(f"[bootstrap] preloaded {name}")
        except OSError as exc:  # pragma: no cover - environment specific
            print(f"[bootstrap] WARN could not preload {name}: {exc}", file=sys.stderr)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    preload_dlls(verbose=bool(os.environ.get("V8_BOOTSTRAP_VERBOSE")))

    if not argv:
        print(__doc__)
        return 2

    target = argv[0]
    if not os.path.isabs(target):
        target = os.path.join(os.getcwd(), target)
    target = os.path.abspath(target)

    if not os.path.isfile(target):
        print(f"[bootstrap] target script not found: {target}", file=sys.stderr)
        return 2

    target_dir = os.path.dirname(target)
    for extra in (target_dir, str(PACKAGE_ROOT)):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    os.chdir(target_dir)

    sys.argv = [target] + argv[1:]
    runpy.run_path(target, run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
