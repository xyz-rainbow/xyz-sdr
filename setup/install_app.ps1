# xyz-sdr — instalador de acceso directo Windows (escritorio / menú inicio)
[CmdletBinding()]
param(
    [switch]$Desktop,
    [switch]$StartMenu,
    [switch]$SimShortcut,
    [switch]$Uninstall,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$RunPs1 = Join-Path $Root "scripts\run.ps1"
$RunCmd = Join-Path $Root "scripts\xyz-sdr.cmd"

function Write-Info([string]$Message) {
    if (-not $Quiet) {
        Write-Host $Message
    }
}

function Get-ShortcutPaths {
    param([switch]$IncludeSim)
    $paths = @()
    if ($Desktop) {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $paths += Join-Path $desktop "xyz-sdr.lnk"
        if ($IncludeSim) {
            $paths += Join-Path $desktop "xyz-sdr (sim).lnk"
        }
    }
    if ($StartMenu) {
        $start = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\xyz-sdr"
        New-Item -ItemType Directory -Force -Path $start | Out-Null
        $paths += Join-Path $start "xyz-sdr.lnk"
        if ($IncludeSim) {
            $paths += Join-Path $start "xyz-sdr (sim).lnk"
        }
    }
    return $paths
}

function New-XyzShortcut {
    param(
        [string]$Path,
        [string]$Arguments,
        [string]$Description
    )
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$RunPs1`" $Arguments"
    $shortcut.WorkingDirectory = $Root
    $shortcut.Description = $Description
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll, 13"
    $shortcut.Save()
}

function Remove-Shortcut([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Force
        Write-Info "Eliminado: $Path"
    }
}

if (-not (Test-Path -LiteralPath $RunPs1)) {
    Write-Host "[XX] No se encontró scripts\run.ps1 en $Root" -ForegroundColor Red
    exit 1
}

if (-not ($Desktop -or $StartMenu -or $Uninstall)) {
    $Desktop = $true
}

if ($Uninstall) {
    foreach ($path in (Get-ShortcutPaths -IncludeSim)) {
        Remove-Shortcut $path
    }
    $startFolder = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\xyz-sdr"
    if (Test-Path -LiteralPath $startFolder) {
        Remove-Item -LiteralPath $startFolder -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Info "Accesos directos xyz-sdr eliminados."
    exit 0
}

if (-not (Test-Path -LiteralPath (Join-Path $Root ".venv\Scripts\python.exe"))) {
    Write-Host "[!!] .venv no encontrado. Ejecuta primero .\setup\install_drivers.ps1" -ForegroundColor Yellow
}

if ($Desktop) {
    $desktopPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "xyz-sdr.lnk"
    New-XyzShortcut -Path $desktopPath -Arguments "" -Description "xyz-sdr — receptor SDR en terminal"
    Write-Info "Creado: $desktopPath"
    if ($SimShortcut) {
        $simPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "xyz-sdr (sim).lnk"
        New-XyzShortcut -Path $simPath -Arguments "-Sim" -Description "xyz-sdr — modo simulación"
        Write-Info "Creado: $simPath"
    }
}

if ($StartMenu) {
    $start = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\xyz-sdr"
    New-Item -ItemType Directory -Force -Path $start | Out-Null
    $menuPath = Join-Path $start "xyz-sdr.lnk"
    New-XyzShortcut -Path $menuPath -Arguments "" -Description "xyz-sdr — receptor SDR en terminal"
    Write-Info "Creado: $menuPath"
    if ($SimShortcut) {
        $simMenu = Join-Path $start "xyz-sdr (sim).lnk"
        New-XyzShortcut -Path $simMenu -Arguments "-Sim" -Description "xyz-sdr — modo simulación"
        Write-Info "Creado: $simMenu"
    }
}

Write-Info ""
Write-Info "También puedes usar: $RunCmd"
Write-Info "Perfiles de banda: .\scripts\run.ps1 -Band fm_broadcast"
