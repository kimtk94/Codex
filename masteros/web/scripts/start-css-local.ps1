# Start CSS local workspace on the authorized workstation.
# No public bind, service account export, CRM mutation, or external hosting.
param(
  [int]$Port = 3000,
  [switch]$NoBrowser
)
$web = Split-Path -Parent $PSScriptRoot
$next = Join-Path $web 'node_modules\next\dist\bin\next'
$node = (Get-Command node.exe -ErrorAction SilentlyContinue).Source
if (-not $node) {
  $node = Join-Path $env:LOCALAPPDATA 'Programs\nodejs\node.exe'
}
if (-not (Test-Path $node)) {
  Write-Error "Node.js not installed. Install Node.js and retry."
  exit 1
}
if (-not (Test-Path $next)) {
  Write-Error "Dependencies missing. Run npm install from masteros\web."
  exit 1
}
if (-not (Test-Path (Join-Path $web '.next\BUILD_ID'))) {
  Write-Error "Production build missing. Run npm run build from masteros\web."
  exit 1
}

$url = "http://127.0.0.1:$Port/sales/commands"
$listener = Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort $Port -ErrorAction SilentlyContinue
if ($listener) {
  try {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
    if ($r.StatusCode -eq 200) {
      Write-Host "Existing local dashboard: $url"
      if (-not $NoBrowser) { Start-Process $url }
      exit 0
    }
  } catch {}
  Write-Error "Local port $Port is occupied by another process."
  exit 1
}

$env:CSS_LOCAL_PROJECTS_ENABLED = "1"
$env:SFDC_LOCAL_COMMAND_ENABLED = "1"
$env:SFDC_LOCAL_PYTHON = "python"
$env:SFDC_LOCAL_CONTACT_LOOKUP_ENABLED = "1"
$env:SFDC_LOCAL_FULL_AUDIT_ENABLED = "1"
$env:SFDC_LOCAL_REVIEW_ENABLED = "1"
$env:CSS_LOCAL_PYTHON = "python"
$env:CSS_LOCAL_MAIL_ENABLED = "1"
$env:CSS_LOCAL_MAIL_OWNER = "taehoon.kim@novogene.com"
$env:NEXT_TELEMETRY_DISABLED = "1"
$logDir = Join-Path $env:USERPROFILE '.sfdc_desktop'
if (-not (Test-Path $logDir)) {
  New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$stdOut = Join-Path $logDir 'css_local_web_stdout.log'
$stdErr = Join-Path $logDir 'css_local_web_stderr.log'
$proc = Start-Process -FilePath $node -ArgumentList @(
  $next, 'start', '--hostname', '127.0.0.1', '--port', [string]$Port
) -WorkingDirectory $web -RedirectStandardOutput $stdOut -RedirectStandardError $stdErr -PassThru
Write-Host "Started local-only dashboard PID=$($proc.Id), URL=$url"
Start-Sleep -Seconds 2
try {
  $result = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
  if ($result.StatusCode -ne 200) { throw 'Unexpected HTTP response' }
  Write-Host "HTTP 200 verified."
  if (-not $NoBrowser) { Start-Process $url }
} catch {
  Write-Error "Dashboard did not start. Check log files locally."
  exit 1
}
