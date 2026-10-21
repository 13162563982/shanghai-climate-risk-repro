<#
    Packaged entry point - the ONLY supported way to launch the pipeline.

    Usage (from the package root):
        env\run.ps1 run_v8.py
        env\run.ps1 run_v8.py --only C01
        env\run.ps1 run_v8.py --from C03 --to C04
        env\run.ps1 Climate\generate_figures_new.py --only basic_facts
        env\run.ps1 run_sensitivity.py

    What it does:
      1. pins CONDA_PREFIX (the single place to edit if the env moves)
      2. removes any anaconda3 entries from PATH and prepends the conda dirs
      3. sets GDAL_DATA / PROJ_DATA / PROJ_LIB and SSL_CERT_FILE
      4. puts env\ on PYTHONPATH so sitecustomize.py (SSL shim) is imported
      5. dispatches through env\bootstrap.py, which preloads the shared DLLs

    KEEP THIS FILE PURE ASCII. Windows PowerShell 5.1 reads .ps1 content using
    the system ANSI code page, so non-ASCII characters (including CJK paths)
    get mangled. All paths here are derived from $PSScriptRoot or CONDA_PREFIX.
#>
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'

# --- 1. the one environment constant -------------------------------------
$env:CONDA_PREFIX = 'C:\Users\Jack\miniforge3\envs\climada_env'
$e = $env:CONDA_PREFIX

if (-not (Test-Path (Join-Path $e 'python.exe'))) {
    Write-Host "[run.ps1] ERROR python.exe not found under CONDA_PREFIX=$e" -ForegroundColor Red
    Write-Host "[run.ps1] Edit the CONDA_PREFIX line at the top of this script."
    exit 1
}

# --- 2. scrub the polluted PATH ------------------------------------------
$keep = ($env:PATH -split ';' | Where-Object { $_ -and ($_ -notmatch 'anaconda3') })
$env:PATH = "$e\Library\bin;$e\Library\usr\bin;$e\Library\mingw-w64\bin;$e;$e\Scripts;" + ($keep -join ';')

# --- 3. geospatial + TLS variables ---------------------------------------
$env:GDAL_DATA     = "$e\Library\share\gdal"
$env:PROJ_DATA     = "$e\Library\share\proj"
$env:PROJ_LIB      = "$e\Library\share\proj"
$env:SSL_CERT_FILE = "$e\Lib\site-packages\certifi\cacert.pem"

# --- 4. import path + I/O encoding ---------------------------------------
$env:PYTHONPATH       = $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:V8_PYTHON        = "$e\python.exe"

# --- 5. dispatch ----------------------------------------------------------
& "$e\python.exe" (Join-Path $PSScriptRoot 'bootstrap.py') @Rest
exit $LASTEXITCODE
