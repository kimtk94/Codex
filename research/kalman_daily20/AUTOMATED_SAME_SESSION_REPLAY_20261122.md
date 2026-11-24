# Daily20 automated same-session replay and independent first-seal monitor

**Prepared 2026-11-22 (KST); research-only.** The original Nov 20 events have no first-capture 21-feature snapshot. The next genuinely new NYSE session is expected to be Monday **2026-11-23**, and it is not yet observed.

## New existing-workflow schedule

The already protected `.github/workflows/kalman-daily20.yml` now uses two UTC schedules on **Tuesday–Saturday**:

| Trigger UTC | Korean time | Intended mode |
|---|---|---|
| **02:40 UTC** | 11:40 KST | First seal of completed U.S. session (20 Bull, 40 Bear signals), or honest missed-seal HOLD |
| **04:40 UTC** | 13:40 KST | Separate **same-session** full Daily20 GitHub Actions run; original first-seal 26 OHLCV / 20×21 feature snapshot and 60 event hashes are immutable; classify input or prediction drift without rewriting |

Two distinct GitHub Actions runs are required; simply rerunning an internal function in one job would not test persistence. Existing Actions **concurrency** serializes research runs. The second run reuses the exact existing read-only market/model pipeline, pinned Drive files and independent full-SHA re-download. No new server, Google Drive ID, trade execution, model rule, credential or PR write route is introduced. The Saturday second pass may repeat a full refresh; track resource usage and adjust after observing real runs.

## Independent monitoring

Existing `stability_drive_readback.py` appends one secret-free log line:

`DAILY20_FIRST_SEAL_CHECK_V1 session=... status=... deep=... current=YES|NO original_run=... snapshot_sha=...`

This is emitted **after** authenticated Drive download, byte-for-byte local-vs-remote ZIP SHA256, all per-member SHA256 and the original 26 OHLCV / 420 features / 40 model records / 60 immutable events deep check. No input date, model prediction or broker writes occur here.

Existing `ops_readiness.py`, already triggered on **every** protected Daily20 run, parses this line and separates:

- **Legacy Nov 20:** `LEGACY_AWAITING_GENUINE_NEW_SESSION`, first snapshot 0; operational PASS permitted but research HOLD.
- **Genuine new first-seal run:** proof count >=1, correct same-day source session and captured original `source_actions_run_id` **equals current GitHub run ID**. Mark `FIRST_SEAL_REMOTE_READBACK_VERIFIED` and research HOLD `WAITING_INDEPENDENT_SAME_SESSION_REPLAY`.
- **Separate scheduled same-day replay:** no new Bull signals; proof contains original source run ID **strictly less than current GitHub run ID**, same session, a non-empty SHA256 verified by remote ZIP inspection. Mark `SAME_SESSION_ORIGINAL_INPUT_REPLAY_VERIFIED`; still research HOLD if regular close independent certification or 4-session outcome missing.
- **Missing first seal after Nov 23, incorrect capture run, changed/missing digest, duplicated log evidence, partial admission, wrong session:** monitor **operational FAIL** and research HOLD, never silently summarize green.

The independent monitor's 90-day GitHub Actions JSON artifact now stores original first-seal run ID and 64-character snapshot SHA256 for cross-run provenance. A **new first seal is not declared complete until the first actual post-Nov 20 completed US session has been observed**. A synthetic CI test validates this design now; it is not a substitute for market time and first real external sources.

## Boundaries and follow-up

- Exact **regular-session exchange-certified close remains 0/26**, historical corporate-action factors still HOLD.
- The original 2026-11-20 first input cannot be reconstructed.
- This proves the independent second run inherited a prior first-sealed, SHA-validated archive; it does not verify independence of Yahoo vs Alpaca or recreate original market tapes.
- Observe Tuesday Nov 24 2026 **11:40 KST** first and **13:40 KST** second scheduled Actions executions, contingent on GitHub scheduling and successful source refresh; validate research logs and the independent monitor status.
- Actual 4-US-session prospective outcome settlements remain pending.

Scope: pure read-only CI orchestration/monitor additions. Main and latest Drive uploads can continue as before; historic frozen signals and strategy thresholds are immutable.
