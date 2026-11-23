# Windows Ollama user-level context setting for Codex on a 16GB laptop.
# Does not require Administrator rights; never edits global Windows environment or firewall.
# Restart Ollama from its taskbar icon to apply. Does not kill existing processes.
[CmdletBinding()]
param(
    [ValidateSet("Apply","Check")]
    [string]$Mode = "Check",
    [ValidateSet(8192,16384,32768)]
    [int]$ContextTokens = 16384
)

$ErrorActionPreference = "Stop"
try {
    $previous = [Environment]::GetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH","User")
    Write-Host "Ollama context (saved user value): $(if($previous) {$previous} else {'<default>'})"
    if ($Mode -eq "Apply") {
        [Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH", [string]$ContextTokens, "User")
        $saved = [Environment]::GetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH","User")
        if ($saved -ne [string]$ContextTokens) {
            throw "Could not persist OLLAMA_CONTEXT_LENGTH in the user environment."
        }
        Write-Host "Saved OLLAMA_CONTEXT_LENGTH=$saved (user scope)"
        Write-Host "NEXT: Close the currently running Codex session."
        Write-Host "NEXT: Right-click Ollama in the Windows system tray and choose Quit."
        Write-Host "NEXT: Restart Ollama from the Start menu so its server inherits the new setting."
        Write-Host "NEXT: Open a fresh PowerShell, then launch Codex again."
        Write-Host "NOTE: This changes the default for ALL Ollama models started by this Windows user."
    }
    if (Get-Command "ollama.exe" -ErrorAction SilentlyContinue) {
        Write-Host "Loaded model state (CONTEXT column, if available):"
        & ollama.exe ps
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Ollama is not currently responding. Start Ollama before testing."
        }
    } else {
        Write-Warning "Ollama executable not found on PATH."
    }
    Write-Host "No model inference or GitHub/Google Drive write was performed."
} catch {
    Write-Error "Ollama context setup failed: $_"
    exit 1
}
