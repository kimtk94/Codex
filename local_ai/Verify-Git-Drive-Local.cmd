@echo off
setlocal
echo [Local AI] Read-only GitHub + Google Drive Desktop configuration check.
powershell.exe -NoProfile -File "%~dp0verify-git-drive-local.ps1"
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
