# Novogene CSS — 8-Patch Snapshot Conflict Validation (2026-10-15)

**VERIFIED IN STAGING — NOT DEPLOYED.**

## Why an eighth patch is necessary

The prior seven-patch candidate prevents duplicate Hold/Skip/Release commands and races among SQLite writers, but it reads Google Sheets controls only once. If a human changes an Overview cell just after that snapshot, the CSS cycle can write the stale command to SQLite. SQLite `SAVEPOINT` protects partial DB changes, **not** the accuracy of an already stale input snapshot.

## Patch 8 — `novogene_css_snapshot_conflict_guard.patch`

In the actual `sync_overview_snooze_actions` function:

1. Read priority-grid and management-grid commands as a single `batch_get` snapshot.
2. Enter a SAVEPOINT, re-read both command ranges immediately before mutating SQLite; abort if the original and second snapshot differ.
3. Apply the existing manual commands and one-shot receipt writes to SQLite.
4. Re-read both ranges again before releasing the SAVEPOINT; if the third snapshot differs, rollback **both the snooze rows and command receipts**, then fail this cycle.
5. Only commit if all three snapshots are identical.

**Important:** Google Sheets and SQLite are independent services. This is an *optimistic change detector*, not an atomic cross-service transaction. A cell change after the third observation and before commit, or an edit that changes from A→B→A between snapshots, remains potentially undetectable. A dedicated client-side action API with action IDs, compare-and-swap, or transactional message queue is needed for an absolute once-only guarantee.

## Evidence

| Gate | Result | Link |
|---|---|---|
| Real CSS function bodies, in-memory synthetic DB, simulated edits after snapshot 1 and after processing, intentional third-read failure, 24 genuine two-process WAL races, eight-patch exact rollback | **200/200 PASS** | [Run 38701293956](https://github.com/kimtk94/Codex/actions/runs/38701293956) |
| SHA-verified server source, all eight patches apply/compile and reverse byte-identically, 433 function names preserved, live DB query-only quick_check/FK | **46/46 PASS** | [Run 38701555123](https://github.com/kimtk94/Codex/actions/runs/38701555123) |
| 1,200 synthetic projects: persistent SIF exclusions, tracker/history, manual overrides, QC transitions, write retry, source rollback | **76/76 PASS** | [Run 38701659819](https://github.com/kimtk94/Codex/actions/runs/38701659819) |
| **Real Google Sheets API** on specifically named synthetic Canary tab: edit at second `batch_get` and third `batch_get`, rollback vs stable 3-read commit, unrelated manual QA preserved, Canary cells cleared | **19/19 PASS** | [Run 38702155598](https://github.com/kimtk94/Codex/actions/runs/38702155598) |

**Original operating source SHA-256:** `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840`

**Eight-patch candidate SHA-256:** `3963b6cbd60205c2738943e4b28e2a88a1987776bfdda05ee8cba269d6ea3806`

**Real Sheets test location:** [CSS SIF Upgrade Canary](https://docs.google.com/spreadsheets/d/1eKMPMnRYeZB8tuPE2dblcSaHXSZ58REHPQgJSq2RIjA/edit), tab `Overview Race Canary`. The only external mutations were to this synthetic tab. The script cleared its test cells on completion. The production CSS Google Sheet was never opened by the Canary test.

## Residual launch gates

- **Full CSS `main()` end-to-end in OS-isolated inputs/network** is still untested; targeted real function bodies and main AST branches were tested instead.
- Snapshot checking incurs two extra Google Sheets batch reads per Overview sync. Review rate limits, latency and error handling under the scheduled CSS service and its other API operations.
- One-shot receipt DB table is a schema addition; retain on source-only rollback to avoid reactivating stale commands. The UI needs a clear-to-rearm/acknowledge explanation, particularly for the same Hold duration.
- A real concurrent human UI edit between final snapshot and DB commit is still not atomic. If strict guarantees are required, introduce a server-side command queue with unique action IDs.
- Pre-deploy: verify latest Drive project + mail DB backups, source SHA and service schedule, staged canary and explicit release approval. During rollout: one scoped cycle, verify SIF Prepayment three projects, non-SIF tasks, manual states, newly created receipt table, and next scheduled cycle. Stop and rollback source on unexpected behavior.
- **No merge, production deployment, mail send or backup deletion was performed.**
