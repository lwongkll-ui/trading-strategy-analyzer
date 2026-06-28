@echo off
REM Silver Miners — weekly Discord post (Sat). Registered in Task Scheduler.
cd /d "%~dp0"
"C:\Users\robot\AppData\Local\Programs\Python\Python312\python.exe" weekly_review.py >> "%~dp0reports\cron.log" 2>&1
