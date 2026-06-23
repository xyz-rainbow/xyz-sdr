# ============================================================
# xyz-sdr | install_drivers.ps1
# Instala SDRplay API, PothosSDR (SoapySDR) y dependencias Python
# ============================================================

param(
    [switch]$SkipDrivers,
    [switch]$SkipPython
)

$ErrorActionPreference = "Stop"

# --- Colores y helpers ---
function Write-Step   { param($msg) Write-Host "`n[>>] $msg" -ForegroundColor Cyan }
function Write-Ok     { param($msg) Write-Host " [OK] $msg" -ForegroundColor Green }
function Write-Warn   { param($msg) Write-Host " [!!] $msg" -ForegroundColor Yellow }
function Write-Err    { param($msg) Write-Host " [XX] $msg" -ForegroundColor Red }

Write-Host @"
  ___  ___  ___     ___  ___  ____
 |   \/   ||   |   / __|/ _ \|  _ \
  \  /\  / |   |__\__ \ (_) | |_) |
   \/  \/  |_____||___/\___/|____/

  Terminal SDR Controller — Setup
  ================================
"@ -ForegroundColor Magenta

# --- Verificar winget / chocolatey ---
Write-Step "Verificando gestores de paquetes..."

$hasWinget = Get-Command winget -ErrorAction SilentlyContinue
$hasChoco  = Get-Command choco  -ErrorAction SilentlyContinue

if ($hasWinget) {
    Write-Ok "winget disponible"
} elseif ($hasChoco) {
    Write-Ok "chocolatey disponible"
} else {
    Write-Warn "winget y chocolatey no encontrados. Descarga manual requerida."
}

# --- 1. SDRplay API ---
if (-not $SkipDrivers) {
    Write-Step "Instalando SDRplay API v3.x..."

    $sdrplayApiUrl = "https://www.sdrplay.com/software/SDRplay_RSP_API-Windows-3.15.1.exe"
    $sdrplayInstaller = "$env:TEMP\SDRplay_API_installer.exe"

    Write-Host "  Descargando SDRplay API desde sdrplay.com..." -ForegroundColor Gray

    try {
        Invoke-WebRequest -Uri $sdrplayApiUrl -OutFile $sdrplayInstaller -UseBasicParsing
        Write-Ok "Descarga completada: $sdrplayInstaller"

        Write-Warn "Instalando SDRplay API (se abrira el instalador grafico)..."
        Start-Process -FilePath $sdrplayInstaller -Wait
        Write-Ok "SDRplay API instalada"
    } catch {
        Write-Warn "No se pudo descargar automaticamente."
        Write-Host "  Descarga manual: https://www.sdrplay.com/softwarehome/" -ForegroundColor Yellow
        Write-Host "  Instala 'SDRplay API' antes de continuar." -ForegroundColor Yellow
        Read-Host "  Presiona Enter cuando hayas instalado manualmente la API"
    }

    # --- 2. PothosSDR (incluye SoapySDR + drivers) ---
    Write-Step "Instalando PothosSDR (SoapySDR para Windows)..."

    $pothosUrl  = "https://github.com/pothosware/PothosSDR/releases/latest/download/PothosSDR-2023.01.0-vc16-x64.exe"
    $pothosFile = "$env:TEMP\PothosSDR_installer.exe"

    try {
        Invoke-WebRequest -Uri $pothosUrl -OutFile $pothosFile -UseBasicParsing
        Write-Ok "Descarga completada: $pothosFile"
        Write-Warn "Instalando PothosSDR (acepta las opciones por defecto)..."
        Start-Process -FilePath $pothosFile -Wait
        Write-Ok "PothosSDR instalado"
    } catch {
        Write-Warn "Descarga automatica fallida."
        Write-Host "  Descarga manual: https://github.com/pothosware/PothosSDR/releases" -ForegroundColor Yellow
        Read-Host "  Presiona Enter cuando hayas instalado manualmente PothosSDR"
    }

    # --- 3. Añadir SoapySDR al PATH ---
    Write-Step "Configurando PATH para SoapySDR..."

    $soapyPaths = @(
        "C:\Program Files\PothosSDR\bin",
        "C:\Program Files\SoapySDR\bin"
    )

    $currentPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")

    foreach ($p in $soapyPaths) {
        if (Test-Path $p) {
            if ($currentPath -notlike "*$p*") {
                [System.Environment]::SetEnvironmentVariable("PATH", "$currentPath;$p", "User")
                Write-Ok "Añadido al PATH: $p"
            } else {
                Write-Ok "Ya en PATH: $p"
            }
        }
    }
}

# --- 4. Dependencias Python ---
if (-not $SkipPython) {
    Write-Step "Instalando dependencias Python..."

    $reqFile = Join-Path $PSScriptRoot "..\requirements.txt"

    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Err "Python no encontrado. Instala Python 3.10+ desde https://python.org"
        exit 1
    }

    $pyVersion = python --version 2>&1
    Write-Ok "Python encontrado: $pyVersion"

    # Instalar uv si no está disponible (más rápido que pip)
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Step "Instalando uv (gestor de paquetes rapido)..."
        pip install uv --quiet
    }

    Write-Step "Instalando paquetes con uv..."
    uv pip install -r $reqFile --system

    Write-Ok "Dependencias Python instaladas"
}

# --- 5. Verificacion final ---
Write-Step "Verificando instalacion..."

python "$PSScriptRoot\..\setup\check_env.py"

Write-Host "`n============================================" -ForegroundColor Green
Write-Host "  Setup completado! Ejecuta:" -ForegroundColor Green
Write-Host "  python main.py" -ForegroundColor White
Write-Host "============================================`n" -ForegroundColor Green
