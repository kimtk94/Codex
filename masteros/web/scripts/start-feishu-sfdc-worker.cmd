@echo off
setlocal
cd /d "%~dp0"
python sfdc_feishu_local_worker.py --write-results
if errorlevel 1 exit /b 1
endlocal
