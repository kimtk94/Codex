@echo off
setlocal
cd /d "%~dp0.."
echo [Local AI] Compare current Qwen3 4B CPU model against Qwen2.5-Coder 3B.
echo [Local AI] This downloads roughly 1.9 GB for the candidate if missing.
echo [Local AI] No code edits, GitHub push, or Drive access will occur.
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0compare-local-coding-models.ps1" -InstallCandidate -ContextTokens 16384 -TimeoutSeconds 180
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [Local AI] Comparison incomplete or candidate failed a check.
pause
exit /b %RC%
