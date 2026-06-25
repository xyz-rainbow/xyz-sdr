# xyz-sdr — matriz Soapy SDRplay RX
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
if (-not (Test-Path -LiteralPath $VenvPy)) { throw "venv missing: $VenvPy" }
$LogDir = if ([System.IO.Path]::IsPathRooted($OutDir)) { $OutDir } else { Join-Path $Root $OutDir }
New-Item -ItemType Directory -Force -Path $LogDir, (Join-Path $LogDir "dumps") | Out-Null
Write-Host "=== xyz-sdr SDRplay stream matrix ===" -ForegroundColor Cyan
if (-not $SkipServiceRestart) {
    Restart-Service SDRplayAPIService -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 10
}
& $VenvPy -m pip freeze | Out-File -FilePath (Join-Path $LogDir "pip-freeze.txt") -Encoding utf8
$args = @("-m", "core.sdrplay_stream_matrix", "--out-dir", $LogDir, "--timeout", "$TimeoutSeconds")
if ($DryRun) { $args += "--dry-run" }
Push-Location -LiteralPath $Root
try { & $VenvPy @args; $rc = $LASTEXITCODE } finally { Pop-Location }
$latest = Get-ChildItem -LiteralPath $LogDir -Filter "sdrplay-matrix-*.json" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latest) {
    $zip = Join-Path $LogDir "sdrplay-matrix-results.zip"
    Compress-Archive -Path $latest.FullName, (Join-Path $LogDir "pip-freeze.txt") -DestinationPath $zip -Force
    Write-Host "[OK] Artefactos: $zip" -ForegroundColor Green
}
exit $rc
