# Autonomous Next — sales verification MVP

One trigger executes up to six **strictly offline/synthetic** validation stages in order and records a durable checkpoint. This replaces repeated chat "다음" prompts *for these six tests only*. It does **not** run an LLM, repair code, write to Salesforce, update Feishu, send emails, merge PRs or certify that live sources are current.

## Existing validation suites used
1. `automation_policy` protected-action tests.
2. `automation/sfdc/test_oppo_quote_popular_patterns.py` (synthetic).
3. `automation/sfdc/test_quote_2026_krw_price_reuse.py` (synthetic; KRW 2026).
4. `integrations/feishu/test_*.py` (offline; credentials blank).
5. `automation/ops/test_css_freshness_policy.py` (offline 9-domain/18-crosscheck freshness contract; not a live data probe).
6. `automation/progress/test_gate_evaluator.py` (evidence policy).

The runner uses a hard-coded command allowlist, `subprocess.run` with no shell, a **minimal environment allowlist** (no inherited GitHub tokens, QQ credentials, Feishu secrets, Google service accounts or arbitrary external environment variables), and a 240-second timeout per stage. Test stdout/stderr is captured but **never persisted** in the checkpoint, public issue, CI summary, or artifact. Failures are recorded only as fixed `OFFLINE_SUITE_NONZERO_EXIT`, `OFFLINE_SUITE_TIMED_OUT` or `OFFLINE_SUITE_FAILED_UNCLASSIFIED` codes. The separately permission-scoped GitHub failure inspection job is the only component that classifies historic CI failure logs, without retaining raw text. The workflow has a 25-minute timeout. A failure stops dependent stages, allows at most three total attempts, and then blocks the queue until reset or new code. There is no `set -e` in the runner.

## How to run

After the PR is reviewed and merged, navigate to **Actions → Autonomous Next - Sales Verification (No Save) → Run workflow**. Choose `max_steps` (1–10, default 6); `reset=true` restarts the chain. The workflow also schedules itself daily at 21:45 KST and executes when relevant files are pushed to main.

- [Checkpoint issue #794](https://github.com/kimtk94/Codex/issues/794): mutable state and operator pause control. **Check `PAUSE_AUTONEXT` to stop before the next stage; uncheck it to resume at the next scheduled/manual run.** A currently running test will finish first (up to 240 seconds). Leave exactly one pause checkbox and do not delete the `AUTONEXT_STATE` markers. Write human notes outside the markers; the runner reloads the latest issue body before each state write so intervening notes are preserved.
- Workflow run summary: completed/remaining stages and next blocked stage.
- `autonomous-next-sales-receipt` artifact: `state.json` and `summary.md`, retained for 30 days.

If the pause checkbox is missing or ambiguous, operation fails closed instead of running more tests. Pause does not bypass prior failures, and `reset=true` does not override the checkbox. The checkpoint is reused only if the plan fingerprint and commit SHA match and it is less than 24 hours old. Otherwise a fresh synthetic verification cycle begins. **Issue and artifact records are test evidence, not acceptance of source-to-sink data freshness.**

## Test locally

```bash
python3 -m unittest discover -s automation/orchestrator -p 'test_*.py' -v
python3 automation/orchestrator/runner.py --dry-run --max-steps 6 --out /tmp/autonext-plan
```

The dry-run never calls GitHub or any external system. PR CI also uses `--offline-run` to execute all six pre-approved offline suites **without** GitHub issue reads/writes; this is distinct from the mocked unit tests. Production checkpointed execution requires the workflow's `GITHUB_TOKEN` (`issues:write`) and existing issue #794; there is no need to store a PAT or OpenAI API key.

## Automatic selection of next investigation (read-only)

The `next-review` GitHub Actions job now polls the **nine existing main-branch GitHub workflow histories** (GitHub Actions read permission only). It creates a sanitized `autonomous-next-readonly-priority` artifact and prints the top candidate in the run summary. No Salesforce, Feishu, QQ, OpenAI API, web deployment, customer amounts, or mail credentials are used.

**Priority order by evidence state:** latest CI failure → GitHub run API unavailable → unknown conclusion → no main-branch run → cancelled/skipped → in progress → CI success without source verification. Ties follow the nine-domain operations policy order. A pending latest run never inherits a previous successful status. Missing or blocked GitHub run visibility is reported as `CI_API_UNAVAILABLE`, **not** as `NO_NEW_DATA` or `PASS`.

The queue recommends `INSPECT_FAILURE_LOGS_READ_ONLY`, `CHECK_WORKFLOW_TRIGGER_AND_BRANCH`, or `COLLECT_ORIGINAL_SOURCE_AND_SINK_READBACK`; no arbitrary workflow dispatches, code edits, writes, or PR merges occur. Even with nine successful CI runs, **business_source_sink_verification is always NOT_VERIFIED** until separate authenticated original-source and sink-readback audits are implemented.

Run locally: `python3 automation/orchestrator/priority.py --out /tmp/autonext-priority.json`. GitHub Actions supplies a read-only ephemeral `GITHUB_TOKEN`. Without API access, results fail closed to an unavailable state.

## Monthly Revenue: read-only mirror parity and snapshot age

The `revenue-mirror-evidence` job (main push, daily schedule or manual execution; **not PR**) uses an existing scoped Google Sheets service account to read only `BI Revenue Net VAT Monthly`, `BI Revenue Lifecycle Monthly`, and `Revenue Source Authority`. It invokes the existing `monthly_revenue_canonical.evidence_rows` 3-way consistency policy and separately checks all four monthly verification/snapshot timestamps.

A 48-hour age is an **investigation threshold for the mirror timestamp**, not a source-system cadence. `MIRROR_3WAY_PARITY_AGED` means the internally reconciled snapshot is old, NOT that no new invoices exist and NOT a proven live-source failure. `MIRROR_3WAY_PARITY_RECENT` means only an internally consistent recent mirror. A mismatch, unavailable service account, missing month, or malformed timestamp fails closed with sanitized status `MIRROR_UNAVAILABLE_OR_MISMATCH`. The full amount and customer identifiers never enter the public CI artifact.

Both outcomes keep `business_source_sink_verification = NOT_VERIFIED`: original QQ Tax Invoice messages, live Feishu Base readback and bank payments are **not** accessed by this job. Those require independent authenticated probes and an explicit parity review. No Feishu write token or Salesforce credentials are provided to the job.

## Evidence-aware prioritization of the next read-only investigation

The `next-review` job waits for the `revenue-mirror-evidence` job on main, retrieves its sanitized receipt from the **same workflow run**, and ranks the nine GitHub workflow signals alongside the separate Revenue mirror signal. PRs do not have access to private Sheets credentials or mirror artifacts. If the mirror job fails or does not upload an artifact, the recommendation becomes `MIRROR_RECEIPT_MISSING` (never `PASS` or `NO_NEW_DATA`).

Revenue mirror evidence states are `MIRROR_3WAY_PARITY_AGED`, `MIRROR_3WAY_PARITY_RECENT`, `MIRROR_UNAVAILABLE_OR_MISMATCH`; malformed/untrusted artifacts become `MIRROR_RECEIPT_INVALID`. A historical Revenue CI failure is **retained as CI_FAILED**, even when a newer three-way mirror is internally consistent; the selected next action changes to comparing the old failure, newer mirror, and independently authenticated original/readback evidence. An aged or unavailable mirror is raised to the top for investigation.

This mechanism chooses **which audit to investigate next**, not which code to modify or which business records to write. No result can certify original QQ invoice coverage, Feishu Base delivery, or paid revenue. The next-review job only needs read access to GitHub Actions artifacts and GitHub workflow metadata; Salesforce, QQ, Feishu tokens are not available to this job.

## Reuse authenticated QQ/Feishu source-probe evidence (no new business credentials)

The new `original-probe-evidence` job reads the **latest main-branch** run of the already-scheduled `css-live-freshness-evidence.yml` and retrieves only its existing `css-authenticated-original-probes` JSON artifact. It uses an ephemeral GitHub read-only token; it does not connect to QQ/Feishu directly, and no private credentials, mail content, customer IDs or payment amounts are uploaded.

The evidence parser enforces bounded artifact sizes, a 12-hour review window (not a source refresh cadence), canonical run identity, a limited status schema, exact scope markers and `domain_business_pass = false`. Cross-host artifact redirects drop the GitHub bearer token. Failure to retrieve a recent, verified artifact yields explicit `SOURCE_AUDIT_NOT_FOUND`, `SOURCE_AUDIT_STALE`, `SOURCE_AUDIT_ARTIFACT_MISSING`, `SOURCE_AUDIT_INVALID`, or `SOURCE_AUDIT_API_UNAVAILABLE` and **never** `NO_NEW_DATA` or business `PASS`.

This is narrow evidence of:
- Original QQ IMAP **UID set** vs local staging: recent 3-day, 60-day and historical missing UID signals. **Not MIME/body or Tax Invoice amount verification.**
- Original Feishu **dated Sheets** vs Google projection consistency. **Not Feishu Base KPI write/readback, eTax issuance, SFDC Save or paid-invoice verification.**

Main-branch next-review automatically waits for both Revenue mirror and the authenticated source-probe receipt, then combines them with nine-domain CI signals. Missing receipts cause read-only investigation, never write execution. PR validation excludes all authentication and uses synthetic tests only.

## Execute one safe investigation automatically (read-only)

A new `next-investigation` GitHub Actions job reads the same-run `autonomous-next-readonly-priority` receipt. On main only, it performs **at most one** selected `INSPECT_FAILURE_LOGS_READ_ONLY` investigation: it retrieves the failed run's GitHub jobs and inspects **at most three failed job logs** using the ephemeral Actions read-only token. The special recommendation `COMPARE_FAILED_REVENUE_CI_WITH_RECENT_MIRROR_AND_ORIGINALS` permits the **failed CI log portion only**, not a comparison against the actual QQ originals.

Only fixed known diagnostic codes, validated GitHub run URLs, and counts are written to the `autonomous-next-next-investigation` artifact; raw log text, invoice amounts, customer identifiers, email addresses and credentials are never persisted. All unknown failures remain `FAILED_JOB_UNCLASSIFIED`, and missing log access remains `FAILED_JOB_LOG_UNAVAILABLE`. The GitHub bearer token is removed on redirects to archive/log storage; log downloads are capped at 2 MB.

This implementation is **not** an autonomous code-editing agent. It does not schedule other workflows, retry failed jobs, bypass source/sink gates, push commits, merge PRs or touch customer systems. If the selected action is not a supported log audit, the job returns `NOT_APPLICABLE` without fetching any logs. It is disabled for PR events; PR unit tests use only mock logs.

## Next iteration — requires separate approval

Link approved read-only source/sink freshness probes and enforce separate `PASS`, `NO_NEW_DATA`, `STALE`, `SOURCE_UNAVAILABLE`, `SINK_LAG` and `BLOCK` results with original timestamps and reconciliation counts. A code-fix agent or API-based AI planner, if later connected, must be restricted to PRs and CI, and must not turn `TEST_CHAIN_PASS` into an operational acceptance claim. SFDC Save, customer email send, deployment, revenue writes and PR auto-merge remain approval-gated.
