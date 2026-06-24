# xyz-sdr — ejecutar la aplicación (requiere .venv)
$Root = Split-Path -Parent $PSScriptRoot
$Pycache = Join-Path $Root "var\pycache"
New-Item -ItemType Directory -Force -Path $Pycache | Out-Null
$env:PYTHONPYCACHEPREFIX = $Pycache
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
    chcp 65001 | Out-Null
} catch {
    # Consola sin soporte UTF-8; splash usará fallback ASCII
}
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
$Main = Join-Path $Root "main.py"

if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Host "`n[XX] Entorno .venv no encontrado." -ForegroundColor Red
    Write-Host "  1. .\setup\install_drivers.ps1  → [1] Instalar o reparar todo" -ForegroundColor Yellow
    Write-Host "  2. .\scripts\run.ps1" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

& $VenvPy $Main @args
exit $LASTEXITCODE
