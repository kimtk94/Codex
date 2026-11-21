# Windows GitHub + Google Drive Desktop configuration health check.
# READ-ONLY. Verifies local paths and process status; does not prove Google cloud sync.
[CmdletBinding()]
param(
    [string]$Repo = "$env:USERPROFILE\Projects\Codex",
    [string]$DriveWorkspace = ""
)
$ErrorActionPreference = "Stop"

function Label([string]$name,[bool]$isPass) {
    $status = if ($isPass) {"PASS"} else {"PENDING"}
    Write-Host "$name : $status"
}

try {
    Write-Host "=== Local AI / GitHub / Drive read-only check ==="
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $git) { throw "Git for Windows unavailable" }
    $repoExists = Test-Path -LiteralPath (Join-Path $Repo ".git")
    Label "Git repository" $repoExists
    if ($repoExists) {
        $resolved = (Resolve-Path -LiteralPath $Repo).Path
        $origin = (& git.exe -C $resolved remote get-url origin)
        $originValid = ($LASTEXITCODE -eq 0 -and $origin -match "^(https://github.com/kimtk94/Codex(\.git)?|git@github.com:kimtk94/Codex(\.git)?)$")
        Label "Expected GitHub origin" $originValid
        Write-Host "Current branch: $(& git.exe -C $resolved branch --show-current)"
        $dirty = @(& git.exe -C $resolved status --porcelain)
        Write-Host "Working tree: $(if (@($dirty | Where-Object { $_ }).Count -eq 0) {'clean'} else {'has local changes (not modified by this check)'})"
    } else {
        $originValid = $false
    }

    $gh = Get-Command gh.exe -ErrorAction SilentlyContinue
    $authValid = $false
    if ($gh) {
        & gh.exe auth status *> $null
        $authValid = $LASTEXITCODE -eq 0
    }
    Label "GitHub CLI authenticated" $authValid

    $workspaceConfig = Join-Path $env:LOCALAPPDATA "LocalAI\workspace.json"
    if (-not $DriveWorkspace -and (Test-Path -LiteralPath $workspaceConfig -PathType Leaf)) {
        try {
            $cfg = Get-Content -LiteralPath $workspaceConfig -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($cfg.drive_workspace_path) { $DriveWorkspace = [string]$cfg.drive_workspace_path }
        } catch {
            Write-Warning "LocalAI workspace.json exists but could not be read."
        }
    }
    if (-not $DriveWorkspace) {
        foreach ($volume in @("G:","H:","I:","D:","E:","F:")) {
            foreach ($folder in @("My Drive","내 드라이브")) {
                $candidate = Join-Path "$volume\" (Join-Path $folder "LocalAI_Workspace")
                if (Test-Path -LiteralPath $candidate -PathType Container) {
                    $DriveWorkspace = $candidate
                    break
                }
            }
            if ($DriveWorkspace) { break }
        }
    }
    $folderExists = $false
    $childrenOK = $false
    if ($DriveWorkspace) {
        $folderExists = Test-Path -LiteralPath $DriveWorkspace -PathType Container
        if ($folderExists) {
            $childrenOK = (Test-Path -LiteralPath (Join-Path $DriveWorkspace "inbox") -PathType Container) -and
                          (Test-Path -LiteralPath (Join-Path $DriveWorkspace "results") -PathType Container)
            Write-Host "Local Drive folder: $DriveWorkspace"
        }
    }
    Label "Drive desktop folder accessible" $folderExists
    Label "Drive inbox/results accessible" $childrenOK
    $driveApp = @(Get-Process -Name "GoogleDriveFS" -ErrorAction SilentlyContinue)
    Label "Google Drive for desktop running" (@($driveApp).Count -gt 0)
    Write-Host "IMPORTANT: A folder or process existing does not prove cloud synchronization."
    Write-Host "Verify the sync status in Google Drive for desktop and check a non-sensitive test file in the Drive web UI."

    $ollamaAvailable = $false
    try {
        $ollama = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
        $ollamaAvailable = $true
        $localModels = @($ollama.models | ForEach-Object { $_.name })
        Label "Local Ollama API" $true
        Label "Qwen2.5 Coder 16K model" (($localModels -contains "qwen25coder3b-16k:latest") -or ($localModels -contains "qwen25coder3b-16k"))
    } catch {
        Label "Local Ollama API" $false
    }
    if (!$ollamaAvailable) {
        Write-Host "Start Ollama via the Windows Start menu if local inference is needed."
    }
    if ($repoExists -and $originValid -and $authValid -and $folderExists -and $childrenOK) {
        Write-Host "PASS: Local GitHub configuration and Drive directory structure are accessible."
        Write-Host "Cloud sync status and local model tool-calling remain UNVERIFIED."
        exit 0
    }
    Write-Warning "PENDING: At least one connection needs local configuration."
    exit 2
} catch {
    Write-Error "Health check failed: $_"
    exit 1
}
