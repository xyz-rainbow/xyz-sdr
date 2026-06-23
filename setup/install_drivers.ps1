# ============================================================
# xyz-sdr | install_drivers.ps1
# Wrapper de PowerShell para lanzar el instalador interactivo de Python
# ============================================================

$ErrorActionPreference = "Stop"

# Comprobar si Python está instalado
$hasPython = Get-Command python -ErrorAction SilentlyContinue

if (-not $hasPython) {
    Write-Host "`n[XX] Error: Python 3.10+ no encontrado." -ForegroundColor Red
    Write-Host "Por favor, descarga e instala Python desde https://python.org y asegúrate de marcar 'Add Python to PATH'." -ForegroundColor Yellow
    Write-Host "Presiona cualquier tecla para salir..." -ForegroundColor Gray
    [void][System.Console]::ReadKey()
    exit 1
}

# Ejecutar el instalador interactivo de Python
$scriptPath = Join-Path $PSScriptRoot "install_drivers.py"
python $scriptPath
