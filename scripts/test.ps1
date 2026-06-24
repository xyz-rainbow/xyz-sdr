# xyz-sdr — ejecutar tests (pytest.ini en raíz del repo)
$Root = Split-Path -Parent $PSScriptRoot
$VarDir = Join-Path $Root "var"
$Pycache = Join-Path $VarDir "pycache"
$PytestCache = Join-Path $VarDir "pytest_cache"
$PytestTmp = Join-Path $VarDir "pytest-tmp"
New-Item -ItemType Directory -Force -Path $Pycache, $PytestCache, $PytestTmp | Out-Null
$env:PYTHONPYCACHEPREFIX = $Pycache
$env:PYTHONUTF8 = "1"

@(
    (Join-Path $Root ".pytest_cache"),
    (Join-Path $Root "__pycache__")
) | ForEach-Object {
    Remove-Item -LiteralPath $_ -Recurse -Force -ErrorAction SilentlyContinue
}

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $VenvPy) {
    & $VenvPy -c "from core.runtime_paths import install_venv_pycache_hook; install_venv_pycache_hook()" | Out-Null
    & $VenvPy -m pytest $Root @args
    exit $LASTEXITCODE
}

python -m pytest $Root @args
