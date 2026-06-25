# xyz-sdr — compilar e instalar SoapySDRPlay3 (delega en setup/soapy_sdrplay3.py)
# Instala Git, CMake y VS Build Tools vía winget cuando faltan.

$ErrorActionPreference = "Stop"

$Root = Split-Path $PSScriptRoot -Parent
$Pycache = Join-Path $Root "var\pycache"
New-Item -ItemType Directory -Force -Path $Pycache | Out-Null
$env:PYTHONPYCACHEPREFIX = $Pycache
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"

if (Test-Path $VenvPy) {
    & $VenvPy (Join-Path $PSScriptRoot "soapy_sdrplay3.py") @args
    exit $LASTEXITCODE
}

$hasPython = Get-Command python -ErrorAction SilentlyContinue

if (-not $hasPython) {
    Write-Host "`n[XX] Error: Python no encontrado." -ForegroundColor Red
    Write-Host "Instala Python 3.12 o ejecuta: winget install Python.Python.3.12" -ForegroundColor Yellow
    Write-Host "También puedes usar: .\setup\install_drivers.ps1 → [1] Reparar todo" -ForegroundColor Yellow
    exit 1
}

python (Join-Path $PSScriptRoot "soapy_sdrplay3.py") @args
