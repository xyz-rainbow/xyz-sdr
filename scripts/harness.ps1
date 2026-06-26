# xyz-sdr — harness de diagnóstico espectro/waterfall
[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Driver,
    [double]$FreqHz,
    [double]$Gain,
    [double]$SampleRate,
    [string]$Config = "config/defaults.toml",
    [string]$ExportDir,
    [switch]$Headless,
    [double]$Duration = 8,
    [int]$MinFrames = 5,
    [switch]$Preflight,
    [int]$Width = 100,
    [int]$Height = 32,
    [switch]$Sim,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

$Pycache = Join-Path $Root "var\pycache"
New-Item -ItemType Directory -Force -Path $Pycache | Out-Null
$env:PYTHONPYCACHEPREFIX = $Pycache
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
$Main = Join-Path $Root "main.py"
if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Error "No se encontró .venv. Ejecuta setup/install_app.ps1 o crea el venv."
    exit 1
}

$pyArgs = @($Main)

if ($Sim) { $pyArgs += @("--driver", "simulated") }
elseif ($Driver) { $pyArgs += @("--driver", $Driver) }
if ($PSBoundParameters.ContainsKey("FreqHz")) { $pyArgs += @("--freq", ($FreqHz / 1e6)) }
if ($PSBoundParameters.ContainsKey("Gain")) { $pyArgs += @("--gain", $Gain) }
if ($PSBoundParameters.ContainsKey("SampleRate")) { $pyArgs += @("--sample-rate", $SampleRate) }
if ($ExportDir) { $pyArgs += @("--display-export-dir", $ExportDir) }
if ($Headless) { $pyArgs += "--headless-display" }
if ($PSBoundParameters.ContainsKey("Duration")) { $pyArgs += @("--display-duration", $Duration) }
if ($PSBoundParameters.ContainsKey("MinFrames")) { $pyArgs += @("--display-min-frames", $MinFrames) }
if ($Preflight) { $pyArgs += "--display-preflight" }
if ($Config -and $Config -ne "config/defaults.toml") { $pyArgs += @("--config", $Config) }
$pyArgs += "--harness"
if ($ExtraArgs) { $pyArgs += $ExtraArgs }

& $VenvPy @pyArgs
exit $LASTEXITCODE
