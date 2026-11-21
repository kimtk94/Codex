@echo off
setlocal
cd /d "%~dp0.."
echo [Local AI] Verify Ollama real loaded context is at least 16K with a synthetic prompt.
powershell.exe -NoProfile -File "%~dp0verify-ollama-context.ps1" -Model qwen3-codex16k -MinimumContext 16384
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [Local AI] Verification did not pass; check the messages above.
if "%RC%"=="0" echo [Local AI] Verification PASS. You can now open Start-Local-Codex.cmd.
pause
exit /b %RC%
