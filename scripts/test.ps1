# xyz-sdr — ejecutar tests (pytest.ini en resources/test)
$Root = Split-Path -Parent $PSScriptRoot
$Pycache = Join-Path $Root "var\pycache"
New-Item -ItemType Directory -Force -Path $Pycache | Out-Null
$env:PYTHONPYCACHEPREFIX = $Pycache
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
$Tests = Join-Path $Root "resources\test"

if (Test-Path -LiteralPath $VenvPy) {
    & $VenvPy -m pytest $Tests @args
    exit $LASTEXITCODE
}

python -m pytest $Tests @args
