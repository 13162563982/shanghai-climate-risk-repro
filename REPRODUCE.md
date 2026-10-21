# REPRODUCE — how to rebuild every number in the paper

This repository contains the complete model code, the **verbatim** input data it
reads, and the frozen outputs it produces. Nothing has been clipped, resampled
or regenerated for publication: the shipped files are byte-identical to the ones
the published results were computed from, and `SHA256SUMS.txt` lets you prove it.

---

## 0. What runs where

| | |
|---|---|
| Entry point | `env\run.ps1` — the **only** supported launcher |
| Pipeline driver | `run_v8.py` — 11 steps, `C01 → C03 → C02 → C04 → C05 → C06 → C07 → F01 → F02 → F03 → X01` |
| Full-chain runtime | **≈ 26 min** (1,568 s total; measured 24 logical cores / 32 GB RAM) |
| Output root | `Climate/output/`, `Finance/output/`, `Composite/output/` |
| Environment | conda env `climada_env`, Python 3.11.13, 232 packages, `env/requirements_frozen.txt` |

**Windows + PowerShell is the supported path.** The four Windows-specific traps
below (GDAL/PROJ, DLL preloading, TLS shim) are all handled by `env\run.ps1` and
`env\bootstrap.py`; do not call `python` directly.

---

## 1. Build the environment

```powershell
conda create -n climada_env -c conda-forge --file env\requirements_frozen.txt
```

Key versions used for the published run:

```
climada 6.1.0     GDAL 3.10.3      geopandas 1.1.3   rasterio 1.4.4
shapely 2.1.2     fiona 1.10.1     numpy 2.3.5       pandas 2.3.3
xarray 2025.6.1   h5py 3.16.0      pyarrow 21.0.0    Cartopy 0.25.0
```

Then open `env\run.ps1` and set the **one** line at the top:

```powershell
$env:CONDA_PREFIX = 'C:\path\to\miniforge3\envs\climada_env'
```

Self-check (must print `G3 SELF-CHECK = PASS`):

```powershell
env\run.ps1 tools\_env_selfcheck.py
```

---

## 2. Fetch the eight oversized files from the Release

GitHub rejects any single file above 100 MiB, and eight of the original inputs /
intermediates are larger than that. They are attached **unmodified** to the
release tagged `v1.0.0` of this repository. See `RELEASE_ASSETS.md` for the full
table and `release_assets.json` for the machine-readable mapping.

Easiest:

```powershell
powershell -ExecutionPolicy Bypass -File .\fetch_release_assets.ps1
```

Manual alternative: download each asset from

```
https://github.com/13162563982/shanghai-climate-risk-repro/releases/tag/v1.0.0
```

and drop it at the path listed in `RELEASE_ASSETS.md`. The script verifies the
SHA-256 after every download, so a clean run is proof that the bytes match.

---

## 3. Verify the checked-in files

```powershell
certutil -hashfile Climate\05_risk.py SHA256      # Windows, one file
```

or, on any platform with coreutils:

```bash
sha256sum -c SHA256SUMS.txt
```

`manifest.json` records path, size and SHA-256 for **every** file in both the
repository and the release, together with the provenance-card id it belongs to.

---

## 4. Run the model

```powershell
env\run.ps1 run_v8.py                      # full chain, 11 steps
env\run.ps1 run_v8.py --only C05           # a single step
env\run.ps1 run_v8.py --from C05 --to C07  # a range
```

Measured wall-clock per step (24 cores / 32 GB):

| step | script | time |
|---|---|---|
| C01 | `01_hazard_tc.py` — tropical-cyclone wind hazard | 324.5 s |
| C03 | `03_exposure.py` — building exposure | 29.8 s |
| C02 | `02_hazard_surge.py` — storm-surge hazard | 131.8 s |
| C04 | `04_vulnerability.py` — vulnerability functions | 5.6 s |
| C05 | `05_risk.py` — compound risk | 261.1 s |
| C06 | `06_defense_sensitivity.py` — defence sensitivity | 577.7 s |
| C07 | `07_climate_index.py` — climate risk index | 5.6 s |
| F01 | `01a_climate_cvar.py` — climate CVaR | 226.4 s |
| F02 | `01_finance_risk_index.py` — finance risk index | 1.6 s |
| F03 | `02_fri_projection.py` — FRI Monte-Carlo projection | 2.5 s |
| X01 | `01_composite_index.py` — CFCI composite | 1.8 s |
| | **total** | **1,568.4 s ≈ 26 min** |

Each step appends a JSONL record (`step_id`, `elapsed_s`, `return_code`) to
`_v8_logs\run_<timestamp>.jsonl`, so you can audit what you actually ran.

Figures:

```powershell
env\run.ps1 Climate\generate_figures_new.py
env\run.ps1 Finance\generate_figures.py
env\run.ps1 Composite\generate_figures.py
```

Sensitivity sweep (the slow one, paper Table 8): `env\run.ps1 run_sensitivity.py`
— ≈ 10.5 h, 17 sweeps × 85 values.

---

## 5. Check that you reproduced the paper

The repository already ships the frozen outputs, so a reproduction run should
**overwrite them with identical numbers**. Compare:

| quantity | file |
|---|---|
| building-level risk panel (all scenarios) | `Climate\output\results\risk_panel_all_scenarios_high_confidence.csv` |
| building-level risk panel (baseline) | `Climate\output\results\risk_panel_high_confidence.csv` |
| city CRI projection | `Climate\output\results\shanghai_city_cri_projection.csv` |
| defensive-profile EAL | `Climate\output\results\defense_profile_eal.csv` |
| finance risk index & projection | `Finance\output\results\shanghai_finance_risk_index.csv`, `shanghai_fri_projection.csv` |
| composite CFCI | `Composite\output\results\shanghai_cfci_projection.csv` |
| temperature-elasticity series | `Climate\output\intermediate\alpha_temp_series.csv` |

`git status` after a run tells you immediately which result files moved: a clean
tree means bit-level agreement. (Monte-Carlo paths under `*.npz` are seeded, so
they should also come back unchanged; if the `npz` files differ while the CSVs
do not, check the NumPy/BLAS version — the CSVs are the reported quantities.)

---

## 6. The four Windows traps (already handled — do not fight them)

| # | symptom | handled in |
|---|---|---|
| 1 | `rasterio.errors.CRSError: proj.db … LAYOUT.VERSION.MINOR` | `env\run.ps1` sets `GDAL_DATA`/`PROJ_DATA`; `00_config.py:init_environment()` re-derives the env root from `sys.executable` |
| 2 | same-named DLLs loaded from a stray Anaconda install | `env\run.ps1` strips `anaconda3` from `PATH` and prepends the conda dirs |
| 3 | `ssl.SSLError: [ASN1: NOT_ENOUGH_DATA]` on `import climada` | `env\sitecustomize.py` wraps `SSLContext.load_default_certs` and falls back to certifi (certificate verification is **not** disabled) |
| 4 | `fiona`/`pyarrow` cannot find `gdal.dll` / `arrow*.dll` | `env\bootstrap.py` preloads them by absolute path with `ctypes.CDLL` |

`env\run.ps1` must stay pure ASCII: Windows PowerShell 5.1 reads `.ps1` files
with the system ANSI code page and would mangle CJK paths.

---

## 7. On Linux / macOS

Every data path in the model is derived from
`PROJECT_ROOT = Path(__file__).resolve().parent.parent`, and there is not a
single hard-coded drive letter in the pipeline. The only platform-specific
parts are the launcher (`env\run.ps1`) and the DLL preloading in
`env\bootstrap.py`. On POSIX, export the equivalent variables and run the
driver directly:

```bash
export CONDA_PREFIX=/path/to/envs/climada_env
export GDAL_DATA=$CONDA_PREFIX/share/gdal
export PROJ_DATA=$CONDA_PREFIX/share/proj
export PYTHONIOENCODING=utf-8
python run_v8.py
```

`sitecustomize.py` and `bootstrap.py` become no-ops there (no Windows DLL
preloading, and the TLS shim only activates on the ASN1 failure).

---

## 8. Where the data came from

`DATA_SOURCES.md` is the human-readable table; `provenance/Dxx.yaml` is the
machine-readable card for each dataset (producer, upstream identifier, licence,
acquisition channel, which files in this repository it corresponds to, and how
the paper uses it). Both are generated from the same ledger that renders the
manuscript's Data Availability statement.
