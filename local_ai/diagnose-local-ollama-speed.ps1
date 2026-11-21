# Diagnostic only: print hardware, currently loaded Ollama model/context, and
# generate a small synthetic prompt to assess baseline local throughput.
# NO Git writes, Drive access, model downloads, telemetry upload or file modification.
[CmdletBinding()]
param(
    [string]$Model = "qwen3-codex16k:latest",
    [ValidateRange(10,300)] [int]$TimeoutSeconds = 120
)
$ErrorActionPreference = "Stop"
try {
    if ($Model -notmatch '^[a-zA-Z0-9_./:-]{1,100}$' -or $Model.EndsWith(":cloud",[StringComparison]::OrdinalIgnoreCase)) {
        throw "Invalid local Ollama model tag."
    }
    Write-Host "=== Local Ollama speed / 16GB RAM diagnostics ==="
    $os = Get-CimInstance Win32_OperatingSystem
    $memFree = [math]::Round([double]$os.FreePhysicalMemory / 1MB, 2)
    $memTotal = [math]::Round([double]$os.TotalVisibleMemorySize / 1MB, 2)
    Write-Host "Available RAM: $memFree GB / $memTotal GB"
    $gpus = @(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name)
    Write-Host "Windows GPU(s): $($gpus -join '; ')"
    $base = "http://127.0.0.1:11434"
    $loaded = Invoke-RestMethod -Uri "$base/api/ps" -TimeoutSec 10
    foreach ($item in @($loaded.models)) {
        $vramGB = [math]::Round([double]$item.size_vram / 1GB, 2)
        Write-Host ("Loaded {0} | Context {1} | VRAM {2}GB" -f $item.name,$item.context_length,$vramGB)
    }
    # Only synthetic content is used; no workspace files or personal data are accessed.
    $payload = @{
        model = $Model
        prompt = "/no_think`nReply with exactly the single word OK. No explanation."
        stream = $false
        think = $false
        keep_alive = "3m"
        options = @{
            num_predict = 128
            temperature = 0
        }
    } | ConvertTo-Json -Depth 5
    Write-Host "Starting small read-only synthetic inference; this may be slow on CPU..."
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $r = Invoke-RestMethod -Method Post -Uri "$base/api/generate" -Body $payload -ContentType "application/json" -TimeoutSec $TimeoutSeconds
    $timer.Stop()
    $seconds = [math]::Round($timer.Elapsed.TotalSeconds, 2)
    $evalTokens = [int]$r.eval_count
    $evalNS = [double]$r.eval_duration
    $promptTokens = [int]$r.prompt_eval_count
    $tps = if ($evalNS -gt 0) { [math]::Round($evalTokens * 1000000000 / $evalNS, 2) } else { 0 }
    $promptEvalNS = [double]$r.prompt_eval_duration
    $promptTps = if ($promptEvalNS -gt 0) { [math]::Round($promptTokens * 1000000000 / $promptEvalNS, 2) } else { 0 }
    $answer = [string]$r.response
    $thinking = [string]$r.thinking
    Write-Host ("Synthetic response completed in {0}s | Prompt tokens {1} | Output tokens {2}" -f $seconds,$promptTokens,$evalTokens)
    Write-Host ("Prompt processing: {0} tokens/s | Output generation: {1} tokens/s" -f $promptTps,$tps)
    Write-Host ("Done reason: {0} | Thinking field length: {1} chars" -f $r.done_reason,$thinking.Length)
    if ($answer) {
        Write-Host ("Answer preview: {0}" -f $answer.Substring(0,[math]::Min(120,$answer.Length)))
    }
    $answerOk = ($answer.Trim().Trim('"') -ceq "OK")
    if (-not $answerOk) {
        Write-Warning "INSTRUCTION FAIL: Model did not return exactly OK. Even if generation is fast, agentic coding reliability remains unverified."
        if ($r.done_reason -eq "length") {
            Write-Warning "The reply reached num_predict=128 without following the instruction."
        }
    }
    $loadedNow = Invoke-RestMethod -Uri "$base/api/ps" -TimeoutSec 10
    foreach ($item in @($loadedNow.models)) {
        if (@($Model, (($Model -replace ":latest$","") + ":latest")) -contains $item.name) {
            Write-Host "Actual loaded context: $($item.context_length)"
        }
    }
    if ($tps -gt 0 -and $tps -lt 3) {
        Write-Warning "Local generation throughput is low. Codex agent requests may require several minutes. Consider a smaller model or GitHub-hosted automation."
    }
    if (-not $answerOk) { exit 2 }
    Write-Host "PASS: Synthetic instruction-following + local model inference. This is NOT proof of Codex agent performance."
    exit 0
} catch {
    Write-Error "Diagnostic failed: $_"
    exit 1
}
