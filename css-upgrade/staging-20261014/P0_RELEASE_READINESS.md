# CSS P0 Release Readiness (offline evidence gate)

**Status:** STAGING ONLY / no production deployment. This adds a small report-only readiness evaluator to the existing G12/G16 draft upgrade. It does **not** import/run operational CSS or the Mail Collector.

## Usage

```bash
python3 css_release_readiness.py --synthetic-demo --expect-blocked
python3 -m unittest -v test_css_release_readiness.py
```

A future **aggregate-only** manifest may contain `schema_version: 1`, `environment: staging`, and `checks`. Each of 11 required checks supplies `status` and `observed_at_utc` (UTC ISO8601). No customer identities, mailbox content, tokens, raw DBs or project records belong in these manifests. Unknown/missing/partial/stale evidence is always a blocker. Historical passing tests do not by themselves prove today's runtime health.

The evaluator deliberately distinguishes the synthetic tests from full CSS E2E; G16 sink isolation, G12 entire-engine canary, live runtime status and explicit approval are separate mandatory requirements.

An all-PASS manifest results in `READY_FOR_HUMAN_REVIEW` **only**. `production_deploy_authorized` is always `false`. It performs **no deployment** and no Google Sheets, SQLite, mail, CRM, backup, cron or server writes. Operator approval and a rehearsed release/rollback remain out of band.

Reference: [G12 recovery contract](G12_SHEETS_SQLITE_RECOVERY_CONTRACT_20261017.md), [G16 boundary probe](G16_BOUNDARY_PROBE.md), [release gates](RELEASE_GATES.md).
