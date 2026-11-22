# Local AI Goal Loop — draft PR pilot

**Status:** GitHub-only controller CI available; the Windows laptop/Ollama end-to-end execution is not verified until the connected device is online. This module does not replace the existing automation_policy gates.

## Architecture

The local **Qwen2.5 Coder 3B / 16K** instance edits an exact allowlisted source file in a **new Git worktree**, using a Markdown goal document and a versioned JSON contract. It syntax-compiles edited Python locally **without executing it**, pushes only the agent feature branch, opens a **draft pull request**, and executes independent acceptance tests only on unprivileged GitHub Actions runners. All accepted check runs must match the exact pushed commit SHA and GitHub Actions app. No direct main writes, no PR merge, no mail/CRM/trade/deploy effects.

The controller runs at most 3 edits / 45 minutes per invocation and keeps a local checkpoint at `~/.goal-loop/<goal_id>/latest.json`. It can resume the same agent branch from that checkpoint after interruption, with a **12-attempt total ceiling**. State `CI_PASS_REVIEW_REQUIRED` means CI passed on the draft PR; it does not mean that the PR is merged.

## First activation (only after reviewing and merging the controller PR)

1. From PowerShell, go to `C:\Users\KimTaeHoon\Projects\Codex`.
2. Run `git pull --ff-only origin main`, then `gh auth status` and `ollama list`. Confirm that `qwen25coder3b-16k` is installed.
3. Verify the safe dry-run first:

   ```powershell
   python -m automation.goal_loop.controller --dry-run
   python -m unittest discover -s automation/goal_loop -p 'test_*.py' -v
   ```

4. Start the isolated pilot:

   ```powershell
   powershell -NoProfile -File .\automation\goal_loop\windows_worker.ps1
   ```

5. To continue automatically while the laptop and Ollama are running, launch the same script with `-Loop`. It checks for Ollama before acting and retries hourly within the total 12-attempt limit. For unattended relaunch after sign-in, create a Windows Task Scheduler task **under your own account** that invokes `powershell.exe -NoProfile -File C:\Users\KimTaeHoon\Projects\Codex\automation\goal_loop\windows_worker.ps1 -Loop` with “Run only when user is logged on.” This task is **not** installed automatically.

## 선택적 7B 모델 전환 (기존 목표·체크포인트 보존)

이전 노트북 측정값은 RAM **16GB**, Qwen2.5-Coder 3B/16K **21.39 tokens/s**,
Qwen3 4B/16K CPU **6.58 tokens/s**입니다. 7B 모델은 직접 측정한 기록이
없습니다. 따라서 자동 설치·자동 모델 변경은 하지 않습니다. 용량은
다운로드 크기와 실행 메모리가 다르며, Windows RAM 사용량에 따라
실행 속도나 안정성이 달라질 수 있습니다.

모델 설치를 원하는 경우 PowerShell에서 한 번 실행:

```powershell
ollama pull qwen2.5-coder:7b
ollama list
$env:GOAL_LOOP_MODEL = "qwen2.5-coder:7b"
python -m automation.goal_loop.controller --dry-run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\automation\goal_loop\windows_worker.ps1"
```

`GOAL_LOOP_MODEL`을 설정하지 않으면 기존 `qwen25coder3b-16k`를 그대로 사용합니다.
7B는 **명시적으로 설치되어 있어야** 선택할 수 있으며, 미설치 상태에서는
모델을 다운로드하거나 기존 목표를 변경하는 대신 안전하게 HOLD로 중단합니다.
`$env:GOAL_LOOP_MODEL`은 현재 PowerShell 세션에만 적용되므로,
새 터미널에서는 다시 지정해야 합니다. 모델 변경으로 체크포인트의
목표 해시, 기존 PR, 전체 12회 시도 예산이 초기화되지 않습니다.

## What a goal document needs

- `docs/...md`: precise objective, input evidence, functional acceptance criteria, hold conditions
- `automation/goal_loop/goals/...json`: matching document path, **existing exact allowlisted files**, independent `python -m unittest` commands, required CI checks, iteration/time budgets
- Actual test modules remain **outside the editable file allowlist**. A test command listed in goal JSON is declarative only; the local controller never executes it. The CI workflow must contain the authoritative test command.

The pilot uses `docs/automation/goal-loop-pilot.md` and `automation/goal_loop/goals/pilot-status.json`. The local code agent is intentionally restricted to `pilot_target.py`. The independent `pilot_acceptance.py` is expected to fail against the baseline and must pass **after** the local agent edits it; only `agent/pilot-status-*` PRs activate this acceptance job.

## Trust and limitations

- Goal documents, model responses, and prior checkpoints are **not trusted completion evidence**. Completion requires the current PR's required GitHub check results.
- GitHub-hosted runners cannot reach a private laptop Ollama instance. On laptop shutdown, AI code editing pauses; GitHub CI may still run independently.
- A code model may return invalid JSON, poor code, or no change. The worker then reports HOLD and never invents success. AI-authored code **must not be run locally** under the user's Windows account; passing acceptance tests is permitted only in restricted PR CI. CI failures trigger a bounded next proposal; no production changes are allowed.
- Neither the local runner nor its Windows user account is a security sandbox. Agent output is only syntax-compiled locally; all Python execution is delegated to restricted CI. The GitHub main protection ruleset remains a separate administrator action. The `main-write-guard` check alone does **not** enforce branch protection.
- Additional projects should be onboarded individually after testing, with reviewed file allowlists, independent acceptance tests, bounded retries, and per-project security policies.
