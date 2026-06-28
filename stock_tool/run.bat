@echo off
:: StockTool launcher
:: Double-click this file, or run it from any terminal.

cd /d "%~dp0"

:: Check Python is available
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found on PATH.
    echo Please install Python 3.12+ and try again.
    pause
    exit /b 1
)

:: Install / verify dependencies (silent if already satisfied)
echo Checking dependencies...
python -m pip install -r requirements.txt -q --disable-pip-version-check

:: Launch the app
echo Starting StockTool...
python main.py %*

:: If the app exits with an error code, keep the window open so you can read it
if errorlevel 1 (
    echo.
    echo StockTool exited with an error (code %errorlevel%).
    pause
)
