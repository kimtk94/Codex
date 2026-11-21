# Guided Google Drive for desktop setup. Account login remains user-controlled.
# No Drive API calls, file uploads or Git writes. Only stores selected local path.
[CmdletBinding()]
param([switch]$InstallIfMissing,[string]$DriveWorkspace="")
$ErrorActionPreference = "Stop"
try {
    Write-Host "=== Google Drive for desktop / LocalAI_Workspace ==="
    $program86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    $locations = @(
        (Join-Path $env:ProgramFiles "Google\Drive File Stream"),
        $(if ($program86) { Join-Path $program86 "Google\Drive File Stream" })
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Container) }
    $exe = $null
    foreach ($location in $locations) {
        $exe = Get-ChildItem -LiteralPath $location -Filter "GoogleDriveFS.exe" -File -Recurse -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
        if ($exe) { break }
    }
    $running = @(Get-Process -Name GoogleDriveFS -ErrorAction SilentlyContinue).Count -gt 0
    if (-not $exe -and -not $running) {
        Write-Warning "Google Drive desktop installation not detected."
        if ($InstallIfMissing) {
            # Google's official enterprise documentation requires computer administrator
            # privileges for Drive for desktop installation. Do not endlessly retry
            # winget after error 1603 on a non-elevated session.
            $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
            $principal = New-Object Security.Principal.WindowsPrincipal($identity)
            $elevated = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
            if (-not $elevated) {
                Write-Warning "Google Drive installer 1603 previously seen; this PowerShell is not elevated."
                Write-Host "Installation was NOT attempted. Ask an authorized administrator/IT to install Drive for desktop."
                Write-Host "GitHub and Ollama can continue working; Drive Desktop sync remains PENDING."
                Write-Host "Existing cloud folder: https://drive.google.com/drive/folders/1uaLzCm1GpjgbmBoI6wQ1dDMcLeb6JD-b"
                exit 2
            }
            if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
                Write-Warning "winget missing. Get installer from https://support.google.com/drive/answer/10838124?hl=ko"
                exit 2
            }
            Write-Host "Installing official Google.GoogleDrive package; Windows may require approval."
            & winget.exe install --id Google.GoogleDrive --exact --source winget --accept-source-agreements --accept-package-agreements
            if ($LASTEXITCODE -ne 0) { Write-Warning "Installer did not complete. Respect enterprise policy."; exit 2 }
        }
    } else {
        Write-Host "Google Drive desktop: executable found=$([bool]$exe); running=$running"
    }

    if (-not $DriveWorkspace) {
        $koreanMyDrive = -join @([char]0xB0B4,[char]0x20,[char]0xB4DC,[char]0xB77C,[char]0xC774,[char]0xBE0C)
        $roots = @(Get-PSDrive -PSProvider FileSystem | ForEach-Object { $_.Root })
        $roots += @((Join-Path $env:USERPROFILE "Google Drive"),$env:USERPROFILE)
        foreach ($root in $roots) {
            foreach ($prefix in @("My Drive",$koreanMyDrive)) {
                $candidate = Join-Path $root (Join-Path $prefix "LocalAI_Workspace")
                if (Test-Path -LiteralPath $candidate -PathType Container) {
                    $DriveWorkspace = $candidate
                    break
                }
            }
            if ($DriveWorkspace) { break }
        }
    }
    if (-not $DriveWorkspace -or -not (Test-Path -LiteralPath $DriveWorkspace -PathType Container)) {
        Write-Warning "LocalAI_Workspace is not mounted in Windows."
        Write-Host "Open Google Drive from Start and sign in to the account holding the existing folder."
        Write-Host "Existing cloud folder: https://drive.google.com/drive/folders/1uaLzCm1GpjgbmBoI6wQ1dDMcLeb6JD-b"
        Write-Host "Open that folder in Windows File Explorer, copy its path, and pass -DriveWorkspace."
        Write-Host "Do NOT create a duplicate cloud folder."
        exit 2
    }
    $resolved = (Resolve-Path -LiteralPath $DriveWorkspace).Path
    $inbox = Test-Path -LiteralPath (Join-Path $resolved "inbox") -PathType Container
    $results = Test-Path -LiteralPath (Join-Path $resolved "results") -PathType Container
    if (-not $inbox -or -not $results) {
        Write-Warning "Drive folder exists, but inbox or results is missing. Check account/sync state."
        exit 2
    }
    $configDir = Join-Path $env:LOCALAPPDATA "LocalAI"
    $configFile = Join-Path $configDir "workspace.json"
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null
    $config = @{}
    if (Test-Path -LiteralPath $configFile -PathType Leaf) {
        $fromJson = Get-Content -LiteralPath $configFile -Encoding UTF8 -Raw | ConvertFrom-Json
        foreach ($p in $fromJson.PSObject.Properties) { $config[$p.Name] = $p.Value }
    }
    $config["drive_workspace_path"] = $resolved
    $config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $configFile -Encoding UTF8
    Write-Host "PASS: Drive inbox/results accessible: $resolved"
    Write-Host "Saved local path only: $configFile"
    Write-Host "IMPORTANT: Confirm real cloud sync status in the Drive desktop app and Drive web."
    exit 0
} catch {
    Write-Error "Drive Desktop guided setup failed: $_"
    exit 1
}
