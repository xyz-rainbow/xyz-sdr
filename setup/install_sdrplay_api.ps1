# xyz-sdr — instalar SDRplay API v3.15 (bundled / Downloads / URL)
$ErrorActionPreference = "Stop"

$Root = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $Root

Write-Host ""
Write-Host "xyz-sdr: instalador SDRplay API v3.15..." -ForegroundColor Cyan
Write-Host "(Puede aparecer UAC / ventana del instalador oficial)" -ForegroundColor DarkGray
Write-Host ""

$Pycache = Join-Path $Root "var\pycache"
New-Item -ItemType Directory -Force -Path $Pycache | Out-Null
$env:PYTHONPYCACHEPREFIX = $Pycache
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $PSScriptRoot "install_sdrplay_api.py"

if (Test-Path -LiteralPath $VenvPy) {
    & "$VenvPy" "$Script" @args
    exit $LASTEXITCODE
}

$hasPython = Get-Command python -ErrorAction SilentlyContinue
if (-not $hasPython) {
    Write-Host "[ERROR] Python no encontrado. Ejecuta: .\setup\install_drivers.ps1" -ForegroundColor Red
    Write-Host "Presiona cualquier tecla para salir..." -ForegroundColor Gray
    [void][System.Console]::ReadKey()
    exit 1
}

& python "$Script" @args
exit $LASTEXITCODE
