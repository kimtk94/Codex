# G12 scoped writer bridge — synthetic implementation and acceptance boundary
Date: 2026-10-17

## Outcome

Added:
- `g12_scoped_writer.py`: explicit, in-memory Google Sheets-style `update(range_name, values, value_input_option="RAW")` adapter.
- `test_g12_scoped_writer.py`: 13 synthetic tests for scoped field writes, record identity checks, manual edit collision, lost-response observation and fail-closed behavior.
- Existing `g12_sheet_range_fence.py`: 11 live-header-derived policy tests remain unchanged and passing.

[GitHub Actions: 24/24 PASS](https://github.com/kimtk94/Codex/actions/runs/39024674188)

The adapter maps the production **column layout** into an in-memory fake only; it explicitly refuses real `gspread.Worksheet` objects, unknown Sheet IDs, unbounded/structural operations, identity overwrites, and protected manual-control fields. An already-running production writer is **not intercepted**.

## Isolated acceptance scenarios

| Test case | Synthetic result | Status for real CSS runtime |
|---|---|---|
| Project/SIF safe display-only bounded update | PASS | UNVERIFIED |
| Manual skip, prepayment and skip_reason untouched | PASS | UNVERIFIED |
| Dashboard exclude, Skipped restore, Exclusions restore protected | PASS | UNVERIFIED |
| Row ID differs before proposed write | DENIED | UNVERIFIED |
| User control edit at synthetic write time | PRESERVED (disjoint column writes) | UNVERIFIED |
| Lost response after synthetic write | observed state matches, no automatic retry or exactly-once claim | UNVERIFIED |
| Lost response before a write | UNKNOWN_NEEDS_REVIEW; no automatic retry | UNVERIFIED |
| Unsupported clear/resize/sort/full-row operations | DENIED | UNVERIFIED |
| Accidental use against real `gspread` object | DENIED by class type | NOT INSTALLED |

## Explicit concurrency limitations

A record key checked in a separate Google Sheets request can still change before a following nontransactional update. The mock registry check demonstrates defensive behavior **only when the physical row changes before the key check**. It is not a Google Sheets compare-and-swap, and it does not protect against a race between check and update. A lost-response readback proving matching current values does not prove exactly one external write. In addition, column-disjoint writes protect **fields**, not correct project-to-row attribution after concurrent reordering.

## Next engineering gates

1. Identify the exact `set_with_dataframe`, `batch_clear`, `clear`, `resize`, `update` destinations in the private CSS writer using a read-only, source-SHA-pinned audit. The earlier AST inventory found **28 candidates, including 8 potentially destructive/full-rewrite** calls, not a proven exhaustive registry.
2. Pick and implement a **separate operator-controlled input vs system-owned output surface** so system code has no direct write authority to manual fields. Avoid adapting a full-row data-frame replacement into a partial update without a keyed migration plan.
3. Use isolated patched CSS function bodies in Bubblewrap with disposable SQLite and a test-only workbook; assert real adapter call interception, user edited-after-snapshot handling, unknown response recovery, row reorder, and no bypass path.
4. Only then attempt G12 full main under G16 all-sink isolation and conduct a release/rollback rehearsal.
5. Keep Draft PR #168 and production deployment explicitly **BLOCKED** until independent approval.

### No-operational-write statement

This addition only changes staging files in GitHub. No production service, Google Sheet, SQLite file, mailbox, CRM, current source or scheduled job was changed by this G12 bridge.
