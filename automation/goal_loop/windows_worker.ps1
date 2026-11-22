# Optional Windows local worker. No registry, service, or task installation effects.
# Schedule with Windows Task Scheduler after review; or launch manually with -Loop.
param(
    [switch]$Loop,
    [string]$Goal = "automation/goal_loop/goals/pilot-status.json"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo
$checkpoint = Join-Path $HOME ".goal-loop\pilot-status-normalizer\latest.json"
$mutex = New-Object System.Threading.Mutex($false, "Local\Kimtk94GoalLoopWorker")
$lock = $false
try {
    $lock = $mutex.WaitOne(0)
    if (-not $lock) {
        Write-Host "Another goal-loop worker is already running."
        exit 0
    }
    do {
        $ready = $false
        try {
            $r = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
            $ready = $null -ne $r.models
        } catch {
            Write-Host "Local Ollama is offline; no Git changes attempted."
        }
        if ($ready) {
            & python -m automation.goal_loop.controller --goal $Goal
            Write-Host "Controller exit code: $LASTEXITCODE"
        }
        if (Test-Path $checkpoint) {
            try {
                $state = Get-Content -Raw $checkpoint | ConvertFrom-Json
                if ($state.state -in @("CI_PASS_REVIEW_REQUIRED", "HOLD_SECURITY_GATE", "TOTAL_ITERATION_BUDGET_EXHAUSTED", "NO_PROGRESS_HOLD", "CI_HEAD_ADVANCED_HOLD")) {
                    Write-Host "Worker stopped at: $($state.state)"
                    break
                }
                if ($state.evidence.reason -match "INVALID_|UNSAFE_|FORBIDDEN_|CHECKPOINT_|OUT_OF_SCOPE|MISSING_CI_GATES") {
                    Write-Host "Permanent policy hold; manual review required."
                    break
                }
            } catch {
                Write-Host "Checkpoint unreadable: manual review required."
                break
            }
        }
        if ($Loop) {
            Start-Sleep -Seconds 3600
        }
    } while ($Loop)
} finally {
    if ($lock) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
