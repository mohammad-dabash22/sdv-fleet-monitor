@echo off
REM Double-click to run the mock demo on Windows.
REM First run: creates a virtual environment in .venv and installs the packages.
REM Extra options are passed on, for example:  run_demo.bat --inject 50

cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul && set "PY=py -3"

%PY% --version >nul 2>nul
if errorlevel 1 (
    echo Python was not found. See "Install Python" in README.md.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment in .venv ...
    %PY% -m venv .venv
    if errorlevel 1 ( pause & exit /b 1 )
)

echo Installing packages (first run can take a minute) ...
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 ( pause & exit /b 1 )

".venv\Scripts\python.exe" run_demo.py %*
pause
