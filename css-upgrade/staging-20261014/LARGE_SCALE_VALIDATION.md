# Novogene CSS — 1,200-record Integrated Regression (2026-10-15)

**Status: STAGING PASS / PRODUCTION NOT DEPLOYED.**

## Scope
- Actual server runtime functions were AST-extracted from a temporary copy of the **exact SHA-verified** `v8.92.1-server-local-adc` source. The module `main()` and mail collector were never imported or executed.
- Two patches were staged **in order**: `novogene_sif_history_candidate.patch` + `novogene_sif_manual_override_collision.patch`.
- Data source: **1,200 synthetic** SIF exclusion rows in in-memory SQLite (including inactive/restored, 30-day-old, malformed JSON, Prepayment and non-Prepayment cases).
- Functions exercised together: active Skip load, Prepayment selection, History rendering, Tracker vs Skipped partition, Overview Prepayment snooze synchronization, single-record restore, and dataframe output changed/unchanged/repair/retry state machine.
- All test file copies live in disposable `/tmp` locations. Source, primary Sheets, DB, mail, and scheduler untouched.

## New regression caught
**Manual Hold/Skip on the SAME project was overwritten by an auto Prepayment snooze.**

The previous green test had manual Hold/Skip on *different projects*. This new overlap scenario reproduced a source-level defect and the new targeted patch preserves manual `hold` and `skip_until_new_mail` modes while continuing to suppress SIF follow-ups through the separate dashboard exclusion mask.

Manual overrides take precedence until a user releases them, at which point the Prepayment auto-snooze may be created again while the project remains at an SIF stage.

## Evidence
- [Large synthetic integration test](https://github.com/kimtk94/Codex/actions/runs/38639585846): 1,200 records and 34 checks PASS. Checks include idempotent reruns; stage transition to QC; manual collision; skip restore and double-restore; 30-day history retention; sheet structure repair; and retry after simulated sheet write exception.
- [Actual Google Sheets load test](https://github.com/kimtk94/Codex/actions/runs/38639854155): server-side real SIF History builder and typed output writer populated a **separate synthetic Canary tab** with 1,200 rows, 400 Prepayment flags. A second identical run correctly skipped writing. Google Sheets connector independently confirmed 1,201 rows including header, **1,200 unique record IDs**, 400 Prepayment TRUE, and unchanged manual QA tab.
- [Canary spreadsheet](https://docs.google.com/spreadsheets/d/1eKMPMnRYeZB8tuPE2dblcSaHXSZ58REHPQgJSq2RIjA/edit): `SIF 1200 Load Canary` tab is test-only and contains synthetic data.
- [Dual-patch rollback/byte-integrity follow-up](https://github.com/kimtk94/Codex/actions/runs/38640063806): tests temporary copy reversal of both patches; inspect Actions conclusion before calling this gate PASS.

## Important limits
- Google Sheets `overwrite_dataframe_if_changed` uses the actual production function and real gspread API, but some sheet layout, obsolete-tail clearing, cache and hash helpers are mocked to avoid canary touching unrelated tabs. This is **not** a production-equivalent full CSS engine execution.
- The 1,200-record load is artificial and does not measure actual mail collector correctness, network faults, Salesforce sync, cross-service lock contention, or business SLA metrics.
- More than one simultaneously executing CSS hourly run remains untested, including true user edits racing a refresh.
- Current Drive offsite mail database (~340 MB) restore and newest project backup origin checks remain release blockers.

## Required before production deployment
1. Source current SHA still matches recorded original; exercise **both** staged patches in one executable release artifact. Ensure neither source nor original DB is changed during preflight.
2. Complete latest offsite project and mail backup restore checks and rehearse source-only rollback without discarding mail updates.
3. Prove isolated full-engine e2e across independent Google Sheets, DB, mail/CRM/Drive adapters and failure paths, with container/network deny, or explicitly scope rollout to the verified SIF component with a controlled single-cycle canary.
4. Verify manual Hold/Skip collision behavior and Prepayment false-positive resolution on the live Dashboard after authorized deploy.
5. Obtain **explicit production rollout authorization**. Until then: no merge, no live source replacement, no mailbox sends or backup deletions.
