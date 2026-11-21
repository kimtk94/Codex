@echo off
setlocal
cd /d "%~dp0.."
echo [Local AI] Installing/checking Node.js, npm, Codex CLI and qwen2.5-coder:3b...
powershell.exe -NoProfile -File "%~dp0local-codex.ps1" -Mode Setup -Model qwen3:4b
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [Local AI] Setup failed. Read the message above and try again.
if "%RC%"=="0" echo [Local AI] Setup complete. Next time use Start-Local-Codex.cmd.
pause
exit /b %RC%
