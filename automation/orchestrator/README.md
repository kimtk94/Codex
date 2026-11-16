# Autonomous Next — sales verification MVP

One trigger executes up to five **strictly offline/synthetic** validation stages in order and records a durable checkpoint. This replaces repeated chat "다음" prompts *for these five tests only*. It does **not** run an LLM, repair code, write to Salesforce, update Feishu, send emails, merge PRs or certify that live sources are current.

## Existing validation suites used
1. `automation_policy` protected-action tests.
2. `automation/sfdc/test_oppo_quote_popular_patterns.py` (synthetic).
3. `automation/sfdc/test_quote_2026_krw_price_reuse.py` (synthetic; KRW 2026).
4. `integrations/feishu/test_*.py` (offline; credentials blank).
5. `automation/progress/test_gate_evaluator.py` (evidence policy).

The runner uses a hard-coded command allowlist, `subprocess.run` with no shell, removed GitHub API credentials for child processes and a 240-second timeout per stage. The workflow has a 25-minute timeout. A failure stops dependent stages, allows at most three total attempts, and then blocks the queue until reset or new code. There is no `set -e` in the runner.

## How to run

After the PR is reviewed and merged, navigate to **Actions → Autonomous Next - Sales Verification (No Save) → Run workflow**. Choose `max_steps` (1–10, default 5); `reset=true` restarts the chain. The workflow also schedules itself daily at 21:45 KST and executes when relevant files are pushed to main.

- [Checkpoint issue #794](https://github.com/kimtk94/Codex/issues/794): mutable state. Do not delete the `AUTONEXT_STATE` markers. Write human notes outside them.
- Workflow run summary: completed/remaining stages and next blocked stage.
- `autonomous-next-sales-receipt` artifact: `state.json` and `summary.md`, retained for 30 days.

The checkpoint is reused only if the plan fingerprint and commit SHA match and it is less than 24 hours old. Otherwise a fresh synthetic verification cycle begins. **Issue and artifact records are test evidence, not acceptance of source-to-sink data freshness.**

## Test locally

```bash
python3 -m unittest discover -s automation/orchestrator -p 'test_*.py' -v
python3 automation/orchestrator/runner.py --dry-run --max-steps 5 --out /tmp/autonext-plan
```

The dry-run never calls GitHub or any external system. Real execution requires the workflow's `GITHUB_TOKEN` (`issues:write`) and existing issue #794; there is no need to store a PAT or OpenAI API key.

## Next iteration — requires separate approval

Link approved read-only source/sink freshness probes and enforce separate `PASS`, `NO_NEW_DATA`, `STALE`, `SOURCE_UNAVAILABLE`, `SINK_LAG` and `BLOCK` results with original timestamps and reconciliation counts. A code-fix agent or API-based AI planner, if later connected, must be restricted to PRs and CI, and must not turn `TEST_CHAIN_PASS` into an operational acceptance claim. SFDC Save, customer email send, deployment, revenue writes and PR auto-merge remain approval-gated.
