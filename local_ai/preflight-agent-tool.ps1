# Local Codex tool-use preflight. Creates ONLY a disposable synthetic Git repository.
# Does NOT access real customer files, Drive, GitHub APIs, or modify an actual project.
# Manual opt-in test for an unverified local model. Can be stopped with Ctrl+C.
[CmdletBinding()]
param([string]$Model="qwen25coder3b-16k:latest")
$ErrorActionPreference="Stop"
try {
    if ($Model -notmatch '^[A-Za-z0-9_./:-]{1,100}$' -or $Model.EndsWith(":cloud",[StringComparison]::OrdinalIgnoreCase)) {
        throw "Only safe local model names supported."
    }
    foreach ($exe in @("git.exe","codex.cmd")) {
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) {
            throw "$exe not found on PATH."
        }
    }
    $testDir = Join-Path $env:TEMP ("codex-tool-preflight-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $testDir -Force | Out-Null
    & git.exe -C $testDir init -q
    if ($LASTEXITCODE -ne 0) { throw "Cannot create a disposable Git test repo." }
    $nonce = [guid]::NewGuid().ToString("N")
    $inputFile = Join-Path $testDir "marker.txt"
    "FILE_MARKER=$nonce" | Set-Content -LiteralPath $inputFile -Encoding Ascii
    $log = Join-Path $testDir "codex-events.jsonl"
    Write-Host "=== Safe local Codex tool invocation test ==="
    Write-Host "Scratch Git directory: $testDir"
    Write-Host "Model: $Model"
    Write-Host "Read-only sandbox; NO real repository or Google Drive access."
    Write-Host "This can be slow on CPU. Press Ctrl+C to cancel if it stalls."
    $prompt = "Read the actual local file marker.txt by using a real command/file tool. Report exactly the FILE_MARKER value found in it. Do not guess. Do not write any files. Do not use external services."
    # --json exposes actual tool events, so a model's text imitation of a tool call
    # cannot pass the verification. See official Codex CLI exec documentation.
    & codex.cmd exec --oss --local-provider ollama -m $Model -C $testDir --sandbox read-only --ephemeral --json -c 'model_context_window=16384' -c 'web_search="disabled"' $prompt 2>&1 |
        ForEach-Object { $_.ToString() } |
        Tee-Object -FilePath $log | Out-Null
    $exitCode = $LASTEXITCODE
    $events = @()
    foreach ($line in (Get-Content -LiteralPath $log -Encoding UTF8)) {
        try {
            $eventObject = $line | ConvertFrom-Json -ErrorAction Stop
            $events += $eventObject
        } catch {
            # CLI stderr can contain non-JSON diagnostics; ignore for event parsing.
        }
    }
    $ranRealCommand = @($events | Where-Object {
        $_.type -eq "item.completed" -and
        $_.item.type -eq "command_execution" -and
        $_.item.exit_code -eq 0 -and
        [string]$_.item.aggregated_output -match [regex]::Escape($nonce)
    }).Count -gt 0
    $finalGroundedAnswer = @($events | Where-Object {
        $_.type -eq "item.completed" -and
        $_.item.type -eq "agent_message" -and
        [string]$_.item.text -match [regex]::Escape($nonce)
    }).Count -gt 0
    Write-Host ("Real tool read marker: {0} | Final answer includes marker: {1} | Codex exit code: {2}" -f $ranRealCommand,$finalGroundedAnswer,$exitCode)
    Write-Host "Logs saved locally: $log"
    if ($exitCode -ne 0 -or -not $ranRealCommand -or -not $finalGroundedAnswer) {
        Write-Warning "FAIL/HOLD: Agent tool capability not established. Do NOT let the model edit/push/commit real code."
        Write-Warning "A fake call such as mcp__codex_tui.read_thread printed as plain text does not count."
        exit 2
    }
    Write-Host "PASS: Real command executed and the output matches a random synthetic file."
    Write-Host "This is a READ-ONLY test, NOT a full code-editing/PR safety validation."
    exit 0
} catch {
    Write-Error "Preflight could not complete: $_"
    exit 1
}
