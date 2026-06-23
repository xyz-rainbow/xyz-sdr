@echo off
rem ============================================================
rem xyz-sdr | install_drivers.bat
rem Wrapper Batch — prefiere .venv del proyecto si existe
rem ============================================================

set "ROOT=%~dp0.."
if not exist "%ROOT%\var\pycache" mkdir "%ROOT%\var\pycache"
set "PYTHONPYCACHEPREFIX=%ROOT%\var\pycache"
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"

if exist "%VENV_PY%" (
    "%VENV_PY%" "%~dp0install_drivers.py" %*
    exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [XX] Error: Python 3.10+ no encontrado.
    echo Instala Python 3.12 o ejecuta: winget install Python.Python.3.12
    echo.
    pause
    exit /b 1
)

python "%~dp0install_drivers.py" %*
