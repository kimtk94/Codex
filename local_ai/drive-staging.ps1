# Explicit, one-file-at-a-time Google Drive for desktop transfer.
# Data is never committed or uploaded through the GitHub CLI.
[CmdletBinding()]
param(
    [ValidateSet("Status","Import","Export")]
    [string]$Action = "Status",
    [string]$FileName = ""
)
$ErrorActionPreference = "Stop"
$configPath = Join-Path $env:LOCALAPPDATA "LocalAI\workspace.json"
try {
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        throw "Workspace not configured: run Setup-Git-Drive.cmd first."
    }
    $cfg = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $repo = [string]$cfg.repository_path
    $drive = [string]$cfg.drive_workspace_path
    if (-not (Test-Path -LiteralPath (Join-Path $repo ".git"))) { throw "Git repo missing: $repo" }
    if ([string]::IsNullOrWhiteSpace($drive) -or -not (Test-Path -LiteralPath $drive -PathType Container)) {
        throw "Google Drive sync folder unavailable. Open Google Drive for desktop and rerun Setup-Git-Drive.cmd."
    }
    $local = Join-Path $repo ".local_ai_data"
    if ($Action -eq "Status") {
        Write-Host "Git repository: $repo"
        Write-Host "Drive for desktop folder: $drive"
        Write-Host "Staging area: $local"
        Write-Host "Import from <Drive>\inbox to <repo>\.local_ai_data\inbox"
        Write-Host "Export from <repo>\.local_ai_data\outbox to <Drive>\results"
        Write-Host "IMPORTANT: Existence of the Drive path does not verify Google cloud synchronization."
        exit 0
    }
    if ([string]::IsNullOrWhiteSpace($FileName) -or $FileName -ne [IO.Path]::GetFileName($FileName) -or $FileName -match '[\\/:*?"<>|]' -or $FileName -eq "." -or $FileName -eq "..") {
        throw "Supply an exact filename only, without paths or wildcards."
    }
    $permitted = @(".md",".txt",".json",".csv",".tsv",".pdf",".xlsx",".zip",".gz",".parquet")
    if ($permitted -notcontains [IO.Path]::GetExtension($FileName).ToLowerInvariant()) {
        throw "Unsupported file type. This bridge deliberately blocks executable/script files."
    }
    if ($Action -eq "Import") {
        $source = Join-Path (Join-Path $drive "inbox") $FileName
        $destDir = Join-Path $local "inbox"
    } else {
        $source = Join-Path (Join-Path $local "outbox") $FileName
        $destDir = Join-Path $drive "results"
    }
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Source file not found: $source" }
    $sourceFile = Get-Item -LiteralPath $source -Force
    if (($sourceFile.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Symlink/reparse source rejected." }
    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    $target = Join-Path $destDir $FileName
    if (Test-Path -LiteralPath $target) { throw "Destination already exists. Choose a new filename; no overwrite performed." }
    Copy-Item -LiteralPath $source -Destination $target
    Write-Host "Copied $Action file: $FileName"
    Write-Host "Destination: $target"
    if ($Action -eq "Export") {
        Write-Host "Confirm Google Drive for desktop reports upload complete; local copy alone does not prove cloud upload."
    }
    Write-Host "No Git commit/push performed."
} catch {
    Write-Error "Drive transfer failed: $_"
    exit 1
}
