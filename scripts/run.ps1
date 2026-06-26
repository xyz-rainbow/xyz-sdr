# xyz-sdr — ejecutar la aplicación (requiere .venv)
# PositionalBinding=false evita que "sdrplay" se asigne a -Band cuando se usa --driver.
[CmdletBinding(PositionalBinding = $false)]
param(
    [Alias("s")]
    [switch]$Sim,

    [Alias("d")]
    [switch]$DebugMode,

    [switch]$Check,
    [switch]$ListDev,
    [switch]$NoSplash,
    [switch]$NoAutoRx,

    [string]$Driver,

    [ValidateSet("fm_broadcast", "airband", "pmr446", "hf_lsb")]
    [string]$Band,

    [string]$Config = "config/defaults.toml",
    [double]$Freq,
    [double]$Gain,
    [ValidateSet("wbfm", "nbfm", "am", "usb", "lsb", "cw", "dsb", "raw", "auto")]
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
# Evita secuencias SGR de ratón mezcladas con la TUI en Windows Terminal / PS.
if (-not $env:XYZ_SDR_MOUSE) {
    $env:XYZ_SDR_NO_MOUSE = "1"
}
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
    Write-Host "  .\scripts\run.ps1                         # lanzar TUI"
    Write-Host "  .\scripts\run.ps1 -Sim                    # simulación sin hardware"
    Write-Host "  .\scripts\run.ps1 -DebugMode              # métricas RX/UI en panel log (-d)"
    Write-Host "  .\scripts\run.ps1 -Driver sdrplay         # o --driver sdrplay o --driver=sdrplay"
    Write-Host "  .\scripts\run.ps1 -Band fm_broadcast      # perfil FM 88–108 MHz"
    Write-Host "  .\scripts\run.ps1 -Check                  # verificar entorno"
    Write-Host "  .\scripts\run.ps1 -ListDev                # listar dispositivos Soapy"
    Write-Host "  .\scripts\run.ps1 -Freq 97.7 -Mode wbfm"
    Write-Host ""
    Write-Host "Perfiles: fm_broadcast, airband, pmr446, hf_lsb (config/bands/)"
    Write-Host "Instalador: .\setup\install_app.ps1         # acceso directo escritorio"
    Write-Host ""
}

if ($ExtraArgs -contains "-?" -or $ExtraArgs -contains "--help" -or $ExtraArgs -contains "-h") {
    Show-RunHelp
    exit 0
}

function Expand-EqualsCliArgs {
    param([string[]]$Tokens)
    if (-not $Tokens) {
        return @()
    }
    $out = [System.Collections.Generic.List[string]]::new()
    foreach ($token in $Tokens) {
        if ($token -match '^(--driver|--band|--config|--freq|--gain|--mode)=(.+)$') {
            $out.Add($Matches[1])
            $out.Add($Matches[2])
        } else {
            $out.Add($token)
        }
    }
    return $out.ToArray()
}

$ExtraArgs = Expand-EqualsCliArgs $ExtraArgs

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
if ($DebugMode) { $pyArgs += "--debug" }
if ($Check) { $pyArgs += "--check" }
if ($ListDev) { $pyArgs += "--list-dev" }
if ($NoSplash) { $pyArgs += "--no-splash" }
if ($NoAutoRx) { $pyArgs += "--no-auto-rx" }
if ($Band) { $pyArgs += @("--band", $Band) }
if ($Driver) { $pyArgs += @("--driver", $Driver) }
if ($PSBoundParameters.ContainsKey("Freq")) { $pyArgs += @("--freq", $Freq) }
if ($PSBoundParameters.ContainsKey("Gain")) { $pyArgs += @("--gain", $Gain) }
if ($Mode) { $pyArgs += @("--mode", $Mode) }
if ($ExtraArgs) { $pyArgs += $ExtraArgs }

function Restore-XyzSdrConsole {
    # Apaga modo ratón SGR / pantalla alterna aunque Python haya crasheado (segfault Soapy).
    $esc = [char]27
    $seq = "${esc}[<u${esc}[?1049l${esc}[?25h${esc}[?1004l${esc}[?2004l${esc}[?1000l${esc}[?1003l${esc}[?1015l${esc}[?1002l${esc}[?1006l${esc}[?1007l${esc}[0m"
    try {
        [Console]::Write($seq)
    } catch {
        Write-Host -NoNewline $seq
    }
    try {
        Clear-Host
    } catch {
        Write-Host -NoNewline "${esc}[2J${esc}[H"
    }
}

function Show-CrashReport {
    param([int]$ExitCode)

    $markerPath = Join-Path $Root "var\log\.last-session.json"
    $marker = $null
    $kind = ""
    $logPath = ""
    $detail = ""

    if (Test-Path -LiteralPath $markerPath) {
        try {
            $marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
            $kind = [string]$marker.kind
            $logPath = [string]$marker.log_path
            $detail = [string]$marker.detail
        } catch {
            $kind = ""
        }
    }

    $gracefulKinds = @("graceful", "keyboard_interrupt", "check", "list_dev", "diagnose")
    if ($gracefulKinds -contains $kind) {
        return
    }

    if ($ExitCode -eq 0 -and -not $kind) {
        return
    }

    $reason = ""
    if ($detail) {
        $reason = $detail
    } elseif ($ExitCode -eq 3221225477 -or $ExitCode -eq -1073741819) {
        $reason = "Native crash suspected (access violation 0xC0000005)"
    } elseif ($kind -eq "abnormal") {
        $reason = "Process exited without clean shutdown (possible native crash)"
    } elseif ($kind -eq "native_crash") {
        $reason = "Native crash (SDRplay/Soapy segfault)"
    } elseif ($ExitCode -ne 0) {
        $reason = "Process exited with code $ExitCode"
    } else {
        $reason = "Unexpected session termination"
    }

    if (-not $logPath) {
        $logDir = Join-Path $Root "var\log"
        if (Test-Path -LiteralPath $logDir) {
            $latest = Get-ChildItem -LiteralPath $logDir -Filter "xyz-sdr-*.log" -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending |
                Select-Object -First 1
            if ($latest) {
                $logPath = $latest.FullName
            }
        }
    }

    $nativeCrash = ($ExitCode -eq 3221225477 -or $ExitCode -eq -1073741819 -or $ExitCode -eq 3221225725 -or $ExitCode -eq -1073741571)
    if ($nativeCrash -or ($ExitCode -ne 0 -and $gracefulKinds -notcontains $kind)) {
        $crashKind = if ($nativeCrash) { "native_crash" } elseif ($kind) { $kind } else { "abnormal" }
        try {
            $payload = @{
                kind      = $crashKind
                timestamp = (Get-Date).ToUniversalTime().ToString("o")
                log_path  = $logPath
                detail    = $reason
                exit_code = $ExitCode
            }
            $payload | ConvertTo-Json | Set-Content -LiteralPath $markerPath -Encoding UTF8
        } catch {
            # marker para reinicio SDRplayAPIService en la siguiente sesión
        }
    }

    $crashArgs = @("-m", "core.crash_ui", "--exit-code", $ExitCode, "--reason", $reason)
    if ($logPath) {
        $crashArgs += @("--log", $logPath)
    }
    if ($NoSplash) {
        $crashArgs += "--no-splash"
    }

    try {
        & "$VenvPy" @crashArgs
    } catch {
        Write-Host ""
        Write-Host "[ERROR] xyz-sdr terminó de forma inesperada: $reason" -ForegroundColor Red
        if ($logPath -and (Test-Path -LiteralPath $logPath)) {
            Write-Host "Log: $logPath" -ForegroundColor Yellow
            Get-Content -LiteralPath $logPath -Tail 25
        }
    }
}

try {
    & "$VenvPy" @pyArgs
    $exitCode = $LASTEXITCODE
} finally {
    Restore-XyzSdrConsole
    Show-CrashReport -ExitCode $exitCode
}
exit $exitCode
