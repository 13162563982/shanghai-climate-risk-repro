<#
    fetch_release_assets.ps1 - download the oversized release assets and
    put them where the model expects them.

    GitHub rejects any single file above 100 MiB and a git push above 2 GiB, so the
    big inputs/artefacts of this project live as Release assets instead of git
    objects (eight files exceed the limit; 18 assets are attached because the
    shapefile companions travel with their .shp).  This script downloads them,
    verifies SHA-256 and copies them to the exact repository-relative path
    recorded in release_assets.json.

    KEEP THIS FILE PURE ASCII: Windows PowerShell 5.1 reads .ps1 with the system
    ANSI code page, so CJK paths are handled through the UTF-8 JSON payload.

    Usage (from the repository root):
        powershell -ExecutionPolicy Bypass -File .\fetch_release_assets.ps1
        powershell -ExecutionPolicy Bypass -File .\fetch_release_assets.ps1 -Repo owner/name -Tag v1.0.0
#>
param(
    [string]$Repo = '13162563982/shanghai-climate-risk-repro',
    [string]$Tag  = 'v1.0.0',
    [string]$Manifest = (Join-Path $PSScriptRoot 'release_assets.json')
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if (-not (Test-Path $Manifest)) {
    Write-Host "[fetch] manifest not found: $Manifest" -ForegroundColor Red
    exit 1
}

$spec = Get-Content -Raw -Encoding UTF8 $Manifest | ConvertFrom-Json
$assets = $spec.assets
$base = "https://github.com/$Repo/releases/download/$Tag"

Write-Host "[fetch] repo   : $Repo"
Write-Host "[fetch] release: $Tag"
Write-Host "[fetch] assets : $($assets.Count)"
Write-Host ""

$fail = 0
foreach ($a in $assets) {
    $target = Join-Path $PSScriptRoot ($a.repository_path -replace '/', '\')
    $dir = Split-Path $target -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

    $name = $a.asset
    Write-Host ("[fetch] {0}  ({1:N0} bytes)" -f $name, $a.bytes)

    if (Test-Path $target) {
        $have = (Get-FileHash -Algorithm SHA256 -Path $target).Hash.ToLower()
        if ($have -eq $a.sha256) {
            Write-Host "        already present and verified - skipped" -ForegroundColor Green
            continue
        }
        Write-Host "        existing file has a different hash - re-downloading" -ForegroundColor Yellow
    }

    $url = "$base/$name"
    $tmp = "$target.part"
    try {
        Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing -TimeoutSec 3600
    } catch {
        Write-Host "        download failed: $($_.Exception.Message)" -ForegroundColor Red
        if (Test-Path $tmp) { Remove-Item $tmp -Force }
        $fail++
        continue
    }

    $got = (Get-FileHash -Algorithm SHA256 -Path $tmp).Hash.ToLower()
    if ($got -ne $a.sha256) {
        Write-Host "        SHA-256 mismatch" -ForegroundColor Red
        Write-Host "          expected $($a.sha256)"
        Write-Host "          got      $got"
        Remove-Item $tmp -Force
        $fail++
        continue
    }

    Move-Item -Force $tmp $target
    Write-Host "        ok -> $($a.repository_path)" -ForegroundColor Green
}

Write-Host ""
if ($fail -gt 0) {
    Write-Host "[fetch] $fail asset(s) failed - the tree is incomplete." -ForegroundColor Red
    exit 2
}
Write-Host "[fetch] all assets present and SHA-256 verified." -ForegroundColor Green

# quick consistency check against the checked-in checksum list
$sums = Join-Path $PSScriptRoot 'SHA256SUMS.txt'
if (Test-Path $sums) {
    Write-Host "[fetch] repository-level checksums are in SHA256SUMS.txt (verify with sha256sum -c)."
}
exit 0
