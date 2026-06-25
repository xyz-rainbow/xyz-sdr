# xyz-sdr — lanzar la aplicación (delega en scripts/run.ps1)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Script = Join-Path $Root "scripts\run.ps1"
Set-Location -LiteralPath $Root
& powershell -NoProfile -ExecutionPolicy Bypass -File "$Script" @args
exit $LASTEXITCODE
