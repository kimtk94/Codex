@echo off
setlocal
cd /d "%~dp0.."
echo [Local AI] Create and verify qwen3-codex16k (local model, 16K context).
powershell.exe -NoProfile -File "%~dp0create-codex16k.ps1" -BaseModel qwen3:4b -Model qwen3-codex16k -ContextTokens 16384
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" echo [Local AI] PASS: now use Start-Local-Codex.cmd.
if not "%RC%"=="0" echo [Local AI] FAIL: model was not verified. Read errors and check Ollama settings.
pause
exit /b %RC%
