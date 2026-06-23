@echo off
rem xyz-sdr — ejecutar tests (pytest.ini en resources/test)
set "ROOT=%~dp0.."
if not exist "%ROOT%\var\pycache" mkdir "%ROOT%\var\pycache"
set "PYTHONPYCACHEPREFIX=%ROOT%\var\pycache"
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"

if exist "%VENV_PY%" (
    "%VENV_PY%" -m pytest "%ROOT%\resources\test" %*
    exit /b %errorlevel%
)

python -m pytest "%ROOT%\resources\test" %*
