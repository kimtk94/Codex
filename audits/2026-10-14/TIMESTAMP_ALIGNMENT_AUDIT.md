# Broker / Neon timestamp alignment gate (2026-10-14)

Status: OFFLINE_IMPLEMENTED / CI_PASS / BROKER_UNVERIFIED

## Why
Identical LRCX quantities from observations at different times must not yield a holdings-match verdict. Before this change, the offline reconciler checked timestamp format but not freshness or alignment.

## Implemented controls (audit branch only)
- Broker capture time age <= 300 seconds; future skew <= 30 seconds, require timezone-aware ISO 8601.
- Mirror evidence requires explicit `mirror_as_of` and age <= 300 seconds; future skew <= 30 seconds.
- Difference between broker capture and mirror timestamp <= 300 seconds; threshold configurable.
- Invalid, missing or NaN/Infinity values fail closed.
- Actual broker open orders or unresolved SUBMITTED records prevent any full lifecycle success verdict; `HOLDINGS_MATCH` describes holdings alone, not trading correctness.
- Historical replay accepts a caller-supplied pinned `now`; ordinary runtime checks use UTC clock automatically.
- No trading APIs, secrets, SSH, token caches or production databases used by these tests.

## Verification
Final audit branch commit: 57657d29d70dd3aa78ac6f2b7b59bf997ea30f68
GitHub Actions run: 38568069142, completed/success, 45 tests, no failures.
https://github.com/kimtk94/Codex/actions/runs/38568069142

## Caveats and next evidence
- An `updated_at` field may describe mirror synchronization, **not** when the broker observed the holding. Do not substitute it for proven broker capture time without auditing provenance.
- Actual Toss holdings, outstanding orders and the 21 SUBMITTED lifecycle outcomes remain UNKNOWN; no live broker snapshot was acquired.
- Thresholds (300s and 30s) are provisional engineering choices and should be calibrated against observed pipeline SLAs, without weakening fail-closed behavior.
- The separate independent GET prototype returns raw broker payloads. No tested, schema-specific normalization into the sanitized snapshot contract has yet been established.
- Do not deploy, alter LIVE orders, or update Neon Production as part of this research audit.
