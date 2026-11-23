@echo off
setlocal
echo [Local AI] Google Drive desktop guided install and folder detection.
echo [Local AI] Google sign-in and account selection require your interaction.
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0setup-drive-desktop.ps1" -InstallIfMissing
set "RC=%ERRORLEVEL%"
if "%RC%"=="2" echo [Local AI] PENDING: sign into Drive desktop and run again.
if "%RC%"=="0" echo [Local AI] Workspace path saved. Confirm cloud sync separately.
pause
exit /b %RC%
