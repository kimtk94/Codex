@echo off
setlocal
cd /d "%~dp0.."
powershell.exe -NoProfile -File "%~dp0connect-workspaces.ps1" -Mode Check
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
