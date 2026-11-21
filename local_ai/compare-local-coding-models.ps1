# Compare two local Ollama models on the user's Windows laptop using synthetic prompts.
# Optional 1.9GB candidate download is explicit. No cloud inference; no GitHub/Drive access.
# This is a screening benchmark; it does NOT validate autonomous code editing.
[CmdletBinding()]
param(
    [switch]$InstallCandidate,
    [ValidateRange(8192,32768)][int]$ContextTokens = 16384,
    [ValidateRange(30,600)][int]$TimeoutSeconds = 180
)
$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:11434"
$baseline = "qwen3-codex16k:latest"
$candidate = "qwen25coder3b-16k"
function Have-Model([string]$tag) {
    $data = Invoke-RestMethod -Uri "$base/api/tags" -TimeoutSec 10
    $names = @($data.models | ForEach-Object { [string]$_.name })
    return (($names -contains $tag) -or ($names -contains ($tag + ":latest")))
}
function Benchmark([string]$model,[string]$name) {
    $cases = @(
        @{ name="exact_word"; prompt="Reply with only the word OK, without punctuation or explanation."; expected="OK" },
        @{ name="math"; prompt="Reply with only the number 42: What is six multiplied by seven?"; expected="42" }
    )
    $result = @()
    foreach ($test in $cases) {
        $body = @{
            model = $model
            prompt = $test.prompt
            think = $false
            stream = $false
            keep_alive = "3m"
            options = @{
                temperature = 0
                num_ctx = $ContextTokens
                num_predict = 128
            }
        } | ConvertTo-Json -Depth 6
        $timer = [Diagnostics.Stopwatch]::StartNew()
        try {
            $resp = Invoke-RestMethod -Uri "$base/api/generate" -Method Post -ContentType "application/json" -Body $body -TimeoutSec $TimeoutSeconds
            $timer.Stop()
            $answer = [string]$resp.response
            $answer = $answer.Trim()
            $answerOk = ($answer -ceq [string]$test.expected)
            $promptSpeed = if ([double]$resp.prompt_eval_duration -gt 0) {
                [math]::Round([double]$resp.prompt_eval_count * 1e9 / [double]$resp.prompt_eval_duration,2)
            } else { 0 }
            $outputSpeed = if ([double]$resp.eval_duration -gt 0) {
                [math]::Round([double]$resp.eval_count * 1e9 / [double]$resp.eval_duration,2)
            } else { 0 }
            $result += [pscustomobject]@{
                Model=$name
                Test=$test.name
                Pass=$answerOk
                Completed=([string]$resp.done_reason -ne "length")
                Seconds=[math]::Round($timer.Elapsed.TotalSeconds,2)
                PromptTPS=$promptSpeed
                OutputTPS=$outputSpeed
                AnswerPreview=$answer.Substring(0,[math]::Min(80,$answer.Length))
            }
        } catch {
            $timer.Stop()
            $result += [pscustomobject]@{
                Model=$name; Test=$test.name; Pass=$false; Completed=$false
                Seconds=[math]::Round($timer.Elapsed.TotalSeconds,2)
                PromptTPS=0; OutputTPS=0; AnswerPreview="ERROR: $($_.Exception.Message)"
            }
        }
    }
    return $result
}
try {
    if (-not (Get-Command ollama.exe -ErrorAction SilentlyContinue)) { throw "Ollama.exe is missing." }
    if (-not (Have-Model $baseline)) {
        throw "Baseline $baseline was not found. Run Fix-Codex-4096.cmd first."
    }
    $os = Get-CimInstance Win32_OperatingSystem
    $free = [math]::Round([double]$os.FreePhysicalMemory / 1MB,2)
    $gpu = @(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name)
    Write-Host ("System free RAM {0}GB; GPU: {1}" -f $free,($gpu -join "; "))
    if (-not (Have-Model $candidate)) {
        if (-not $InstallCandidate) {
            Write-Host "Candidate missing. Download is ~1.9GB. Run Compare-Local-Coding-Models.cmd to install candidate."
            exit 2
        }
        Write-Host "Downloading official qwen2.5-coder:3b (~1.9GB)."
        & ollama.exe pull qwen2.5-coder:3b
        if ($LASTEXITCODE -ne 0) { throw "Candidate base download failed." }
        $mf = Join-Path $env:TEMP "Modelfile.qwen25coder3b-16k"
        ("FROM qwen2.5-coder:3b" + [Environment]::NewLine + "PARAMETER num_ctx $ContextTokens" + [Environment]::NewLine) |
            Set-Content -LiteralPath $mf -Encoding Ascii
        & ollama.exe create $candidate -f $mf
        if ($LASTEXITCODE -ne 0) { throw "Custom candidate creation failed." }
    }
    Write-Host "Running two synthetic prompts on each model. No private inputs."
    $results = @()
    $results += @(Benchmark $baseline "qwen3-4b")
    $results += @(Benchmark ($candidate + ":latest") "qwen25coder-3b")
    $results | Format-Table Model,Test,Pass,Completed,Seconds,PromptTPS,OutputTPS,AnswerPreview -AutoSize | Out-Host
    $summary = $results | Group-Object Model | ForEach-Object {
        $ok = @($_.Group | Where-Object { $_.Pass -and $_.Completed }).Count
        "{0}: {1}/{2} synthetic checks passed" -f $_.Name,$ok,@($_.Group).Count
    }
    Write-Host ($summary -join " | ")
    Write-Host "No Codex launcher has been switched. Review these results before any agent use."
    if (@($results | Where-Object { $_.Model -eq "qwen25coder-3b" -and (!$_.Pass -or !$_.Completed) }).Count -gt 0) {
        Write-Warning "Candidate failed at least one trivial instruction test; do not promote it automatically."
        exit 2
    }
    Write-Host "Candidate passed basic prompts. Real Codex tool-use remains unverified."
    exit 0
} catch {
    Write-Error "Local model comparison failed: $_"
    exit 1
}
