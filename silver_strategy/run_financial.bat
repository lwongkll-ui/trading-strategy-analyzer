@echo off
REM Silver Miners — monthly financial review (1st of month). Registered in Task Scheduler.
cd /d "%~dp0"
"C:\Users\robot\AppData\Local\Programs\Python\Python312\python.exe" financial_review.py >> "%~dp0reports\cron.log" 2>&1
