@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0start-css-local.ps1" %*
if errorlevel 1 (
  echo Local CSS dashboard failed. Check the console message.
  exit /b 1
)
endlocal
