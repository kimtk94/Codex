# Unified Harness (read-only staged rollout)

Stage: draft pull request. No production deployment or LIVE modifications.

The existing IS issue worker and GitHub five-minute schedule remain unchanged.
The existing CSS audit and Kalman deployment/test workflows remain unchanged.

## Stage 1: Safe aggregator

`scripts/unified_harness_briefing.py` reads four optional JSON snapshots:
`is_ckd.json`, `css.json`, `kalman.json`, `harness.json`.
All missing, stale, invalid, oversized, symlinked or future-dated input becomes UNKNOWN.
It does not invoke SSH, modify servers or GitHub Issues, send messages, or trade.
The workflow has contents:read only and publishes an Actions artifact.
Its daily UTC cron maps to 08:30 KST (GitHub schedules may be delayed).

Until sanitized snapshots are explicitly made available to the runner, all statuses
remain UNKNOWN. Never publish customer data, research subjects, trading keys, tokens,
or sensitive financial account information in public artifacts.

Expected input format:
```json
{"domain":"is_ckd","status":"REVIEW_REQUIRED",
 "summary":"Evidence audited; scientific review pending",
 "next_action":"Review interpretation","requires_approval":true,
 "evidence":["safe immutable reference"],
 "observed_at":"2026-10-18T00:00:00Z"}
```

## Stage 2: Not yet implemented

Audit SSH runtime with an existing approved, read-only GitHub Actions SSH workflow;
verify which state files can be exported without sensitive data. Do not change
existing systemd timers or scheduling and do not enable external actions.
Then implement minimal source adapters and tests, deploy on a separate approval.

Never couple this briefing to LIVE orders, strategies, trading credentials,
client email sending, SFDC writes, or data mutations.
