@echo off
REM xyz-sdr — launcher doble clic (delega en run.ps1)
setlocal
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run.ps1" %*
