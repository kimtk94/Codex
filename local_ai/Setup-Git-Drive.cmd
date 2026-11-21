@echo off
setlocal
cd /d "%~dp0.."
echo [Local AI] GitHub + Google Drive for desktop setup
echo [Local AI] You will sign in to GitHub via your browser if needed.
echo [Local AI] Google Drive sign-in is separate: use the official Drive for desktop app.
powershell.exe -NoProfile -File "%~dp0connect-workspaces.ps1" -Mode Setup
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [Local AI] Connection incomplete. Follow the on-screen Git or Drive instructions.
if "%RC%"=="0" echo [Local AI] GitHub repo and Drive folder paths verified.
pause
exit /b %RC%
