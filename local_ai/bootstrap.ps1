# Run from the root of the cloned Codex repository:
#   .\local_ai\bootstrap.ps1
#   .\local_ai\bootstrap.ps1 -PullModel
# Does not modify machine settings, ports, firewall, or GitHub runner configuration.
param(
    [string]$Model = "qwen3:4b",
    [switch]$PullModel
)

$ErrorActionPreference = "Stop"
Write-Host "=== Windows Local AI diagnostics ==="

$os = Get-CimInstance Win32_OperatingSystem
$computer = Get-CimInstance Win32_ComputerSystem
$ramGB = [math]::Round($computer.TotalPhysicalMemory / 1GB, 1)
Write-Host ("OS: {0}" -f $os.Caption)
Write-Host ("RAM: {0} GB" -f $ramGB)

try {
    $gpuNames = @(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name)
    Write-Host ("GPU: {0}" -f ($gpuNames -join ", "))
} catch {
    Write-Host "GPU: Could not detect; CPU execution remains available."
}

try {
    $ollama = Get-Command ollama -ErrorAction Stop
    Write-Host ("Ollama executable: {0}" -f $ollama.Source)
} catch {
    Write-Host "Ollama not installed or not in PATH."
    Write-Host "Install the official Windows app from https://ollama.com/download/windows"
    exit 2
}

if ($Model.EndsWith(":cloud", [System.StringComparison]::OrdinalIgnoreCase)) {
    Write-Host "Cloud models are not allowed in this local-only setup."
    exit 3
}

if ($PullModel) {
    Write-Host ("Downloading local model: {0}" -f $Model)
    & ollama pull $Model
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Model download failed."
        exit 4
    }
}

try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 10
    $names = @($tags.models | ForEach-Object { $_.name })
    Write-Host ("Local model(s): {0}" -f ($names -join ", "))
} catch {
    Write-Host "Ollama localhost API is not responding."
    Write-Host "Launch Ollama from the Start menu, then run this diagnostic again."
    exit 5
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python .\local_ai\ollama_client.py --check
    if ($LASTEXITCODE -ne 0) { exit 6 }
} else {
    Write-Host "Python not found: install Python 3.10+ to use ollama_client.py."
}
Write-Host "Diagnostics complete. No remote API or SFDC/Feishu writes were made."
