# Toss broker GET safety audit (2026-10-14)
Status: VERIFIED SOURCE CODE / NO BROKER QUERY / NO LIVE CHANGES

From `kalman-toss-gateway/app/toss_client.py`:
- `holdings()`, `orders()`, and `order()` issue HTTP GET via `_request`.
- `_request` calls `_headers`, which calls `_get_token`.
- `_get_token` may create token-cache parent directory and lock file, acquire a lock, issue an OAuth token request and write the refreshed token cache.
- On HTTP 401, `_request` invokes `_invalidate_rejected_token`, which may create a lock file and unlink the shared cached token.
- Hence GET does **not** guarantee zero local writes.
- `engine/execution_telemetry_sync.py` creates `TradeLedger` (may migrate SQLite) and patches telemetry; do NOT use it as a read-only audit.

SAFE_NEXT:
1. Obtain broker positions and open-order inventory from a separately vetted read-only reporting path, not the production token-handling client.
2. Review any proposed alternative implementation for filesystem and token side effects, including 401 retry.
3. Collect only redacted counts and holdings aggregates, then compare with timestamp-matched Neon mirror.
4. Keep `BROKER_RECONCILIATION_PENDING` until broker-side ground truth exists.

DO NOT execute new broker API code, disable token caching, or alter running LIVE configuration just to perform this audit.
