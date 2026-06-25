@echo off
rem xyz-sdr — instalar SDRplay API v3.15 (offline / Downloads / URL)
setlocal EnableExtensions

set "ROOT=%~dp0.."
if not exist "%ROOT%\var\pycache" mkdir "%ROOT%\var\pycache"
set "PYTHONPYCACHEPREFIX=%ROOT%\var\pycache"
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"

echo.
echo xyz-sdr: instalador SDRplay API v3.15...
echo (Puede aparecer UAC / ventana del instalador oficial)
echo.

if exist "%VENV_PY%" (
    "%VENV_PY%" "%~dp0install_sdrplay_api.py" %*
    set "RC=%ERRORLEVEL%"
    goto :done
)

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [XX] Python no encontrado. Ejecuta: .\setup\install_drivers.ps1
    echo.
    pause
    exit /b 1
)

python "%~dp0install_sdrplay_api.py" %*
set "RC=%ERRORLEVEL%"

:done
if not "%RC%"=="0" (
    echo.
    echo [ERROR] Codigo de salida: %RC%
    pause
)
exit /b %RC%
