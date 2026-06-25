@echo off
rem xyz-sdr — lanzar la aplicación (doble clic desde la raíz del repo)
setlocal EnableExtensions
cd /d "%~dp0"

echo xyz-sdr: iniciando...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run.ps1" %*
exit /b %ERRORLEVEL%
