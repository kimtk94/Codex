# CSS Full-Main Effect Isolation Matrix — 2026-10-18

**Read-only static census PASS. Full main execution remains BLOCKED.**

## Evidence

[Exact source-to-owner sink ledger](https://github.com/kimtk94/Codex/actions/runs/39050808293) analyzed production source SHA `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840` without importing or running production modules.

The transitive AST traversal identified **337 reachable functions** and **278 selected call sites**.

| Selected family | AST sites | Owning functions | Key calls |
|---|---:|---:|---|
| SQLite access and possible mutations | 211 | 63 | `conn.execute` 166, `conn.commit` 24, `conn.executemany` 9, `conn.rollback` 11, `conn.backup` 1 |
| Sheets output and formatting | 53 | 23 | `overwrite_dataframe_if_changed` 26, `overwrite_typed_worksheet` 5, `spreadsheet.batch_update` 13, `worksheet.update` 6, `worksheet.freeze` 3 |
| Local file mutations | 12 | 5 | `os.replace` 5, `shutil.copy2` 7 |
| Google connection | 2 | 2 | `gc.open_by_key` 1, `gspread.authorize` 1 |

**Caution:** counts are occurrences in source. These categories overlap at the call-chain level; database `execute` can read or write, and Google Sheets calls may perform formatting. The exact-name ledger is not exhaustive of dynamic aliases, HTTP calls through wrappers, credential discovery, top-level module side effects or indirect dispatch.

## Required isolation adapters / barriers

1. **Files:** create an explicitly controlled temporary root with only synthetic input files. Require read-only access to the preflight source copy and deny reads or writes to operational CSS folders except a separately approved data snapshot. Any `os.replace`/copy/delete sink must resolve only under temporary root. Do not rely on a Python boolean flag to constrain raw filesystem access.
2. **SQLite:** use a temporary cloned, disposable database, separated from production data directories. Deny access to operational DB filenames and WAL/SHM paths. Verify migrations, rollback, atomic commits, backup and foreign-key checks on the disposable copy only.
3. **Google Sheets:** provide a mock or proxy that cannot resolve the production spreadsheet ID. Expose synthetic worksheets, explicit tab/range allowlists, and record attempted writes. For a true full-engine test, block outbound network altogether; the previous real Canary test was a narrower separately authorized test using its test-only spreadsheet.
4. **Mail:** deny SMTP/IMAP and any web-hook or message-send mechanisms. Provide synthetic mailbox fixtures only. No real customer addresses/UIDs should be included in the test log.
5. **Salesforce, Drive, OAuth:** inject fixture responses through narrow adapters and prevent raw connection creation. Do not mount operational credentials inside the isolated process.
6. **Process and network:** enforce an operating-system boundary (e.g. disposable container with `--network none`, read-only root, constrained volumes/user, zero secrets, no host network). Verify that unexpected HTTP/socket and out-of-root filesystem writes actively fail.
7. **Scheduler:** `main()` only invoked inside isolation, never by the operating service unit. No startup scripts, task timers, cron edits or background mail collector.
8. **Instrumentation:** export only synthetic IDs, function names, status counters, attempted sink calls, safe error classes and timing. No customer data.

## Acceptance gate for full synthetic main

- Same eight-patch staged SHA `3963b6cbd60205c2738943e4b28e2a88a1987776bfdda05ee8cba269d6ea3806`, with baseline source SHA revalidated.
- A fully disposable environment that proves **network deny**, **production filesystem deny**, and **no secret/credential mounts** using negative controls.
- Synthetic project, mail, SIF, Salesforce, invoice and manual control fixtures; no connector reads against customer accounts.
- Explicit allowlisted database and spreadsheet writes to disposable stores only.
- No uninstrumented sink call remains in a complete execution path; otherwise fail closed.
- Business invariants: SIF Prepayment suppression, portfolio preservation, independent customer tasks, one-shot receipt stability, release/re-arm behavior and appropriate QC re-entry.
- Clean rollback and complete disposal of all temporary outputs, together with logs demonstrating no live mutation.

**Status: NOT READY for full `main()` invocation.** Static auditing cannot prove enforcement, and current plugin/CI tests have not yet supplied a process-level mandatory access-control boundary. The Draft PR must remain open and unmerged until explicit deployment authorization.
