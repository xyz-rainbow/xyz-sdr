# xyz-sdr — diagnóstico SDRplay / Soapy (Fase 0)
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Host "[XX] .venv no encontrado. Ejecuta .\install-drivers.bat" -ForegroundColor Red
    exit 1
}

function Wait-SDRplayServiceRunning {
    param([int]$TimeoutSec = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $svc = Get-Service -Name SDRplayAPIService -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -eq "Running") {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

$svc = Get-Service -Name SDRplayAPIService -ErrorAction SilentlyContinue
if ($svc) {
    if ($svc.Status -ne "Running") {
        Write-Host "[!!] SDRplayAPIService detenido — intentando iniciar..." -ForegroundColor Yellow
        try {
            Start-Service -Name SDRplayAPIService -ErrorAction Stop
        } catch {
            Write-Host "[XX] No se pudo iniciar el servicio (¿PowerShell como administrador?)." -ForegroundColor Red
            Write-Host "     Start-Service SDRplayAPIService" -ForegroundColor Yellow
        }
    }
    if (-not (Wait-SDRplayServiceRunning -TimeoutSec 30)) {
        Write-Host "[XX] SDRplayAPIService no reporta Running tras 30s — el stream test fallará." -ForegroundColor Red
        Write-Host "     Restart-Service SDRplayAPIService; espera 10s y reintenta." -ForegroundColor Yellow
    } else {
        Start-Sleep -Seconds 2
    }
}

$pyArgs = @("-m", "core.diagnose_sdrplay")
if ($args -contains "--no-stream") {
    $pyArgs += "--no-stream"
}
if ($args -contains "--no-probe") {
    $pyArgs += "--no-probe"
}

& "$VenvPy" @pyArgs
exit $LASTEXITCODE
