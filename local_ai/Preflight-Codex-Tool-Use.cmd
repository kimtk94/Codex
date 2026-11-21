@echo off
setlocal
cd /d "%~dp0.."
echo [Local AI] Run read-only tool-use smoke in disposable synthetic Git repo.
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0preflight-agent-tool.ps1" -Model qwen25coder3b-16k:latest
set "RC=%ERRORLEVEL%"
if "%RC%"=="2" echo [Local AI] HOLD: genuine Codex tool use not proven.
if "%RC%"=="1" echo [Local AI] ERROR: preflight did not complete.
pause
exit /b %RC%
