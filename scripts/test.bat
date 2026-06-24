@echo off
rem xyz-sdr — ejecutar tests (pytest.ini en raíz del repo)
set "ROOT=%~dp0.."
if not exist "%ROOT%\var\pycache" mkdir "%ROOT%\var\pycache"
if not exist "%ROOT%\var\pytest_cache" mkdir "%ROOT%\var\pytest_cache"
if not exist "%ROOT%\var\pytest-tmp" mkdir "%ROOT%\var\pytest-tmp"
set "PYTHONPYCACHEPREFIX=%ROOT%\var\pycache"
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"

if exist "%ROOT%\.pytest_cache" rmdir /s /q "%ROOT%\.pytest_cache"
if exist "%ROOT%\__pycache__" rmdir /s /q "%ROOT%\__pycache__"

if exist "%VENV_PY%" (
    "%VENV_PY%" -c "from core.runtime_paths import install_venv_pycache_hook; install_venv_pycache_hook()"
    "%VENV_PY%" -m pytest "%ROOT%" %*
    exit /b %errorlevel%
)

python -m pytest "%ROOT%" %*
