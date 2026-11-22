# Local AI Goal Loop — draft PR pilot

**Status:** GitHub-only controller CI available; the Windows laptop/Ollama end-to-end execution is not verified until the connected device is online. This module does not replace the existing automation_policy gates.

## Architecture

The local **Qwen2.5 Coder 3B / 16K** instance edits an exact allowlisted source file in a **new Git worktree**, using a Markdown goal document and a versioned JSON contract. It then runs an independent acceptance test, pushes only the agent feature branch, opens a **draft pull request**, and checks required GitHub CI jobs. No direct main writes, no PR merge, no mail/CRM/trade/deploy effects.

The controller runs at most 3 edits / 45 minutes per invocation and keeps a local checkpoint at \`~/.goal-loop/<goal_id>/latest.json\`. It can resume the same agent branch from that checkpoint after interruption, with a **12-attempt total ceiling**. State \`CI_PASS_REVIEW_REQUIRED\` means CI passed on the draft PR; it does not mean that the PR is merged.

## First activation (only after reviewing and merging the controller PR)

1. From PowerShell, go to \`C:\Users\KimTaeHoon\Projects\Codex\`.
2. Run \`git pull --ff-only origin main\`, then \`gh auth status\` and \`ollama list\`. Confirm that \`qwen25coder3b-16k\` is installed.
3. Verify the safe dry-run first:

   \`\`\`powershell
   python -m automation.goal_loop.controller --dry-run
   python -m unittest discover -s automation/goal_loop -p 'test_*.py' -v
   \`\`\`

4. Start the isolated pilot:

   \`\`\`powershell
   powershell -NoProfile -File .\automation\goal_loop\windows_worker.ps1
   \`\`\`

5. To continue automatically while the laptop and Ollama are running, launch the same script with \`-Loop\`. It checks for Ollama before acting and retries hourly within the total 12-attempt limit. For unattended relaunch after sign-in, create a Windows Task Scheduler task **under your own account** that invokes \`powershell.exe -NoProfile -File C:\Users\KimTaeHoon\Projects\Codex\automation\goal_loop\windows_worker.ps1 -Loop\` with “Run only when user is logged on.” This task is **not** installed automatically.

## What a goal document needs

- \`docs/...md\`: precise objective, input evidence, functional acceptance criteria, hold conditions
- \`automation/goal_loop/goals/...json\`: matching document path, **existing exact allowlisted files**, independent \`python -m unittest\` commands, required CI checks, iteration/time budgets
- Actual test modules remain **outside the editable file allowlist**.

The pilot uses \`docs/automation/goal-loop-pilot.md\` and \`automation/goal_loop/goals/pilot-status.json\`. The local code agent is intentionally restricted to \`pilot_target.py\`. The independent \`pilot_acceptance.py\` is expected to fail against the baseline and must pass **after** the local agent edits it; only \`agent/pilot-status-*\` PRs activate this acceptance job.

## Trust and limitations

- Goal documents, model responses, and prior checkpoints are **not trusted completion evidence**. Completion requires the current PR's required GitHub check results.
- GitHub-hosted runners cannot reach a private laptop Ollama instance. On laptop shutdown, AI code editing pauses; GitHub CI may still run independently.
- A code model may return invalid JSON, poor code, or no change. The worker then reports HOLD and never invents success.
- The GitHub main protection ruleset remains a separate administrator action. The \`main-write-guard\` check alone does **not** enforce branch protection.
- Additional projects should be onboarded individually after testing, with reviewed file allowlists, independent acceptance tests, bounded retries, and per-project security policies.
