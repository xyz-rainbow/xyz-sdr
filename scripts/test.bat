@echo off
rem xyz-sdr — ejecutar tests (config pytest en pyproject.toml)
rem Requiere .venv\. Scripts\python.exe. Si no existe, abortar con mensaje claro.
setlocal EnableDelayedExpansion
set "ROOT=%~dp0.."
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [ERROR] .venv no encontrado en %ROOT%\.venv
    echo Crea el entorno con:
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
    echo O usa .\setup\install_drivers.ps1 (menu Express: [1] Instalar o reparar todo).
    exit /b 1
)

rem Bootstrap project caches + cleanup stray __pycache__ (consistent with test.sh)
"%VENV_PY%" -c "import sys, shutil; from pathlib import Path; ROOT=Path(r'%ROOT%'); sys.path.insert(0, str(ROOT)); from core.runtime_paths import bootstrap_project_caches, install_venv_pycache_hook, remove_stray_project_caches; bootstrap_project_caches(ROOT); remove_stray_project_caches(ROOT); install_venv_pycache_hook(ROOT)"

"%VENV_PY%" -m pytest "%ROOT%" %*
exit /b %errorlevel%