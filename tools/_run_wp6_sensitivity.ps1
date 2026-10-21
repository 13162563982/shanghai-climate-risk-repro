<#
    WP6 (sensitivity sweep) driver + post-run baseline recovery.

    Usage (from the package root, no pipe, no redirection):
        .\tools\_run_wp6_sensitivity.ps1 -DryRun      # inventory + pre-flight only
        .\tools\_run_wp6_sensitivity.ps1              # sweep, then post-run recovery
        .\tools\_run_wp6_sensitivity.ps1 -Stage post  # post-run recovery only

    Why a driver:
      * KEEP THIS FILE PURE ASCII. Windows PowerShell reads .ps1 using the system
        ANSI code page, so CJK literals get mangled. Every CJK path is resolved
        at runtime, never written out.
      * The post-run main-chain rerun needs the three pins. In a NEW shell
        V8_PARAM_OVERRIDES is empty, which silently switches C01 back to the
        CURRENT IBTrACS file (108 events / frequency 1/82) and to the config
        fallback Knutson factors (1.05/1.10). Re-pinning is automated here.

    Facts about the sweep this driver verifies before starting
    (re-measured 2026-10-17; the earlier "81 values" note was wrong):
      * config\sensitivity_sweep.json holds 17 sweeps / 85 parameter values
        (16 sweeps x 5 scalar values + 1 tuple sweep `FRI_WEIGHT_GAP` x 5 rows).
        run_sensitivity.py handles both `values` and `values_tuples`.
      * run_sensitivity.STEP_SCRIPTS covers C04..X01 only - C01/C02/C03 are NEVER
        run inside the sweep, so the hazard HDF5s from the WP5-A run are reused
        and the IBTrACS pin does not affect the sweep itself.
      * restore_baseline() runs the full C04..X01 chain once before EVERY sweep
        (17 times), which is why the wall-clock cost is dominated by restores.
      * Estimated wall clock: ~17-19 h from the measured WP5-A per-step times.
        Only the per-step times are measured; the total is an extrapolation and
        has never been observed end to end. Treat it as a budget, not a promise.
#>

param(
    [ValidateSet('all', 'sweep', 'post')]
    [string]$Stage = 'all',
    [switch]$DryRun
)

$NR = Split-Path -Parent $PSScriptRoot
$IBTRACS_NAME = 'IBTrACS.WP.v04r01_old_202510.nc'
$IBTRACS_SIZE = 8904634
$IBTRACS_SHA  = 'DA05013357E6ADFC11DAE72C5830BED602A6C2AAFC3F3C228653850BA8DEF91D'
$MIN_FREE_GB  = 60

$ErrorActionPreference = 'Continue'

function Fail($msg) {
    Write-Host "[WP6] ABORT: $msg" -ForegroundColor Red
    exit 2
}

function Step($msg) {
    Write-Host ''
    Write-Host "=== $msg ===" -ForegroundColor Cyan
}

# Resolve + verify the pinned IBTrACS snapshot, then set the three pins.
function Set-Pins {
    $hits = @(Get-ChildItem -Path (Join-Path $NR 'data') -Filter $IBTRACS_NAME -Recurse -File -ErrorAction SilentlyContinue)
    if ($hits.Count -ne 1) { Fail "expected exactly 1 match for $IBTRACS_NAME under data\, found $($hits.Count)" }
    if ($hits[0].Length -ne $IBTRACS_SIZE) { Fail "IBTrACS size $($hits[0].Length) <> $IBTRACS_SIZE" }
    $sha = (Get-FileHash -LiteralPath $hits[0].FullName -Algorithm SHA256).Hash
    if ($sha -ne $IBTRACS_SHA) { Fail "IBTrACS SHA256 $sha <> $IBTRACS_SHA" }
    $ov = [ordered]@{
        IBTRACS_FILE                            = $hits[0].FullName
        'SSP_TC_INTENSITY_FACTOR_2050.SSP2-4.5' = 1.0324
        'SSP_TC_INTENSITY_FACTOR_2050.SSP5-8.5' = 1.0442
    }
    $env:V8_PARAM_OVERRIDES = ($ov | ConvertTo-Json -Compress)
    if ($env:V8_PARAM_OVERRIDES -match 'ADMIN_BOUNDARY|COASTLINE_BOUNDARY') {
        Fail 'overrides must not pin the boundary layers (option A is in force)'
    }
    Write-Host "[WP6] pins set (IBTrACS $IBTRACS_SIZE B, SHA verified; Knutson 1.0324 / 1.0442)"
    return $hits[0].FullName
}

Write-Host '============================================================'
Write-Host 'WP6 - sensitivity sweep + post-run baseline recovery'
Write-Host '============================================================'
Write-Host "[WP6] package root : $NR"
Write-Host "[WP6] stage        : $Stage"
Write-Host "[WP6] started      : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# ---------------------------------------------------------------- pre-flight
Step 'pre-flight'

$other = @(Get-Process -Name python -ErrorAction SilentlyContinue)
if ($other.Count -gt 0) { Fail "$($other.Count) python.exe already running (one C01 at a time)" }
Write-Host '  [OK] no stray python.exe'

$freeGb = [math]::Round((Get-PSDrive D).Free / 1GB, 1)
if ($freeGb -lt $MIN_FREE_GB) { Fail "only $freeGb GB free on D: (need >= $MIN_FREE_GB GB)" }
Write-Host "  [OK] D: free = $freeGb GB"

foreach ($pair in @(
        @{ f = 'Climate\00_config.py';         s = 'COASTLINE_BOUNDARY_SHP = ADMIN_BOUNDARY_LEGACY_SHP' },
        @{ f = 'Climate\climate_functions.py'; s = '_coast_shp = getattr(config, "COASTLINE_BOUNDARY_SHP"' }
    )) {
    $p = Join-Path $NR $pair.f
    if (-not (Test-Path -LiteralPath $p)) { Fail "missing $($pair.f)" }
    if (-not (Select-String -LiteralPath $p -SimpleMatch -Pattern $pair.s -Quiet)) {
        Fail "option-A edit absent in $($pair.f)"
    }
}
Write-Host '  [OK] option-A edits in place (coastline decoupled)'

$sweepCfg = Join-Path $NR 'config\sensitivity_sweep.json'
if (-not (Test-Path -LiteralPath $sweepCfg)) { Fail "missing $sweepCfg" }
$j = Get-Content -LiteralPath $sweepCfg -Raw | ConvertFrom-Json
$nSweeps = @($j.sweeps).Count
# Some sweeps use "values" (scalar), one uses "values_tuples" (FRI_WEIGHTS).
# run_sensitivity.py handles both, so count both here to match the runtime.
$nVals = 0
$nTuple = 0
foreach ($s in $j.sweeps) {
    if ($s.PSObject.Properties.Name -contains 'values_tuples') {
        $nVals += @($s.values_tuples).Count
        $nTuple += 1
    } else {
        $nVals += @($s.values).Count
    }
}
$nRestores = $nSweeps
Write-Host "  [OK] sweep config: $nSweeps sweeps / $nVals parameter values ($nTuple tuple sweep)"
Write-Host ('  [i]  estimate: ~17.4 h wall clock (12.9 h variations + 4.6 h for ' + $nRestores + ' baseline restores)')
Write-Host '  [i]  C01/C02/C03 are NOT part of any sweep: the WP5-A hazard HDF5s are reused'

$ibtracs = Set-Pins
if ($DryRun) {
    Write-Host ''
    Write-Host '[WP6] DRY RUN - all pre-flight checks passed, nothing launched.'
    exit 0
}

$t0 = Get-Date
$rcSweep = 0
$rcMain = 0

# ---------------------------------------------------------------- sweep
if ($Stage -in @('all', 'sweep')) {
    Step 'WP6.1  run_sensitivity.py'
    & "$NR\env\run.ps1" run_sensitivity.py
    $rcSweep = $LASTEXITCODE
    Write-Host "[WP6] run_sensitivity.py exit code = $rcSweep"
    if ($rcSweep -ne 0) {
        Write-Host '[WP6] sweep FAILED - skipping post-run recovery; outputs may be mid-sweep.' -ForegroundColor Red
        Write-Host '[WP6] Fix and re-run with:  .\tools\_run_wp6_sensitivity.ps1 -Stage post'
        exit $rcSweep
    }
}

# ---------------------------------------------------------------- recovery
if ($Stage -in @('all', 'post')) {
    Step 'WP6.2  re-pin and restore the main baseline (run_v8.py, ~25-30 min)'
    Write-Host '  [i] run_sensitivity restores C04..X01 but a clean full chain plus the'
    Write-Host '  [i] three pins is what the manuscript numbers must be rebuilt from.'
    $null = Set-Pins
    & "$NR\env\run.ps1" run_v8.py
    $rcMain = $LASTEXITCODE
    Write-Host "[WP6] run_v8.py exit code = $rcMain"

    Step 'WP6.3  regenerate the 41 figures'
    & "$NR\env\run.ps1" "$NR\Climate\generate_figures_new.py"
    & "$NR\env\run.ps1" "$NR\Finance\generate_figures.py"
    & "$NR\env\run.ps1" "$NR\Composite\generate_figures.py"
    & "$NR\env\run.ps1" "$NR\tools\gen_sensitivity_figures.py" --out "$NR\manuscript\figures"
    & "$NR\env\run.ps1" "$NR\tools\_wp5_figure_label_check.py"

    Step 'WP6.4  archive the sensitivity results'
    $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
    & "$NR\env\run.ps1" "$NR\tools\_archive_outputs.py" "wp6_sensitivity_$ts" --with-sensitivity
}

$elapsed = (Get-Date) - $t0
Write-Host ''
Write-Host '============================================================'
Write-Host ("[WP6] done. sweep rc={0}  main rc={1}  elapsed={2:dd}d {2:hh}h{2:mm}m" -f $rcSweep, $rcMain, $elapsed)
Write-Host '============================================================'
Write-Host ''
Write-Host 'STILL MANUAL (see the breakpoint record, docs section 6):'
Write-Host '  * recompute all 20 rows of Table 8 from _sensitivity_results:'
Write-Host '      env\run.ps1 tools\audit_manuscript_consistency.py   (build_table8_row)'
Write-Host '  * then WP7 manuscript rewrite: 48 of the 60 frozen values changed.'
exit ([math]::Max($rcSweep, $rcMain))
