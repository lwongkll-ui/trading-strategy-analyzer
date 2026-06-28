@echo off
REM Silver Miners — daily Discord post (Mon-Fri). Registered in Task Scheduler.
cd /d "%~dp0"
"C:\Users\robot\AppData\Local\Programs\Python\Python312\python.exe" post_to_discord.py --mode daily --days 10 >> "%~dp0reports\cron.log" 2>&1
