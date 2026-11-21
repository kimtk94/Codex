# Read-only smoke check for real Ollama context allocation on Windows.
# No GitHub/Google Drive API calls, no file modifications, no customer data.
[CmdletBinding()]
param(
    [string]$Model = "qwen3:4b",
    [ValidateRange(8192,131072)]
    [int]$MinimumContext = 16384
)
$ErrorActionPreference = "Stop"
try {
    if ($Model -notmatch '^[a-zA-Z0-9_./:-]{1,100}$' -or $Model.EndsWith(":cloud", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Invalid local model tag. Cloud models are not supported."
    }
    $baseUrl = "http://127.0.0.1:11434"
    Write-Host "=== Ollama context smoke test (read-only/synthetic prompt) ==="
    Write-Host "Model=$Model | RequiredContext=$MinimumContext"
    $saved = [Environment]::GetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH","User")
    Write-Host "Saved user OLLAMA_CONTEXT_LENGTH=$(if ($saved) { $saved } else { '<unset>' })"
    $os = Get-CimInstance Win32_OperatingSystem
    $freeGB = [Math]::Round($os.FreePhysicalMemory / 1MB, 2)
    Write-Host "Windows available system RAM: $freeGB GB"
    if ($freeGB -lt 3.0) {
        Write-Warning "Less than 3 GB available; model loading may fail or become very slow."
    }
    $tags = Invoke-RestMethod -Uri "$baseUrl/api/tags" -Method Get -TimeoutSec 10
    $models = @($tags.models | ForEach-Object { $_.name })
    if ($models -notcontains $Model -and $models -notcontains ($Model + ":latest")) {
        throw "Model not installed locally: $Model. Run Fix-Codex-4096.cmd to create it."
    }

    # IMPORTANT: omit options.num_ctx so /api/ps reports the true model default,
    # including the environment / Ollama desktop Settings applied to the server.
    $payload = @{
        model = $Model
        prompt = "Reply with the single English word OK."
        stream = $false
        think = $false
        keep_alive = "3m"
        options = @{ num_predict = 16; temperature = 0 }
    } | ConvertTo-Json -Depth 5

    Write-Host "Loading model using a synthetic, non-sensitive prompt (may use CPU)..."
    $reply = Invoke-RestMethod -Uri "$baseUrl/api/generate" -Method Post -Body $payload -ContentType "application/json" -TimeoutSec 240
    if ($null -eq $reply.response -or [string]::IsNullOrWhiteSpace([string]$reply.response)) {
        throw "No inference response returned by Ollama."
    }
    Write-Host "Synthetic inference response received. No user data was transmitted."
    $loaded = Invoke-RestMethod -Uri "$baseUrl/api/ps" -Method Get -TimeoutSec 10
    $selected = @($loaded.models | Where-Object { ($_.name -eq $Model -or $_.model -eq $Model -or $_.name -eq ($Model + ":latest") -or $_.model -eq ($Model + ":latest")) }) | Select-Object -First 1
    if ($null -eq $selected -or @($selected).Count -eq 0) {
        throw "Ollama model was not listed as loaded in /api/ps. Check ollama ps."
    }
    $actual = [int]$selected.context_length
    $processor = if ($selected.size_vram -and $selected.size) {
        $ratio = [math]::Round(100 * [double]$selected.size_vram / [double]$selected.size, 1)
        "$ratio percent of model memory in VRAM (estimate)"
    } else { "unknown" }
    Write-Host "Effective loaded CONTEXT=$actual | Minimum=$MinimumContext | VRAM=$processor"
    if ($actual -lt $MinimumContext) {
        Write-Warning "FAIL: Ollama is still allocating only $actual tokens, below requested $MinimumContext."
        Write-Warning "Quit Ollama completely from system tray and restart. Check app Context length settings."
        Write-Warning "Then rerun Verify-Local-Codex-16K.cmd before launching Codex."
        exit 2
    }
    Write-Host "PASS: Real localhost inference worked and loaded context >= $MinimumContext."
    Write-Host "Next: launch Codex using Start-Local-Codex.cmd, run /status, and try a read-only short prompt."
    exit 0
} catch {
    Write-Error "Ollama smoke test failed: $_"
    exit 1
}
