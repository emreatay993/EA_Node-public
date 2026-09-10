@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo [1/4] Selecting Python...
set "PYEXE="
for %%V in (3.12 3.11 3.10) do (
  if not defined PYEXE (
    py -%%V -c "import sys" >nul 2>&1 && set "PYEXE=py -%%V"
  )
)
if not defined PYEXE (
  py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
)
if not defined PYEXE (
  echo Python 3.10 or newer was not found.
  echo Install 64-bit Python, then run this file again.
  pause
  exit /b 1
)

%PYEXE% -c "import sys; print('Using', sys.executable, sys.version)"
if errorlevel 1 exit /b 1

echo [2/4] Creating virtual environment...
%PYEXE% -m venv .venv
if errorlevel 1 exit /b 1

call .venv\Scripts\activate.bat

echo [3/4] Installing dependencies and application...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 exit /b 1
python -m pip install -e ".[dev]"
if errorlevel 1 exit /b 1

echo [4/4] Running numerical self-test...
python -m pytest -q
if errorlevel 1 (
  echo Installation completed, but the self-test failed.
  pause
  exit /b 1
)

echo.
echo Installation and self-test completed successfully.
echo Start the application with run_gui.bat.
pause
