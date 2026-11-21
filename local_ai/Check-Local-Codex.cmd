@echo off
setlocal
cd /d "%~dp0.."
powershell.exe -NoProfile -File "%~dp0local-codex.ps1" -Mode Diagnose -Model qwen2.5-coder:3b
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
