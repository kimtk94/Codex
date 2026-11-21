@echo off
setlocal
cd /d "%~dp0.."
echo [Local AI] Check GPU / memory / actual Ollama model speed with synthetic data only.
powershell.exe -NoProfile -File "%~dp0diagnose-local-ollama-speed.ps1" -Model qwen3-codex16k:latest -TimeoutSeconds 120
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [Local AI] Diagnostics did not complete. Check the error above.
pause
exit /b %RC%
