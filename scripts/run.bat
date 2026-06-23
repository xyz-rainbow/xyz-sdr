@echo off
rem xyz-sdr — ejecutar la aplicación (requiere .venv)
set "ROOT=%~dp0.."
if not exist "%ROOT%\var\pycache" mkdir "%ROOT%\var\pycache"
set "PYTHONPYCACHEPREFIX=%ROOT%\var\pycache"
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo.
    echo [XX] Entorno .venv no encontrado.
    echo     1. .\setup\install_drivers.ps1  ^(opcion [1] Reparar^)
    echo     2. .\scripts\run.bat
    echo.
    exit /b 1
)

"%VENV_PY%" "%ROOT%\main.py" %*
