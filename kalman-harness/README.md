# Kalman Integrated Harness v1 — read-only

Created: 2026-10-16
Branch: harness/kalman-control-v1-20261016 (based on audit/kalman-control-20261014)
Release: RESEARCH_ONLY / PRODUCTION_HOLD. No merge, deployment, or LIVE config change authorized.

## Implemented

- All eight workstreams: 00 Control; 01 US LIVE; 02 US strategy; 03 Crypto Grid; 04 Crypto Regime/futures; 05 Data freshness; 06 Harness/AI; 07 Vercel/Neon.
- Python standard-library runner uses GET-only GitHub metadata endpoints for two explicit allowlisted workflow files and a fixed repo.
- Workflow completion, conclusion, UTC time, and 48-hour CI age gate are classified as SUCCESS/FAILURE/STALE/IN_PROGRESS/NO_RUN/UNAVAILABLE.
- Machine and readable outputs: kalman-harness/out/status.json and STATUS.md, containing provenance, controls, P0–P2 priorities and the next actions.
- 15 regression tests, no-network mode, local fixtures, and a GitHub Actions workflow with read-only permissions and 30-day artifact retention.
- The 6-hour schedule is defined but **will not run until the workflow exists on the default branch**. Feature-branch push testing is available.

## Local commands

    python3 -m unittest discover -s kalman-harness/tests -p 'test_*.py' -v
    python3 kalman-harness/harness_runner.py --no-network
    python3 kalman-harness/harness_runner.py

No server interaction; the last command queries GitHub workflow metadata only. GitHub Actions uses a limited GITHUB_TOKEN.

## Historical audit findings — not fresh/live evidence

- 2026-10-15 audit: 230 offline/unittest methods passed including 15 isolated PostgreSQL methods and 8 synthetic demo tests; 17 additional loopback HTTP scenarios also passed.
- Five historical multi-entry net-return overstatements remained unresolved in Production.
- Actual LIVE broker orders, positions, server runtime SHA and production HTTP responses were not attested.
- Current production web routing MAIN -> shared US/KR consumers was mapped, while main Git link pointed to an unrelated research repo.
- Prior inspected staging did not have SSO/password protection; DEMO ONLY source was NOT deployed.
- Historical CRYPTO/GLOBAL dataset READY vs TTL freshness conflict remains under investigation.

Primary evidence reports:
- audits/2026-10-15/LOCAL_HTTP_AND_DEMO_ONLY_STAGING_GATE_20261015.md
- audits/2026-10-15/VERCEL_ACTUAL_ALIAS_DEPENDENCY_P1_GATE.md
- audits/2026-10-14/README.md

## Next stages and acceptance

P0 — Workstreams 00 and 01: authorized server + broker GET-only provenance; reconcile real holdings, open orders and event records without account side effects.

P0 — Workstream 07: repair incorrect historical returns from proven fee/order evidence; prove MAIN/US/KR alias mapping, active source and staging protection before planning any release.

P1 — Workstream 05: correct TTL producer; READY and FRESH must never be synonymous, unknown timestamps must stay UNKNOWN, impossible timestamps INVALID.

P1 — Workstream 06: incorporate timestamped, sanitized server/Neon/Vercel read-only evidence with separate retention, expiration and redaction contracts. Do not treat a green offline test as live proof.

P2 — Workstreams 02/03/04: OOS walk-forward and longer regime histories; account for fee, slippage, fill realism, drawdown, turnover and leverage/liquidation risk.

P2 — Workstream 00: after Drive authorization/policy, archive redacted reports and content hashes in Drive/Kalman_Diagnostics.

## Non-negotiable boundary

No trading endpoints; no account/production SQL writes; no SSH or broker connections in this GitHub workflow; no Vercel deployment/alias update; no credential or position payloads in public artifacts; no automatic merge or unblock of P0 issues. All harness reports say production_release_authorized=false and live_runtime_verified=false.

Phase A completion: green tests + artifact containing all eight rows, accurate timestamp/freshness states, and immutable release-false guarantees.

Phase B completion: fresh real-world read-only evidence across server, broker, database, data quality and active website, followed by reviewed workstream clearance.

Phase C: production change only through separate explicitly approved release gate, including rollback and impact validation.
