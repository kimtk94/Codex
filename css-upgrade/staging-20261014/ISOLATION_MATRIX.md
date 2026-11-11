# CSS Synthetic Canary Isolation Matrix — 2026-10-15

**Status: FAIL CLOSED — full `main()` execution is NOT authorized.**

This document is a read-only inventory and validation plan, not a production execution permit. The source is proprietary and must not be committed to a public repository.

## Verified server-source facts

- [Production AST inventory](https://github.com/kimtk94/Codex/actions/runs/38637725484): exact original CSS SHA matched; `main()` has 584 AST call sites / 205 unique call targets.
- Among those calls: 25 `overwrite_dataframe_if_changed` sites, 15 selected DB-mutating call sites, eight selected backup/log-related call sites. Counts are AST call locations, not runtime API traffic or an exhaustive sink inventory.
- [Import-time audit](https://github.com/kimtk94/Codex/actions/runs/38637952229): CSS module has potential pip install via top-level `subprocess.run`; mail collector has 139 top-level call expressions with SQLite/Google Sheets/Drive effects and no `__main__` guard. Importing either is not a safe canary procedure.
- [Fail-closed gate on server](https://github.com/kimtk94/Codex/actions/runs/38638533644): no import or full `main()` performed; static analyzer blocked both modules and refused unisolated main.
- [Pure synthetic guard tests](https://github.com/kimtk94/Codex/actions/runs/38638413462): 19 of 19 passed. The wrapper is a testing tripwire **not an OS-level security boundary**.

## External side-effect matrix

| Boundary | Observed or plausible code path | Isolation required before end-to-end | Gate |
|---|---|---|---|
| Module import | Top-level pip subprocess, collector import-side effects | AST-only extraction or subprocess with sealed site-packages and no network; collector never imported | BLOCKED in current canary |
| Google Sheet discovery/writes | `open_configured_spreadsheet`, 25 dataframe-write call sites and formatting/health paths | Substitute Google Sheets client with ID-specific allowlist, verify *every* worksheet and update method is covered, or use API-mock with all external sockets blocked | PARTIAL: SIF-only canary |
| SQLite project state | `connect_db`, `set_meta`, upserts, run history, manual user states | Private cloned DB in a temporary directory; reject production path, symlinks and WAL/SHM files outside sandbox | BLOCKED for whole main |
| Mail SQLite source | Incremental UID queue processing and collector sync | Independent mail snapshot with synthetic message content; never import/execute production collector | BLOCKED |
| IMAP/SMTP/OAuth | Collector authentication, possible network APIs | Fake mail backend; enforce OS-level network deny for non-allowlisted endpoints and deny outbound sends | BLOCKED |
| CRM/Salesforce | Salesforce events/lead sync | Synthetic event source; require read/write endpoint mapping before test | NOT PROVEN |
| Backups and logs | `backup_runtime_db`, `save_json`, Drive publishing | Route source, state, logs and backups to private disposable directories; no source Drive folder access | BLOCKED for whole main |
| Error/exception path | Failed run writes health and backup records | Failure-path injection against disposable DB and mock sheet; verify all writes stay isolated | BLOCKED |
| Runtime services | 10-minute mail collector, hourly CSS wrapper | Run in detached test namespace without touching live locks, service state or schedules | BLOCKED |

## What is already tested

- Patch AST compile and byte-exact reverse on isolated server source copy.
- Current real SQLite, read-only: 5 active Skip / 3 Prepayment / 5 history rows.
- Synthetic in-memory SQLite snooze lifecycle preserves manual Hold/Skip and releases QC transition.
- Selected **real CSS SIF history/dataframe writer functions** operate against synthetic DB + separate Canary Google Sheet; identical second run skips writes.
- Server ADC credentials can perform scoped writes to the dedicated Canary document only.
- Current SQLite state can be snapshotted into a disposable database and restored with integrity/FK checks.

## Required to change full-engine gate from BLOCKED

1. All production source, mail, sheet and backup paths are replaced by disposable fixtures; outputs stay under a dedicated temporary root.
2. All external client constructors, including indirect wrappers and exception-handler paths, are intercepted/denied; network egress is separately enforced at the process/container boundary.
3. A static and runtime check confirms no production spreadsheet ID, no production DB paths, no Gmail/IMAP/SMTP sends, no production backups or service locks.
4. Test executes *only* in an isolated process/container with disposable credentials and source inputs, not by importing the mail collector.
5. First-run, identical second-run, error injection, manual override, SIF stage advancement, and outcome diff checks all pass.
6. Restore newest offsite Google Drive backups (project and mail) independently and verify full content.
7. Produce a targeted source diff and a rollback plan. Deploy only with explicit authorization.

### Important limits of the current guard

`canary_isolation_gate.py` provides preflight checks and an allowlisted synthetic Google Sheets wrapper. Python callers can bypass this wrapper if they directly instantiate a Google client or use raw sockets. Boolean flags in the policy **do not themselves disable network access**. Therefore passing its unit tests does **not** mean a full engine run is safe. `run_full_main()` intentionally always raises `FULL_MAIN_BLOCKED`.

No production source/DB/Sheets/scheduler/backup is changed or deleted by the tests above.
