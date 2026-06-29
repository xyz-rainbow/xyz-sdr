# xyz-sdr — E2E FM ~98 MHz (Textual Pilot, sim o hardware)
param(
    [switch]$Hardware,
    [int]$Loop = 1,
    [string]$Export = "",
    [switch]$RunnerOnly
)

$Root = Split-Path -Parent $PSScriptRoot
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Host "[XX] Entorno .venv no encontrado." -ForegroundColor Red
    exit 1
}

Set-Location -LiteralPath $Root
$env:PYTHONUTF8 = "1"

$useRunner = $RunnerOnly -or ($Loop -gt 1) -or ($Export -ne "")

if ($useRunner) {
    $runnerArgs = @("-m", "resources.test.fm98_e2e_runner")
    if ($Hardware) {
        $runnerArgs += "--hardware"
    } else {
        $runnerArgs += "--sim"
    }
    if ($Loop -gt 1) {
        $runnerArgs += @("--loop", "$Loop")
    }
    if ($Export -ne "") {
        $runnerArgs += @("--export", $Export)
    }
    & $VenvPy @runnerArgs
    exit $LASTEXITCODE
}

if ($Hardware) {
    & $VenvPy -m pytest resources/test/test_tui_fm98_e2e.py::test_fm98_e2e_sdrplay -m integration -v
} else {
    & $VenvPy -m pytest resources/test/test_tui_fm98_e2e.py::test_fm98_e2e_sim -v
}
exit $LASTEXITCODE
