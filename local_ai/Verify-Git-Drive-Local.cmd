@echo off
setlocal
echo [Local AI] Read-only GitHub + Google Drive Desktop configuration check.
rem RemoteSigned applies only to this child PowerShell process. Do not alter machine/user policy.
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0verify-git-drive-local.ps1"
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
