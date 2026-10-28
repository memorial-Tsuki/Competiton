@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "PYTHON_EXE=%UserProfile%\miniconda3\python.exe"
set "APP_FILE="

for /r "%ROOT%" %%F in (app.py) do if not defined APP_FILE set "APP_FILE=%%F"

if not defined APP_FILE (
  echo ERROR: app.py was not found. Extract the complete repository first.
  pause
  exit /b 1
)
if not exist "%PYTHON_EXE%" (
  echo ERROR: Miniconda Python was not found at:
  echo %PYTHON_EXE%
  echo Install Miniconda or run the command shown in README.md.
  pause
  exit /b 1
)

for %%F in ("%APP_FILE%") do cd /d "%%~dpF"
echo Starting local credit scoring web page. Keep this window open.
echo If the browser does not open, copy the http://127.0.0.1 address shown below.
"%PYTHON_EXE%" app.py
pause
