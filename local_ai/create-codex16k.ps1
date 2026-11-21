# Windows Ollama: create an explicitly configured, persistent 16K-context model.
# No cloud inference, GitHub/Drive writes, sandbox bypass, or elevated privileges.
# Run via Fix-Codex-4096.cmd (from a reviewed repository).
[CmdletBinding()]
param(
    [string]$BaseModel = "qwen3:4b",
    [string]$Model = "qwen3-codex16k",
    [ValidateSet(8192,16384,32768)]
    [int]$ContextTokens = 16384
)
$ErrorActionPreference = "Stop"
try {
    if ($BaseModel -notmatch '^[A-Za-z0-9_./:-]{1,100}$' -or $Model -notmatch '^[A-Za-z0-9_./:-]{1,100}$') {
        throw "Invalid local Ollama model tag."
    }
    if ($BaseModel.EndsWith(":cloud", [StringComparison]::OrdinalIgnoreCase) -or $Model.EndsWith(":cloud", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Cloud models are not allowed."
    }
    if (-not (Get-Command ollama.exe -ErrorAction SilentlyContinue)) {
        throw "Ollama.exe is missing. Install and launch Ollama for Windows."
    }
    $api = "http://127.0.0.1:11434"
    $tags = Invoke-RestMethod -Method Get -Uri "$api/api/tags" -TimeoutSec 10
    $available = @($tags.models | ForEach-Object { $_.name })
    if ($available -notcontains $BaseModel -and $available -notcontains ($BaseModel + ":latest")) {
        throw "Base model '$BaseModel' missing locally. Run ollama pull $BaseModel first."
    }
    $dir = Join-Path $env:TEMP "local-ai-codex"
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    $modelfile = Join-Path $dir "Modelfile.qwen3-codex16k"
    $definition = "FROM $BaseModel" + [Environment]::NewLine + "PARAMETER num_ctx $ContextTokens" + [Environment]::NewLine
    $definition | Set-Content -LiteralPath $modelfile -Encoding Ascii

    Write-Host "Creating local model '$Model' from '$BaseModel' with num_ctx=$ContextTokens..."
    & ollama.exe create $Model -f $modelfile
    if ($LASTEXITCODE -ne 0) { throw "ollama create failed (exit code $LASTEXITCODE)." }

    # Check the saved model declaration BEFORE running it.
    $modelConfig = (& ollama.exe show $Model --modelfile) -join [Environment]::NewLine
    if ($LASTEXITCODE -ne 0 -or $modelConfig -notmatch "(?m)^\s*PARAMETER\s+num_ctx\s+$ContextTokens\s*$") {
        throw "Saved model does not declare PARAMETER num_ctx $ContextTokens."
    }
    Write-Host "Verified saved Modelfile: PARAMETER num_ctx $ContextTokens"

    $payload = @{
        model = $Model
        prompt = "Reply with OK only."
        stream = $false
        think = $false
        keep_alive = "3m"
        options = @{ num_predict = 16; temperature = 0 }
    } | ConvertTo-Json -Depth 5
    Write-Host "Running ONE synthetic prompt to verify real model loading (may be slow on CPU)..."
    $reply = Invoke-RestMethod -Uri "$api/api/generate" -Method Post -Body $payload -ContentType "application/json" -TimeoutSec 240
    if ([string]::IsNullOrWhiteSpace([string]$reply.response)) {
        throw "Ollama returned no text during synthetic inference."
    }
    $loaded = Invoke-RestMethod -Uri "$api/api/ps" -Method Get -TimeoutSec 10
    $found = @($loaded.models | Where-Object {
        $_.name -eq $Model -or $_.model -eq $Model -or
        $_.name -eq ($Model + ":latest") -or $_.model -eq ($Model + ":latest")
    }) | Select-Object -First 1
    if (-not $found) { throw "Created model missing from /api/ps after inference." }
    $effective = [int]$found.context_length
    Write-Host "Effective model CONTEXT: $effective tokens"
    if ($effective -lt $ContextTokens) {
        throw "Model declaration is $ContextTokens, but server actually allocated only $effective. Check Ollama app Context length and model settings."
    }
    Write-Host "PASS: Local model '$Model' supports $effective tokens of context."
    Write-Host "Next command: codex.cmd --oss -m $Model -c 'model_context_window=$ContextTokens'"
    exit 0
} catch {
    Write-Error "Codex 4096-context fix failed: $_"
    exit 1
}
