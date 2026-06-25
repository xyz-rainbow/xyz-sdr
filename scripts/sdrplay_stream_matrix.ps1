# xyz-sdr — matriz Soapy SDRplay RX (sub-fase 0.2 — evidencia completa)
param(
    [string]$OutDir = "var/log",
    [switch]$DryRun,
    [switch]$SkipServiceRestart,
    [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"

$Root = Split-Path $PSScriptRoot -Parent
$env:PYTHONPYCACHEPREFIX = Join-Path $Root "var\pycache"
$env:XYZ_SDR_PREFLIGHT_TIMEOUT = "$TimeoutSeconds"

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPy)) {
    throw "venv missing: $VenvPy — run setup/install_drivers.ps1 first"
}

$LogDir = if ([System.IO.Path]::IsPathRooted($OutDir)) { $OutDir } else { Join-Path $Root $OutDir }
$DumpsDir = Join-Path $LogDir "dumps"
[void][System.IO.Directory]::CreateDirectory($LogDir)
[void][System.IO.Directory]::CreateDirectory($DumpsDir)

function Write-LiteralUtf8 {
    param([string]$Path, [string]$Content)
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

$ServiceLog = Join-Path $LogDir "service-events.txt"
$ts = (Get-Date).ToUniversalTime().ToString("o")

Write-Host ""
Write-Host "=== xyz-sdr SDRplay stream matrix (0.2) ===" -ForegroundColor Cyan
Write-Host ""

$sdrProcs = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match 'SDRuno|SDRConsole|sdrconsole'
}
if ($sdrProcs) {
    Write-Warning "Close SDR Console / SDRuno before matrix: $($sdrProcs.Name -join ', ')"
}

if (-not $SkipServiceRestart) {
    [System.IO.File]::AppendAllText($ServiceLog, "$ts Restart-Service SDRplayAPIService begin`n")
    try {
        Restart-Service SDRplayAPIService -Force -ErrorAction Stop
        [System.IO.File]::AppendAllText($ServiceLog, "$((Get-Date).ToUniversalTime().ToString('o')) Restart-Service OK`n")
    } catch {
        [System.IO.File]::AppendAllText($ServiceLog, "$((Get-Date).ToUniversalTime().ToString('o')) Restart-Service FAIL: $($_.Exception.Message)`n")
        throw
    }
    Start-Sleep -Seconds 10
    $svc = Get-Service SDRplayAPIService
    [System.IO.File]::AppendAllText($ServiceLog, "$((Get-Date).ToUniversalTime().ToString('o')) Service Status=$($svc.Status)`n")
} else {
    [System.IO.File]::AppendAllText($ServiceLog, "$ts SkipServiceRestart`n")
}

$env:XYZ_SDR_MATRIX_SERVICE_EVENTS = $ServiceLog

Write-Host "[>>] python -V + pip freeze..." -ForegroundColor Gray
$pyVerPath = Join-Path $LogDir "python-version.txt"
$pipPath = Join-Path $LogDir "pip-freeze.txt"
$pyVerLine = (& $VenvPy -V 2>&1 | Out-String).Trim()
Write-LiteralUtf8 -Path $pyVerPath -Content ($pyVerLine + "`n")
Write-LiteralUtf8 -Path $pipPath -Content ((& $VenvPy -m pip freeze) | Out-String)

$matrixArgs = @("-m", "core.sdrplay_stream_matrix", "--out-dir", $LogDir, "--timeout", "$TimeoutSeconds")
if ($DryRun) { $matrixArgs += "--dry-run" }

Push-Location -LiteralPath $Root
try {
    & $VenvPy @matrixArgs
    $rc = $LASTEXITCODE
} finally {
    Pop-Location
}

$latestJson = Get-ChildItem -LiteralPath $LogDir -Filter "sdrplay-matrix-*.json" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1

$zipPath = Join-Path $LogDir "sdrplay-matrix-results.zip"
$toZip = @(
    (Join-Path $LogDir "pip-freeze.txt"),
    (Join-Path $LogDir "python-version.txt"),
    (Join-Path $LogDir "service-events.txt")
)
if ($latestJson) { $toZip += $latestJson.FullName }
Get-ChildItem -LiteralPath $DumpsDir -Filter "*.dmp" -ErrorAction SilentlyContinue | ForEach-Object { $toZip += $_.FullName }
Get-ChildItem -LiteralPath $LogDir -Filter "*.dmp" -ErrorAction SilentlyContinue | ForEach-Object { $toZip += $_.FullName }

$existing = @($toZip | Where-Object { $_ -and (Test-Path -LiteralPath $_) })
if ($existing.Count -gt 0) {
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -Path $existing -DestinationPath $zipPath -Force
    Write-Host ""
    Write-Host "[OK] Artefactos para Mario: $zipPath" -ForegroundColor Green
    if ($latestJson) {
        Write-Host "     JSON: $($latestJson.FullName)" -ForegroundColor Gray
    }
}

exit $rc
