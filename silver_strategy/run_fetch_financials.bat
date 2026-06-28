@echo off
REM Silver Miners — fetch latest quarterly financials + refresh narrative (last day of month).
REM Registered in Task Scheduler. Narrative step is best-effort: if no Anthropic key is set,
REM fetch still succeeds and the report falls back to the curated baseline narrative.
cd /d "%~dp0"
set PY="C:\Users\robot\AppData\Local\Programs\Python\Python312\python.exe"
%PY% fetch_financials.py >> "%~dp0reports\cron.log" 2>&1
%PY% llm_narrative.py >> "%~dp0reports\cron.log" 2>&1
