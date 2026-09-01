@echo off
REM Stock Selection - daily refresh (weekday evening, HK + prior US close settled).
REM Registered in Task Scheduler as "StockSelect Daily Refresh".
REM
REM Regenerates reports\index.html from live data. Because the 7-day fundamentals
REM cache only stamps names that actually resolved, each daily run also grabs the
REM next batch of profiles that Yahoo throttled the day before, so coverage
REM converges over successive days without any babysitting.
REM
REM The Cloudflare deploy runs only once wrangler is installed and configured
REM (Milestone B); until then it is skipped cleanly and the page is refreshed
REM locally only.
cd /d "%~dp0"
set "PY=C:\Users\robot\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%~dp0reports" mkdir "%~dp0reports"

echo [%DATE% %TIME%] refresh start >> "%~dp0reports\cron.log"
"%PY%" main.py --out reports\index.html >> "%~dp0reports\cron.log" 2>&1

where wrangler >nul 2>&1
if %ERRORLEVEL%==0 (
    echo [%DATE% %TIME%] wrangler deploy >> "%~dp0reports\cron.log"
    call wrangler deploy >> "%~dp0reports\cron.log" 2>&1
) else (
    echo [%DATE% %TIME%] wrangler not installed - skipping deploy >> "%~dp0reports\cron.log"
)
echo [%DATE% %TIME%] refresh done >> "%~dp0reports\cron.log"
