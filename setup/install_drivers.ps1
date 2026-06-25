# ============================================================
# xyz-sdr | install_drivers.ps1
# Wrapper PowerShell — prefiere .venv del proyecto si existe
# ============================================================

$ErrorActionPreference = "Stop"

$Root = Split-Path $PSScriptRoot -Parent
$Pycache = Join-Path $Root "var\pycache"
New-Item -ItemType Directory -Force -Path $Pycache | Out-Null
$env:PYTHONPYCACHEPREFIX = $Pycache
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $VenvPy) {
    & "$VenvPy" (Join-Path $PSScriptRoot "install_drivers.py") @args
    exit $LASTEXITCODE
}

$hasPython = Get-Command python -ErrorAction SilentlyContinue

if (-not $hasPython) {
    Write-Host "`n[XX] Error: Python no encontrado." -ForegroundColor Red
    Write-Host "Instala Python 3.12 o ejecuta: winget install Python.Python.3.12" -ForegroundColor Yellow
    Write-Host "Presiona cualquier tecla para salir..." -ForegroundColor Gray
    [void][System.Console]::ReadKey()
    exit 1
}

python (Join-Path $PSScriptRoot "install_drivers.py") @args
