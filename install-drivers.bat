@echo off
rem xyz-sdr — instalación de drivers y entorno (doble clic desde la raíz del repo)
setlocal EnableExtensions
cd /d "%~dp0"

echo xyz-sdr: configurando drivers y entorno...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\install_drivers.ps1" %*
exit /b %ERRORLEVEL%
