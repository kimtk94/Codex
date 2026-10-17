# G16 operational Sheets manual-write overlap audit — 2026-10-17

**Read-only AST-only evidence; release blocked.** This source analysis does not execute, import, modify or export the operational CSS module.

## Verified result
- Workflow: https://github.com/kimtk94/Codex/actions/runs/39042243069
- Expected source SHA verified: `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840`.
- Top-level function definitions parsed: **400**.
- Candidate sheet-write call sites: **104**, in **43** functions.
- Functions that contain both a watched manual-column literal and a candidate Sheet writer: **four**.
- Overlapping functions by literal (not exclusive): `Prepayment` 2, `skip_reason` 2, `exclude` 1, `exclude_reason` 1, `skip` 1, `restore` 1.
- **Not proven:** any specific row or cell was overwritten. Calls may be read/format operations or writes to different tabs; mere AST co-occurrence is an inventory clue.

## CI failure distinction
The **new static audit** printed `G16_MANUAL_WRITE_AUDIT_END` and `G16_STATIC_COOCCURRENCE_NOT_WRITE_RANGE_PROOF` successfully. The overall multi-step workflow later returned FAILURE at an **existing and previously unresolved private real-helper semantic contract**: `G16_PRIVATE_REAL_HELPER_FAILED_MINIMUM_TWO_PURE_HELPERS`. This is unrelated to the static inventory assertions. Neither substep is grounds to mark full G16 PASS.

## Next targeted acceptance tests

1. Build an **AST-level dataflow map** from each Dashboard / SIF Tracker / SIF Skipped / Manual Exclusions output writer to the sheet variable, DataFrame and generated column subset. Confirm whether a clear/resize/full-width update is performed.
2. Classify the live controls `exclude`, `exclude_reason`, `skip`, `Prepayment`, `skip_reason`, and `restore` as manual owned / computed / mixed *per tab*, with validation and onEdit event behavior confirmed separately.
3. Demonstrate, on a non-production sheet with manual edits mid-write, that output updates do not erase user-owned values. Readback after an unknown response is only an observed state, **not** proof of exactly-once delivery.
4. Confirm five active SQLite SIF Skip records (three Prepayment) appear as intended in the future protected history output; do not treat empty 30-day Skipped tab as missing DB records.
5. Keep `G16=BLOCKED/PARTIAL`, `G12=NOT_RUN`, and production deployment on hold until actual whole-engine isolation and explicit approval.

**No production Sheet cells, DBs, source code, services, locks, mail or schedule were changed.**
