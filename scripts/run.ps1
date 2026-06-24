# xyz-sdr — ejecutar la aplicación (requiere .venv)
[CmdletBinding()]
param(
    [Alias("s")]
    [switch]$Sim,

    [Alias("d")]
    [switch]$Debug,

    [switch]$Check,
    [switch]$ListDev,
    [switch]$NoSplash,

    [ValidateSet("fm_broadcast", "airband", "pmr446", "hf_lsb")]
    [string]$Band,

    [string]$Config = "config/defaults.toml",
    [string]$Driver,
    [double]$Freq,
    [double]$Gain,
    [ValidateSet("wbfm", "nbfm", "am", "usb", "lsb")]
    [string]$Mode,

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
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
    chcp 65001 | Out-Null
} catch {
    # Consola sin soporte UTF-8; splash usará fallback ASCII
}

function Show-RunHelp {
    Write-Host ""
    Write-Host "xyz-sdr — atajos de scripts\run.ps1" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  .\scripts\run.ps1                    # lanzar TUI"
    Write-Host "  .\scripts\run.ps1 -Sim               # simulación sin hardware"
    Write-Host "  .\scripts\run.ps1 -Debug             # métricas RX/UI en panel log"
    Write-Host "  .\scripts\run.ps1 -Band fm_broadcast # perfil FM 88–108 MHz"
    Write-Host "  .\scripts\run.ps1 -Band airband      # aviación VHF"
    Write-Host "  .\scripts\run.ps1 -Check             # verificar entorno"
    Write-Host "  .\scripts\run.ps1 -ListDev           # listar dispositivos Soapy"
    Write-Host "  .\scripts\run.ps1 -Freq 97.7 -Mode wbfm"
    Write-Host ""
    Write-Host "Perfiles: fm_broadcast, airband, pmr446, hf_lsb (config/bands/)"
    Write-Host "Instalador: .\setup\install_app.ps1    # acceso directo escritorio"
    Write-Host ""
}

if ($ExtraArgs -contains "-?" -or $ExtraArgs -contains "--help" -or $ExtraArgs -contains "-h") {
    Show-RunHelp
    exit 0
}

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
$Main = Join-Path $Root "main.py"

if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Host "`n[XX] Entorno .venv no encontrado." -ForegroundColor Red
    Write-Host "  1. .\setup\install_drivers.ps1  → [1] Instalar o reparar todo" -ForegroundColor Yellow
    Write-Host "  2. .\setup\install_app.ps1        → acceso directo (opcional)" -ForegroundColor Yellow
    Write-Host "  3. .\scripts\run.ps1" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

$pyArgs = @($Main)

if ($Config -and $Config -ne "config/defaults.toml") { $pyArgs += @("--config", $Config) }
if ($Sim) { $pyArgs += "--sim" }
if ($Debug) { $pyArgs += "--debug" }
if ($Check) { $pyArgs += "--check" }
if ($ListDev) { $pyArgs += "--list-dev" }
if ($NoSplash) { $pyArgs += "--no-splash" }
if ($Band) { $pyArgs += @("--band", $Band) }
if ($Driver) { $pyArgs += @("--driver", $Driver) }
if ($PSBoundParameters.ContainsKey("Freq")) { $pyArgs += @("--freq", $Freq) }
if ($PSBoundParameters.ContainsKey("Gain")) { $pyArgs += @("--gain", $Gain) }
if ($Mode) { $pyArgs += @("--mode", $Mode) }
if ($ExtraArgs) { $pyArgs += $ExtraArgs }

& $VenvPy @pyArgs
exit $LASTEXITCODE
