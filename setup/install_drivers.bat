@echo off
rem ============================================================
rem xyz-sdr | install_drivers.bat
rem Wrapper Batch para lanzar el instalador interactivo de Python
rem ============================================================

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [XX] Error: Python 3.10+ no encontrado.
    echo Por favor, descarga e instala Python desde https://python.org y asegúrate de marcar 'Add Python to PATH'.
    echo.
    pause
    exit /b 1
)

python "%~dp0install_drivers.py"
