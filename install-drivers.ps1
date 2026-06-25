# xyz-sdr — instalación de drivers y entorno (delega en setup/install_drivers.ps1)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Script = Join-Path $Root "setup\install_drivers.ps1"
Set-Location -LiteralPath $Root
& powershell -NoProfile -ExecutionPolicy Bypass -File "$Script" @args
exit $LASTEXITCODE
