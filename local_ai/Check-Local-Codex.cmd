@echo off
setlocal
cd /d "%~dp0.."
powershell.exe -NoProfile -File "%~dp0local-codex.ps1" -Mode Diagnose -Model qwen3:4b
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
