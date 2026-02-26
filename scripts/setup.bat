@echo off
setlocal
cd /d "%~dp0\.."

where py >nul 2>nul
if %errorlevel%==0 (
  py -3.12 scripts\bootstrap.py && exit /b 0
  py -3.11 scripts\bootstrap.py && exit /b 0
  py -3.10 scripts\bootstrap.py && exit /b 0
)

where python >nul 2>nul
if %errorlevel%==0 (
  python scripts\bootstrap.py
  exit /b %errorlevel%
)

echo Python 3.10+ is required. Install Python and rerun scripts\setup.bat
exit /b 1
