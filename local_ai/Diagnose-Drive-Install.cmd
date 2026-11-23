@echo off
setlocal
echo [Local AI] Google Drive for desktop installer error 1603 read-only diagnostics.
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0diagnose-drive-install.ps1"
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
