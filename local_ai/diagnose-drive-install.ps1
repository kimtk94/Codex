# Read-only diagnosis for Google Drive for desktop installer exit 1603.
# No changes to PowerShell policy, services, registry, permissions or installed apps.
# Does not upload logs or expose credentials.
[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
try {
    Write-Host "=== Google Drive for desktop install 1603 diagnostics ==="
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    Write-Host "Current PowerShell elevated: $isAdmin"
    Write-Host "A false result does not prove this caused error 1603."

    $program86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    $folders = @((Join-Path $env:ProgramFiles "Google\Drive File Stream"))
    if ($program86) { $folders += (Join-Path $program86 "Google\Drive File Stream") }
    foreach ($folder in $folders) {
        Write-Host "Possible install folder: $folder | Exists=$(Test-Path -LiteralPath $folder -PathType Container)"
    }
    $running = @(Get-Process -Name GoogleDriveFS -ErrorAction SilentlyContinue).Count -gt 0
    Write-Host "GoogleDriveFS running: $running"

    $registered = @()
    foreach ($root in @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )) {
        $registered += @(Get-ItemProperty -Path $root -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like "*Google Drive*" } |
            Select-Object DisplayName,DisplayVersion,Publisher)
    }
    if ($registered.Count) { $registered | Format-Table -AutoSize | Out-Host }
    else { Write-Host "No Google Drive uninstall registration found." }

    Write-Host "Recent Google installer logs in Windows TEMP (filenames ONLY):"
    $logs = @(Get-ChildItem -LiteralPath $env:TEMP -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "(?i)GoogleDrive|DriveFS|GoogleUpdate" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 15 Name, LastWriteTime, Length, FullName)
    if ($logs.Count) {
        $logs | Format-Table Name,LastWriteTime,Length -AutoSize | Out-Host
    } else { Write-Host "No matching files in current user TEMP." }

    Write-Host "Recent MSI installer events (metadata only):"
    try {
        $events = @(Get-WinEvent -FilterHashtable @{
            LogName = "Application"
            ProviderName = "MsiInstaller"
            StartTime = (Get-Date).AddHours(-6)
        } -MaxEvents 15 -ErrorAction Stop)
        if ($events.Count) {
            $events | Select-Object TimeCreated,Id,LevelDisplayName |
                Format-Table -AutoSize | Out-Host
        }
    } catch {
        Write-Host "No readable recent MsiInstaller events."
    }
    Write-Host "Diagnosis complete. Do not share raw installer logs without redacting paths, account names and credentials."
    if (-not $isAdmin) {
        Write-Host "If Windows installation requires elevation, use authorized administrator approval."
        Write-Host "Do not bypass corporate endpoint protection, group policy or Windows security."
    }
    Write-Host "Official Drive Desktop help: https://support.google.com/drive/answer/10838124?hl=ko"
    exit 0
} catch {
    Write-Error "Drive installation diagnostic failed: $_"
    exit 1
}
