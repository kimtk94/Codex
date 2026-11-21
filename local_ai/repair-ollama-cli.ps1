# Repair missing "ollama" command in Windows PowerShell/VS Code terminal.
# Uses known official installation paths; no reinstall or Administrator rights.
# With -Persist, updates the CURRENT USER PATH only (not machine PATH).
[CmdletBinding()]
param([switch]$Persist)
$ErrorActionPreference = "Stop"
try {
    Write-Host "=== Ollama CLI discovery ==="
    $existing = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($existing) {
        $exePath = $existing.Source
    } else {
        $candidates = @(
            (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
            (Join-Path $env:ProgramFiles "Ollama\ollama.exe"),
            (Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\ollama.exe")
        )
        $exePath = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    }
    $apiReady = $false
    try {
        $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 8
        $apiReady = $true
        $modelNames = @($tags.models | ForEach-Object { [string]$_.name })
        Write-Host "Ollama local API: ONLINE"
        Write-Host "Installed models: $($modelNames -join ', ')"
    } catch {
        Write-Warning "Ollama local API not responding at 127.0.0.1:11434. Start Ollama from the Windows Start menu."
    }
    if (-not $exePath) {
        Write-Warning "Ollama CLI executable not found in common installation directories."
        Write-Host "This can occur when a running app is installed outside these paths."
        Write-Host "Find your actual ollama.exe location and append its PARENT directory to the USER PATH."
        if ($apiReady) {
            Write-Host "Codex can still use Ollama through the localhost API without the CLI command."
            exit 2
        }
        exit 1
    }
    $exePath = (Resolve-Path -LiteralPath $exePath).Path
    $directory = Split-Path -Parent $exePath
    Write-Host "Ollama CLI: $exePath"
    # Temporarily fix the path in THIS terminal, even when -Persist isn't used.
    $sessionPaths = @($env:Path -split ';' | Where-Object { $_ })
    if ($sessionPaths -notcontains $directory) {
        $env:Path = $env:Path.TrimEnd(';') + ';' + $directory
        Write-Host "Fixed PATH for this PowerShell process."
    }
    & $exePath --version
    if ($LASTEXITCODE -ne 0) { throw "Ollama CLI executable failed to run." }
    if ($Persist) {
        $userPath = [Environment]::GetEnvironmentVariable("Path","User")
        $userParts = @($userPath -split ';' | Where-Object { $_ })
        if ($userParts -notcontains $directory) {
            $newPath = ($userParts + $directory) -join ';'
            [Environment]::SetEnvironmentVariable("Path",$newPath,"User")
            Write-Host "Ollama directory added to CURRENT USER PATH."
            Write-Host "Close and reopen other PowerShell/VS Code terminals to pick up this change."
        } else {
            Write-Host "Current USER PATH already contains the Ollama directory."
            Write-Host "Reopen PowerShell/VS Code terminals to refresh the inherited PATH."
        }
    }
    Write-Host "Local API online: $apiReady"
    Write-Host "Try: ollama list"
    exit 0
} catch {
    Write-Error "Ollama PATH repair failed: $_"
    exit 1
}
