# Local AI goal-loop pilot — acceptance contract

## Goal

Demonstrate **document → local Qwen code edit → restricted GitHub PR CI tests → review-required completion** without modifying live CRM, payment, trading, research, or deployment workflows.

## Allowed implementation target

Only `automation/goal_loop/pilot_target.py` may be changed by the AI.

## Functional acceptance

The function `normalize_status(value)` must map:

- `pass`, `passed`, `ok`, `done`, `success` (case-insensitive, whitespace ignored) → `PASS`
- `fail`, `failed`, `error` → `FAIL`
- Every other value, including `None`, empty string, numbers, and mappings → `HOLD`

## Completion evidence

1. GitHub Actions executes `automation.goal_loop.pilot_acceptance` against the exact AI-generated PR commit with no user secrets or local machine credentials.
2. The specific draft pull request has **all** named GitHub checks in the JSON goal file passing.
3. The controller records the PR URL, iteration number, immutable commit SHA, and required CI check conclusions.
4. State is `CI_PASS_REVIEW_REQUIRED`. This is **not merged** and is **not a production deployment**.

## Hold and safety

- At most three iterations and 45 minutes per invocation.
- No test, goal, policy, security, workflow, secrets, or non-allowlisted edits.
- Never execute model-authored source or shell snippets on the laptop. Only compile syntax locally; execute generated Python only in restricted GitHub Actions with no checked-out credentials.
- Never auto-merge, auto-deploy, send email, create CRM records, or trade.
- If the laptop/Ollama connection is unavailable, mark `HOLD` rather than pretending work continued.
- This pilot intentionally starts with an incomplete implementation. Only pilot acceptance tests in the `agent/pilot-status-*` pull requests are release-blocking. The general controller contract CI is independently testable before the laptop comes online.
