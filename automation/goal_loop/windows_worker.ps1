# Optional Windows local worker. No registry, service or task installation.
# Run a single shot while V2 acceptance remains unverified; do NOT use -Loop.
param(
    [switch]$Loop,
    [string]$Goal = "automation/goal_loop/goals/pilot-status.json"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

# Keep V1's exhausted checkpoint immutable; use the goal ID for V2.
$approvedGoals = @(
    "automation/goal_loop/goals/pilot-status.json",
    "automation/goal_loop/goals/pilot-status-v2.json"
)
$normalizedGoal = $Goal.Replace([char]92, [char]47)
if ($normalizedGoal -notin $approvedGoals) {
    throw "Goal path is not allowlisted for this pilot."
}
$goalFile = Join-Path $repo $normalizedGoal
if (-not (Test-Path -LiteralPath $goalFile -PathType Leaf)) {
    throw "Missing goal definition: $normalizedGoal"
}
$goalMetadata = Get-Content -LiteralPath $goalFile -Raw | ConvertFrom-Json
$goalId = [string]$goalMetadata.goal_id
if ($goalId -notmatch '^[a-z0-9][a-z0-9-]{2,48}$') {
    throw "Invalid goal ID."
}
$checkpointDir = Join-Path (Join-Path $HOME ".goal-loop") $goalId
$checkpoint = Join-Path $checkpointDir "latest.json"

# Shared mutex prevents two pilots from writing to the same Git repository.
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
            & python -m automation.goal_loop.controller --goal $normalizedGoal
            Write-Host "Controller exit code: $LASTEXITCODE"
        }
        if (Test-Path -LiteralPath $checkpoint -PathType Leaf) {
            try {
                $state = Get-Content -LiteralPath $checkpoint -Raw | ConvertFrom-Json
                $attemptCount = 0
                if ($null -ne $state.evidence.iterations) {
                    $attemptCount = @($state.evidence.iterations).Count
                }
                $latestCI = if ($state.evidence.last_ci) { $state.evidence.last_ci.verdict } else { "none" }
                Write-Host "Goal summary: goal=$goalId; state=$($state.state); attempts=$attemptCount/12; CI=$latestCI; PR=$($state.evidence.pr_url)"
                if ($state.evidence.reason) {
                    Write-Host "Hold reason: $($state.evidence.reason)"
                }
                if ($attemptCount -ge 12 -or $state.state -in @(
                    "CI_PASS_REVIEW_REQUIRED", "HOLD_SECURITY_GATE",
                    "TOTAL_ITERATION_BUDGET_EXHAUSTED", "NO_PROGRESS_HOLD",
                    "STATIC_QUALITY_HOLD", "CI_HEAD_ADVANCED_HOLD"
                )) {
                    Write-Host "Worker stopped at: $($state.state)"
                    break
                }
                if ($state.evidence.reason -match "INVALID_|UNSAFE_|FORBIDDEN_|CHECKPOINT_|OUT_OF_SCOPE|MISSING_CI_GATES|MODEL_OVERRIDE_|SELECTED_LOCAL_MODEL_NOT_INSTALLED|TOTAL_ITERATION_") {
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
