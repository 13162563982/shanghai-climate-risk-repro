<#
    WP5 (option A) driver - rebuild the official-boundary run with the storm-surge
    shoreline decoupled onto the fine township layer (config.COASTLINE_BOUNDARY_SHP).

    Usage (from the package root, no pipe, no redirection):
        .\tools\_run_wp5_option_a.ps1
        .\tools\_run_wp5_option_a.ps1 -DryRun     # pre-flight checks only

    Why a driver instead of an inline command:
      * KEEP THIS FILE PURE ASCII. Windows PowerShell reads .ps1 using the system
        ANSI code page, so CJK literals get mangled. Every CJK path here is
        resolved at runtime (Get-ChildItem / $PSScriptRoot), never written out.
      * It enforces the three hard pins before the ~28 min run starts, so a wrong
        configuration fails in seconds instead of after half an hour.

    Pins enforced (see the breakpoint record, docs sections 3 and 4):
      1. IBTRACS_FILE -> the 2025-10 snapshot (107 events, NOT the 108-event one)
      2. SSP2-4.5 / SSP5-8.5 Knutson factors -> 1.0324 / 1.0442
      3. ADMIN_BOUNDARY_SHP is deliberately NOT overridden: it stays the official
         GS(2024)0650 layer; only the shoreline reads the fine layer.
#>

param([switch]$DryRun)

$NR = Split-Path -Parent $PSScriptRoot
$PY = 'C:\Users\Jack\miniforge3\envs\climada_env\python.exe'
$IBTRACS_NAME = 'IBTrACS.WP.v04r01_old_202510.nc'
$IBTRACS_SIZE = 8904634
$IBTRACS_SHA  = 'DA05013357E6ADFC11DAE72C5830BED602A6C2AAFC3F3C228653850BA8DEF91D'

function Fail($msg) {
    Write-Host "[WP5-A] ABORT: $msg" -ForegroundColor Red
    exit 2
}

Write-Host '============================================================'
Write-Host 'WP5 (option A) - official boundary, decoupled shoreline'
Write-Host '============================================================'
Write-Host "[WP5-A] package root : $NR"
Write-Host "[WP5-A] started      : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# --- pre-flight 1: exactly one C01 at a time -------------------------------
$other = @(Get-Process -Name python -ErrorAction SilentlyContinue)
if ($other.Count -gt 0) {
    Fail "$($other.Count) python.exe already running (constraint: one C01 at a time)"
}
Write-Host '[WP5-A] CHECK no stray python.exe : OK'

# --- pre-flight 2: resolve + verify the pinned IBTrACS snapshot ------------
$hits = @(Get-ChildItem -Path (Join-Path $NR 'data') -Filter $IBTRACS_NAME -Recurse -File -ErrorAction SilentlyContinue)
if ($hits.Count -ne 1) { Fail "expected exactly 1 match for $IBTRACS_NAME under data\, found $($hits.Count)" }
$ibtracs = $hits[0].FullName
if ($hits[0].Length -ne $IBTRACS_SIZE) { Fail "IBTrACS size $($hits[0].Length) <> $IBTRACS_SIZE" }
$sha = (Get-FileHash -LiteralPath $ibtracs -Algorithm SHA256).Hash
if ($sha -ne $IBTRACS_SHA) { Fail "IBTrACS SHA256 $sha <> $IBTRACS_SHA" }
Write-Host "[WP5-A] CHECK IBTrACS pinned      : OK  ($IBTRACS_SIZE B, SHA verified)"

# --- pre-flight 3: the decoupled shoreline resolves to the fine layer -------
# ASCII-only filter: the fine township layer is '2021*.shp' (its CJK stem must
# not appear as a literal here - see the header note on ANSI code pages).
$coast = Get-ChildItem -Path (Join-Path $NR 'data') -Filter '2021*.shp' -Recurse -File -ErrorAction SilentlyContinue |
         Where-Object { $_.DirectoryName -notmatch 'GS2024' } | Select-Object -First 1
if (-not $coast) { Fail 'fine township layer .shp not found under data\' }
Write-Host "[WP5-A] CHECK fine layer present  : OK  ($($coast.Length) B)"

# --- pre-flight 4: the edited sources are the option-A revision ------------
$must = @{
    (Join-Path $NR 'Climate\00_config.py')            = 'COASTLINE_BOUNDARY_SHP = ADMIN_BOUNDARY_LEGACY_SHP'
    (Join-Path $NR 'Climate\climate_functions.py')    = '_coast_shp = getattr(config, "COASTLINE_BOUNDARY_SHP"'
}
foreach ($f in $must.Keys) {
    if (-not (Test-Path -LiteralPath $f)) { Fail "missing source $f" }
    if (-not (Select-String -LiteralPath $f -SimpleMatch -Pattern $must[$f] -Quiet)) {
        Fail "option-A edit absent in $f"
    }
}
Write-Host '[WP5-A] CHECK option-A edits in place : OK'

# --- the three pins -------------------------------------------------------
$ov = [ordered]@{
    IBTRACS_FILE                           = $ibtracs
    'SSP_TC_INTENSITY_FACTOR_2050.SSP2-4.5' = 1.0324
    'SSP_TC_INTENSITY_FACTOR_2050.SSP5-8.5' = 1.0442
}
$env:V8_PARAM_OVERRIDES = ($ov | ConvertTo-Json -Compress)
if ($env:V8_PARAM_OVERRIDES -match 'ADMIN_BOUNDARY') { Fail 'overrides must not pin ADMIN_BOUNDARY_SHP' }
Write-Host "[WP5-A] overrides   : $env:V8_PARAM_OVERRIDES"

if ($DryRun) {
    Write-Host '[WP5-A] DRY RUN - all pre-flight checks passed, pipeline NOT launched.'
    exit 0
}

# --- run header for the archive ------------------------------------------
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$hdr = [ordered]@{
    work_package      = 'WP5-optionA'
    started           = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    package_root      = $NR
    overrides         = $env:V8_PARAM_OVERRIDES
    ibtracs_path      = $ibtracs
    ibtracs_sha256    = $sha
    coastline_layer   = $coast.FullName
    config_sha256     = (Get-FileHash -LiteralPath (Join-Path $NR 'Climate\00_config.py') -Algorithm SHA256).Hash
    climate_fn_sha256 = (Get-FileHash -LiteralPath (Join-Path $NR 'Climate\climate_functions.py') -Algorithm SHA256).Hash
    python            = $PY
}
New-Item -ItemType Directory -Force -Path (Join-Path $NR 'output_archive') | Out-Null
$hdrPath = Join-Path $NR "output_archive\_wp5a_header_$ts.json"
$hdr | ConvertTo-Json | Set-Content -LiteralPath $hdrPath -Encoding UTF8
Set-Content -LiteralPath (Join-Path $NR 'output_archive\_wp5a_run_ts.txt') -Value $ts -Encoding ASCII
Write-Host "[WP5-A] run header  : $hdrPath"

# --- dispatch: direct call, NO pipe, NO redirection ------------------------
Write-Host '[WP5-A] launching run_v8.py (11 steps, ~28 min) ...'
Write-Host '------------------------------------------------------------'
$t0 = Get-Date
& "$NR\env\run.ps1" run_v8.py
$rc = $LASTEXITCODE
$elapsed = (Get-Date) - $t0
Write-Host '------------------------------------------------------------'
Write-Host ("[WP5-A] run_v8.py exit code = {0}   elapsed = {1:hh\:mm\:ss}" -f $rc, $elapsed)
Write-Host "[WP5-A] finished    : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$hdr['exit_code'] = $rc
$hdr['elapsed_s'] = [int]$elapsed.TotalSeconds
$hdr['finished']  = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
$hdr | ConvertTo-Json | Set-Content -LiteralPath $hdrPath -Encoding UTF8
if ($rc -ne 0) { Write-Host "[WP5-A] NON-ZERO EXIT - inspect _v8_logs before archiving" -ForegroundColor Red }
exit $rc
