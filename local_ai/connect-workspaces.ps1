# One-time Windows GitHub + Google Drive for desktop setup.
# Stores local folder paths only; never records tokens in repository files.
[CmdletBinding()]
param(
    [ValidateSet("Setup","Check")]
    [string]$Mode = "Check",
    [string]$Repository = "kimtk94/Codex",
    [string]$RepoPath = "",
    [string]$DriveWorkspacePath = ""
)
$ErrorActionPreference = "Stop"
$configDir = Join-Path $env:LOCALAPPDATA "LocalAI"
$configPath = Join-Path $configDir "workspace.json"
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function Has-Command([string]$name) {
    return $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}
function Install-IfMissing([string]$exe, [string]$wingetId) {
    if (Has-Command $exe) { return }
    if ($Mode -ne "Setup") { throw "Missing $exe. Run Setup-Git-Drive.cmd or install $wingetId." }
    if (-not (Has-Command "winget.exe")) { throw "winget not found. Install $wingetId manually." }
    Write-Host "Installing $wingetId with winget; confirm any installer prompt..."
    & winget.exe install --exact --id $wingetId --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget failed for $wingetId (exit $LASTEXITCODE)" }
    Refresh-Path
    if (-not (Has-Command $exe)) { throw "Installed $wingetId but $exe is not on PATH. Open a new PowerShell and retry." }
}
function Read-SavedConfig {
    if (!(Test-Path -LiteralPath $configPath -PathType Leaf)) { return $null }
    try { return (Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json) }
    catch { throw "Invalid local config: $configPath" }
}
function Test-DrivePath([string]$path) {
    return (-not [string]::IsNullOrWhiteSpace($path) -and (Test-Path -LiteralPath $path -PathType Container))
}
function Find-DriveWorkspace {
    foreach ($letter in @("G","H","I","D","E","F")) {
        foreach ($folder in @("My Drive","내 드라이브")) {
            $candidate = $letter + ":\" + $folder + "\LocalAI_Workspace"
            if (Test-DrivePath $candidate) { return $candidate }
        }
    }
    return ""
}
function Initialize-LocalGitExclusion([string]$path) {
    $exclude = Join-Path $path ".git\info\exclude"
    if (!(Test-Path -LiteralPath $exclude -PathType Leaf)) { throw "Git info/exclude not found: $path" }
    $content = Get-Content -LiteralPath $exclude -Raw -Encoding UTF8
    if ($content -notmatch '(?m)^\.local_ai_data/$') {
        Add-Content -LiteralPath $exclude -Value ".local_ai_data/" -Encoding UTF8
    }
    $staging = Join-Path $path ".local_ai_data"
    if (!(Test-Path -LiteralPath $staging)) {
        New-Item -ItemType Directory -Path $staging | Out-Null
    }
}
try {
    $saved = Read-SavedConfig
    if ([string]::IsNullOrWhiteSpace($RepoPath)) {
        if ($saved -and $saved.repository_path) { $RepoPath = [string]$saved.repository_path }
        else { $RepoPath = Join-Path $env:USERPROFILE "Projects\Codex" }
    }
    if ([string]::IsNullOrWhiteSpace($DriveWorkspacePath)) {
        if ($saved -and $saved.drive_workspace_path) { $DriveWorkspacePath = [string]$saved.drive_workspace_path }
        else { $DriveWorkspacePath = Find-DriveWorkspace }
    }
    Write-Host "=== Local AI GitHub + Google Drive workspace ($Mode) ==="
    Install-IfMissing "git.exe" "Git.Git"
    Install-IfMissing "gh.exe" "GitHub.cli"
    Write-Host "Git: $(& git.exe --version)"
    Write-Host "GitHub CLI: $(& gh.exe --version | Select-Object -First 1)"
    & gh.exe auth status *> $null
    $authenticated = $LASTEXITCODE -eq 0
    if (-not $authenticated -and $Mode -eq "Setup") {
        Write-Host "GitHub login required. Follow the browser-based GitHub CLI flow."
        & gh.exe auth login --hostname github.com --git-protocol https --web
        if ($LASTEXITCODE -ne 0) { throw "GitHub login did not complete." }
        & gh.exe auth setup-git
        if ($LASTEXITCODE -ne 0) { throw "GitHub credential helper setup did not complete." }
        & gh.exe auth status *> $null
        $authenticated = $LASTEXITCODE -eq 0
    }
    Write-Host "GitHub authenticated: $authenticated"
    if (-not $authenticated -and $Mode -eq "Setup") { throw "GitHub authentication is required." }
    if (-not (Test-Path -LiteralPath (Join-Path $RepoPath ".git"))) {
        if ($Mode -eq "Setup") {
            if (Test-Path -LiteralPath $RepoPath) {
                throw "Folder already exists but is not a Git clone: $RepoPath. Move/rename it manually."
            }
            New-Item -ItemType Directory -Path (Split-Path -Parent $RepoPath) -Force | Out-Null
            & gh.exe repo clone $Repository $RepoPath
            if ($LASTEXITCODE -ne 0) { throw "GitHub repository clone failed." }
        } else {
            Write-Host "Repository not cloned at $RepoPath"
        }
    }
    if (Test-Path -LiteralPath (Join-Path $RepoPath ".git")) {
        $origin = (& git.exe -C $RepoPath remote get-url origin)
        if ($LASTEXITCODE -ne 0) { throw "Could not read repository origin at $RepoPath" }
        if ($origin -notmatch "(?i)(^|[:/])$([regex]::Escape($Repository))(\.git)?$") {
            throw "Repository origin mismatch; refusing unrelated folder: $origin"
        }
        Write-Host "Git clone verified at $RepoPath"
        if ($Mode -eq "Setup") { Initialize-LocalGitExclusion $RepoPath }
    }
    if ($Mode -eq "Setup" -and -not (Test-DrivePath $DriveWorkspacePath)) {
        Write-Host "Google Drive for desktop must be signed in and showing a locally synced folder."
        Write-Host "Install: https://support.google.com/drive/answer/10838124?hl=ko"
        Write-Host "Create LocalAI_Workspace on Google Drive and copy its Windows folder path."
        $candidate = Read-Host "Enter EXISTING LocalAI_Workspace folder path (or blank to configure later)"
        if (-not [string]::IsNullOrWhiteSpace($candidate)) {
            $DriveWorkspacePath = $candidate.Trim('"')
        }
    }
    $driveConfigured = Test-DrivePath $DriveWorkspacePath
    if ($driveConfigured) {
        $DriveWorkspacePath = (Resolve-Path -LiteralPath $DriveWorkspacePath).Path
        Write-Host "Drive for desktop workspace found: $DriveWorkspacePath"
        Write-Host "NOTE: Verify this is genuinely synced by Google Drive; existence alone does not prove cloud sync."
    } else {
        $DriveWorkspacePath = ""
        Write-Warning "Google Drive workspace NOT configured. GitHub can still work; Drive remains pending."
    }
    if ($Mode -eq "Setup") {
        New-Item -ItemType Directory -Path $configDir -Force | Out-Null
        $cfg = [ordered]@{
            repository = $Repository
            repository_path = $RepoPath
            drive_workspace_path = $DriveWorkspacePath
            saved_utc = [DateTime]::UtcNow.ToString("o")
        }
        $cfg | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $configPath -Encoding UTF8
        Write-Host "Saved local paths (NO credentials): $configPath"
    }
    Write-Host ("STATUS GitHub auth: {0} | Repo: {1} | Drive folder: {2}" -f $authenticated, (Test-Path -LiteralPath (Join-Path $RepoPath ".git")), $driveConfigured)
    if (-not $driveConfigured -or -not $authenticated -or -not (Test-Path -LiteralPath (Join-Path $RepoPath ".git"))) { exit 2 }
    exit 0
} catch {
    Write-Error "Workspace setup failed: $_"
    exit 1
}
