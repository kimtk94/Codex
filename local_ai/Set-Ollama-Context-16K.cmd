@echo off
setlocal
cd /d "%~dp0.."
echo [Local AI] Set Ollama context window to 16K for Codex (user-level setting).
powershell.exe -NoProfile -File "%~dp0set-ollama-context.ps1" -Mode Apply -ContextTokens 16384
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" echo IMPORTANT: Fully Quit Ollama from the Windows system tray, then restart it.
if not "%RC%"=="0" echo Context setting failed. Review the error above.
pause
exit /b %RC%
