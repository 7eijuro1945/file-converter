@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-build.txt --disable-pip-version-check
".venv\Scripts\python.exe" build_exe.py
if exist "dist\Converter.exe" (
  echo.
  echo Ready: dist\Converter.exe
)
