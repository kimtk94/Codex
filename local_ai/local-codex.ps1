# Local Windows Codex launcher. Run using Setup-Local-Codex.cmd / Start-Local-Codex.cmd.
# Installs only Node.js LTS (if missing) and official @openai/codex (on Setup).
# Never changes execution policy, registers a runner, changes CRM, or opens network ports.
[CmdletBinding()]
param(
    [ValidateSet("Setup", "Start", "Diagnose")]
    [string]$Mode = "Diagnose",
    [string]$Model = "qwen25coder3b-16k",
    [string]$ProjectPath = ""
)

$ErrorActionPreference = "Stop"

function Get-Exe([string]$CommandName) {
    return (Get-Command $CommandName -ErrorAction SilentlyContinue)
}

function Refresh-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Require-Ollama {
    if (-not (Get-Exe "ollama.exe")) {
        throw "Ollama was not found. Install the Windows app from https://ollama.com/download/windows."
    }
    try {
        $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 8
    } catch {
        throw "Ollama localhost API is offline. Launch Ollama from Start, then retry. Details: $_"
    }
    $installed = @($tags.models | ForEach-Object { $_.name })
    Write-Host "Installed Ollama models: $($installed -join ', ')"
    return $installed
}

function Require-NodeNpm {
    $node = Get-Exe "node.exe"
    $npm = Get-Exe "npm.cmd" # Avoid PowerShell npm.ps1 execution-policy errors.
    if ($node -and $npm) {
        Write-Host "Node: $(& node.exe --version)"
        Write-Host "npm: $(& npm.cmd --version)"
        return
    }
    if ($Mode -ne "Setup") {
        throw "Node.js/npm missing. Run Setup-Local-Codex.cmd first."
    }
    if (-not (Get-Exe "winget.exe")) {
        throw "winget was not found. Install Node.js LTS from https://nodejs.org/en/download, open a NEW terminal, and rerun Setup."
    }
    if (Get-Exe "nvm.exe") {
        throw "nvm-windows detected but node/npm not active. Activate your existing Node.js installation with nvm use; do not mix winget Node installations."
    }
    Write-Host "Installing official Node.js LTS (includes npm) through winget..."
    & winget.exe install --exact --id OpenJS.NodeJS.LTS --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Node.js installation did not succeed. winget exit code: $LASTEXITCODE"
    }
    Refresh-SessionPath
    if (-not (Get-Exe "node.exe") -or -not (Get-Exe "npm.cmd")) {
        throw "Node.js was installed, but PATH not refreshed. Close terminals and rerun Setup-Local-Codex.cmd."
    }
    Write-Host "Node: $(& node.exe --version)"
    Write-Host "npm: $(& npm.cmd --version)"
}

try {
    if ($Model -notmatch '^[A-Za-z0-9_./:-]{1,100}$' -or $Model.EndsWith(":cloud", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Specify a valid local Ollama model tag (not a :cloud tag)."
    }
    Write-Host "=== Local AI / Codex / Windows ==="
    Write-Host "Mode: $Mode | Model: $Model"
    if ($Mode -eq "Setup" -or $Mode -eq "Diagnose") {
        Require-NodeNpm
        if ($Mode -eq "Setup") {
            Write-Host "Installing/updating official OpenAI Codex CLI via npm..."
            & npm.cmd install --global "@openai/codex"
            if ($LASTEXITCODE -ne 0) { throw "npm install failed. Exit code: $LASTEXITCODE" }
            Refresh-SessionPath
        }
    } elseif (-not (Get-Exe "npm.cmd")) {
        throw "npm is missing. Run Setup-Local-Codex.cmd."
    }

    $codex = Get-Exe "codex.cmd"
    if (-not $codex) {
        throw "Codex CLI missing from PATH. Run Setup-Local-Codex.cmd and reopen terminal if needed."
    }
    Write-Host "Codex: $(& codex.cmd --version)"

    $models = @(Require-Ollama)
    # Ollama lists untagged custom aliases as name:latest.
    $modelAvailable = ($models -contains $Model) -or ($models -contains ($Model + ":latest"))
    $customBaseModels = @{
        "qwen3-codex16k" = "qwen3:4b"
        "qwen25coder3b-16k" = "qwen2.5-coder:3b"
    }
    $alias = $Model -replace ":latest$", ""
    if (-not $modelAvailable -and $Mode -eq "Start" -and $customBaseModels.ContainsKey($alias)) {
        # An Ollama custom alias is NOT a registry model. Create from an existing base.
        $baseModel = $customBaseModels[$alias]
        $creator = Join-Path $PSScriptRoot "create-codex16k.ps1"
        if (-not (Test-Path -LiteralPath $creator -PathType Leaf)) {
            throw "Local 16K model creator is missing: $creator"
        }
        Write-Host "Local model '$alias' is missing. Creating it from '$baseModel'..."
        & powershell.exe -NoProfile -File $creator -BaseModel $baseModel -Model $alias -ContextTokens 16384
        if ($LASTEXITCODE -ne 0) {
            throw "Custom model creation failed. Check that base '$baseModel' is installed (ollama list)."
        }
        $models = @(Require-Ollama)
        $modelAvailable = ($models -contains $Model) -or ($models -contains ($alias + ":latest"))
    }
    if (-not $modelAvailable) {
        if ($Mode -eq "Setup") {
            Write-Host "Downloading local Ollama model: $Model"
            & ollama.exe pull $Model
            if ($LASTEXITCODE -ne 0) { throw "ollama pull failed. Exit code: $LASTEXITCODE" }
            $models = @(Require-Ollama)
            if ($models -notcontains $Model -and $models -notcontains ($Model + ":latest")) { throw "Model download could not be verified." }
        } else {
            throw "Model '$Model' is not installed. Pull the base registry model, then run Start-Local-Codex.cmd to create a local 16K alias."
        }
    }

    if ($Mode -eq "Start") {
        if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
            # Prefer a previously configured GitHub clone for repeatable sessions.
            $workspaceConfig = Join-Path $env:LOCALAPPDATA "LocalAI\workspace.json"
            if (Test-Path -LiteralPath $workspaceConfig -PathType Leaf) {
                try {
                    $workspace = Get-Content -LiteralPath $workspaceConfig -Raw -Encoding UTF8 | ConvertFrom-Json
                    if ($workspace.repository_path -and
                        (Test-Path -LiteralPath ([string]$workspace.repository_path) -PathType Container)) {
                        $ProjectPath = [string]$workspace.repository_path
                        Write-Host "Using saved GitHub clone as project directory."
                    }
                } catch {
                    Write-Warning "Saved workspace config is unreadable; using launcher directory."
                }
            }
        }
        if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
            $ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
        }
        if (-not (Test-Path -LiteralPath $ProjectPath -PathType Container)) {
            throw "Project folder not found: $ProjectPath"
        }
        $resolved = (Resolve-Path -LiteralPath $ProjectPath).Path
        Write-Host "Project folder: $resolved"
        Write-Host "Starting LOCAL Codex with explicit model $Model (not cloud)."
        $savedContext = [Environment]::GetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH", "User")
        if ($alias -notin @("qwen3-codex16k","qwen25coder3b-16k") -and $savedContext -ne "16384") {
            Write-Warning "The Ollama server's context may be smaller than 16K. Verify with ollama ps."
        }
        Write-Host "Codex recommendations: use it on a git branch and REVIEW every change."
        Push-Location -LiteralPath $resolved
        try {
            # --oss uses Ollama. Context budget is aligned with our Windows 16K preset.
            # This Codex-side value alone does NOT increase Ollama server allocation.
            # For local 16K aliases, Modelfile PARAMETER num_ctx supplies the server-side setting.
            & codex.cmd --oss -m $Model -c 'model_context_window=16384' -c 'web_search="disabled"'
            if ($LASTEXITCODE -ne 0) { throw "Codex exited with code $LASTEXITCODE." }
        } finally {
            Pop-Location
        }
    } else {
        Write-Host "Local prerequisites verified."
        Write-Host "Next use: double-click Start-Local-Codex.cmd."
    }
} catch {
    Write-Error "Local Codex setup failed: $_"
    exit 1
}
