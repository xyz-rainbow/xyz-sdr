# xyz-sdr — soak bandwidth (crash temporal espectro/cascada)
param(
    [switch]$Hardware,
    [double]$DurationMin = 10,
    [double]$CyclePauseSec = 2,
    [switch]$NoSidebar,
    [switch]$RunnerOnly,
    [string]$Export = ""
)

$Root = Split-Path -Parent $PSScriptRoot
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Host "[XX] Entorno .venv no encontrado." -ForegroundColor Red
    exit 1
}

Set-Location -LiteralPath $Root
$env:PYTHONUTF8 = "1"

$durationSec = [math]::Max(30, $DurationMin * 60)

$useRunner = $RunnerOnly -or ($Export -ne "")

if (-not $useRunner) {
    $pytestArgs = @(
        "-m", "pytest",
        "resources/test/test_bandwidth_display_soak.py::test_bw_cycle_sim_no_exceptions",
        "-v"
    )
    if ($Hardware) {
        $pytestArgs = @(
            "-m", "pytest",
            "resources/test/test_bandwidth_display_soak.py::test_bw_soak_sdrplay",
            "-m", "integration",
            "-v"
        )
    }
    & $VenvPy @pytestArgs
    exit $LASTEXITCODE
}

$runnerArgs = @("-m", "resources.test.bw_soak_runner", "--duration", "$durationSec", "--cycle-pause", "$CyclePauseSec")
if ($Hardware) { $runnerArgs += "--hardware" } else { $runnerArgs += "--sim" }
if ($NoSidebar) { $runnerArgs += "--no-sidebar" }
if ($Export -ne "") { $runnerArgs += @("--export", $Export) }

& $VenvPy @runnerArgs
exit $LASTEXITCODE
