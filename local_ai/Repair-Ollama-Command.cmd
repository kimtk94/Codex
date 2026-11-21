@echo off
setlocal
cd /d "%~dp0.."
echo [Local AI] Locate existing Ollama CLI; if found, add to current USER PATH for future sessions.
echo [Local AI] No reinstall and no administrator permissions required.
powershell.exe -NoProfile -File "%~dp0repair-ollama-cli.ps1" -Persist
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" echo [Local AI] Done. Open a NEW PowerShell/VS Code terminal and run ollama list.
if not "%RC%"=="0" echo [Local AI] Could not locate the Ollama CLI. Check its install location.
pause
exit /b %RC%
