@echo off
REM Private Salesforce Contact lookup web preview on an authorized Windows PC.
REM Binds to loopback only. No Salesforce Save or customer data upload.
setlocal
set "WEB_ROOT=%~dp0..\..\masteros\web"
if not exist "%WEB_ROOT%\node_modules\next\dist\bin\next" (
  echo Missing Next.js dependencies in %WEB_ROOT%
  echo Run npm.cmd install --no-audit --no-fund from the web directory.
  exit /b 1
)
if not exist "%WEB_ROOT%\.next\BUILD_ID" (
  echo Missing compiled Next.js build.
  echo Run npm.cmd run build from the web directory.
  exit /b 1
)
if /i "%~1"=="--check" (
  echo SFDC local web prerequisites OK. No server started.
  exit /b 0
)
set "SFDC_LOCAL_CONTACT_LOOKUP_ENABLED=1"
set "NEXT_TELEMETRY_DISABLED=1"
cd /d "%WEB_ROOT%"
echo Starting read-only, loopback-only web: http://127.0.0.1:31889/sales/oppo-quote
node node_modules\next\dist\bin\next start --hostname 127.0.0.1 --port 31889
endlocal
