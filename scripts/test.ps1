# xyz-sdr — ejecutar tests (config pytest en pyproject.toml)
$Root = Split-Path -Parent $PSScriptRoot
$env:PYTHONUTF8 = "1"
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $VenvPy) {
    & $VenvPy -c @"
import sys
from pathlib import Path
ROOT = Path(r'$Root')
sys.path.insert(0, str(ROOT))
from core.runtime_paths import bootstrap_project_caches, install_venv_pycache_hook, remove_stray_project_caches
bootstrap_project_caches(ROOT)
remove_stray_project_caches(ROOT)
install_venv_pycache_hook(ROOT)
"@
    Set-Location -LiteralPath $Root
    & $VenvPy -m pytest @args
    exit $LASTEXITCODE
}

Write-Host "`n[XX] Entorno .venv no encontrado." -ForegroundColor Red
Write-Host "  1. .\setup\install_drivers.ps1  -> [1] Instalar o reparar todo" -ForegroundColor Yellow
Write-Host "  2. .\scripts\test.ps1" -ForegroundColor Yellow
Write-Host ""
exit 1
