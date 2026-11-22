# Local AI Goal Loop — draft PR pilot

**Status:** GitHub-only controller CI available; the Windows laptop/Ollama end-to-end execution is not verified until the connected device is online. This module does not replace the existing automation_policy gates.

## V2 — independent, review-first pilot (V1 remains exhausted)

**V1 outcome:** 12/12 attempts, AI-written draft PR #969, independent
\`pilot-acceptance\` failed. Do not delete
\`~/.goal-loop/pilot-status-normalizer/latest.json\`, force-merge #969, or
silently replenish that budget.

**V2 identity:** \`pilot-status-normalizer-v2\`, configured by
\`automation/goal_loop/goals/pilot-status-v2.json\` and documented in
\`docs/automation/goal-loop-pilot-v2.md\`. It has a **separate checkpoint**
\`~/.goal-loop/pilot-status-normalizer-v2/latest.json\` and an
independent \`pilot-acceptance-v2\` CI check. Its AI can edit only
\`pilot_target_v2.py\`; the independent acceptance test and security workflow
remain out of scope. The AST-only preflight rejects V1's top-level \`assert\`
regression **before Git push without importing the model-authored module**.
Two invalid proposals per invocation result in \`STATIC_QUALITY_HOLD\`.

GitHub Actions can verify controller safety and hand-authored fixtures, but
**cannot run your laptop's Ollama**. After this PR has passed CI and merged,
review and run **one single-shot** from Windows PowerShell:

\`\`\`powershell
cd C:\Users\KimTaeHoon\Projects\Codex
git switch main
git pull --ff-only origin main
python -m unittest discover -s automation/goal_loop -p "test_*.py" -v
python -m automation.goal_loop.controller --goal automation/goal_loop/goals/pilot-status-v2.json --dry-run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\automation\goal_loop\windows_worker.ps1" -Goal "automation/goal_loop/goals/pilot-status-v2.json"
\`\`\`

The worker's **default** remains the exhausted V1 goal. Always specify
\`-Goal ...pilot-status-v2.json\` for this distinct experiment. Do not pass
\`-Loop\` until an exact-head PR achieves
\`CI_PASS_REVIEW_REQUIRED\`. No automatic merge or production writes.

### Measured, optional local model comparison

The previous laptop baseline is 16GB RAM, about 21.39 tokens/s for
Qwen2.5-Coder 3B/16K, and about 6.58 tokens/s for Qwen3 4B/16K on CPU.
These measurements **do not prove 7B performance**. Before using V2's
attempt budget, manually compare both *locally installed* models without
executing model-generated code:

\`\`\`powershell
python -m automation.goal_loop.model_probe --model qwen25coder3b-16k
python -m automation.goal_loop.model_probe --model qwen2.5-coder:7b
\`\`\`

Each probe uses only a fixed synthetic prompt over localhost; outputs
latency, returned token rate (when supplied by Ollama), and a structured
mapping correctness score **not** the independent V2 code CI pass rate.
No install, model-derived code execution, token upload, file write or
checkpoint reset. Select the V2 model for the current terminal only if its
measured reliability and speed are acceptable:

\`\`\`powershell
$env:GOAL_LOOP_MODEL = "qwen2.5-coder:7b"
\`\`\`

GitHub Actions remains the sole authority for AI-authored code behavior
and \`pilot-acceptance-v2\`.

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

## Ollama 7B Timeout 진단 (기존 측정: RAM 16GB)

`LOCAL_OLLAMA_UNAVAILABLE:TimeoutError`는 Ollama 모델이 **200초 동안**
응답을 완료하지 못한 기존 컨트롤러 오류입니다. 서버에 연결되지 않았다는
증거는 아닙니다. 7B 선택 시 생성 요청 타임아웃을 **600초**로 늘리고,
선택한 모델과 제한 시간을 콘솔에 기록합니다. 3B의 기존 **200초**는 유지하며
사용자 측정값(3B 21.39 tok/s, Qwen3 4B CPU 6.58 tok/s)을 변경하지 않습니다.

PowerShell에서 아래를 확인한 후 1회 실행하십시오.

```powershell
ollama ps
ollama list
$env:GOAL_LOOP_MODEL = "qwen2.5-coder:7b"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\automation\goal_loop\windows_worker.ps1"
```

`ollama ps`에 **100% CPU**로 표시되거나 생성이 반복해서 타임아웃되면,
7B의 이 노트북 성능은 미검증이므로 3B로 돌아가거나 별도 성능 검증을
해야 합니다. 모델 설치와 RAM 업그레이드는 자동으로 시행하지 않습니다.

```powershell
Remove-Item Env:GOAL_LOOP_MODEL -ErrorAction SilentlyContinue
```

`9/12` 같은 이전 반복 횟수는 그대로 남습니다. 모델 전환 또는 HTTP
타임아웃 변경은 시도 횟수를 초기화하지 않으며, CI PASS가 아닌
`HOLD`에는 자동 병합이 허용되지 않습니다.

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
