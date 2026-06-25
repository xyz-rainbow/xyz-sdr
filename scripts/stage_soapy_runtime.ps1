# xyz-sdr — stage minimal Soapy runtime from Pothos into drivers/win-x64/soapy/
param(
    [string]$PothosRoot = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$Root = Split-Path $PSScriptRoot -Parent
if (-not $Root) {
    $Root = (Get-Location).Path
}

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPy)) {
    throw "venv missing: $VenvPy — run setup/install_drivers.ps1 first"
}

$env:PYTHONPYCACHEPREFIX = Join-Path $Root "var\pycache"

$pyArgs = @("-m", "core.stage_soapy_runtime")
if ($PothosRoot) { $pyArgs += @("--pothos-root", $PothosRoot) }
if ($DryRun) { $pyArgs += "--dry-run" }

Push-Location -LiteralPath $Root
try {
    & $VenvPy @pyArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
