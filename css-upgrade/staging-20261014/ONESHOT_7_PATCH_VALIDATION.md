# Novogene CSS — One-Shot Controls and Two-Process SQLite Validation (2026-10-15)

**Seven-patch candidate: STAGING VERIFIED / NOT DEPLOYED.**

## Fixed workflow ambiguity

Before this patch, the Overview's `Normal Action=Hold` or `Skip` and management `Release` could be replayed from an old sheet snapshot after the previous action had expired or been released. There was no durable consumed-action identity, so an expired Hold could be unintentionally recreated.

Patch 7, `novogene_css_one_shot_receipts.patch`, creates an **idempotent, SQLite-persisted command receipt** table on first manual-control sync:
- `overview_control_receipts(project_id, source, signature, consumed_at)`
- `source` distinguishes priority-grid actions and management-grid Release.
- `signature` includes normalized action and Hold duration, **not the auto-updating mail marker**.
- A conditional upsert claims a signature only when it is new or changed. If the input is an unchanged old command, skip the action even if the underlying Hold/Skip has already expired.
- If the user leaves their project row visible and clears the `Normal Action` / `Hold Days` fields, that observed blank **re-arms** a subsequent input. Changing action to `Release` and then to `Hold` also registers an explicit new user command.
- The receipt is written in the same `SAVEPOINT` as the actual manual-state change, so an exception rolls it back with the action. A fresh SQLite backup preserves receipts.

## Evidence

| Validation | Result | Evidence |
|---|---|---|
| Two **separate Linux processes** / SQLite file connections, WAL writer locks, 24 controlled interleavings: auto-create vs Hold, auto-update vs Skip, QC delete vs Hold | **PASS, 24/24 rounds** | [run 38660214599](https://github.com/kimtk94/Codex/actions/runs/38660214599) |
| Seven patches: real CSS manual sync function, repeated input and expiry, re-arming, same-project non-SIF tasks, stale management release, SQLite receipt backup/restore, 24 process races and reverse patch | **185/185 PASS** | [run 38660918748](https://github.com/kimtk94/Codex/actions/runs/38660918748) |
| Seven-patch exact server source SHA, Python AST compile, preservation of 433 functions, live DB read-only quick_check/FK, full byte-exact patch reversal | **42/42 PASS** | [run 38661084055](https://github.com/kimtk94/Codex/actions/runs/38661084055) |
| **1,200 synthetic SIF projects** across Prepayment, stage transitions, manual states, Tracker/History/Overview and writer retries, seven-patch exact reversal | **72/72 PASS** | [run 38661130690](https://github.com/kimtk94/Codex/actions/runs/38661130690) |

Original source SHA-256: `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840`

Seven-patch staged SHA-256: `2c45c940e35790944a1e0abde9b0312161e3b49a2b7d31993643d2d864fa338a`

## Operational semantics and limitations

1. **Input protocol change:** Same Hold duration entered again *without first clearing or releasing the previous command* intentionally does nothing, even after expiry. The UI should show a consumed-action/acknowledgment status and instructions for deliberate re-issue.
2. A user changing Hold days while an earlier Hold is valid may still be blocked by the previously staged active-Hold protection. Explicit `Release` then new `Hold` is the current safe workflow. Additional dedicated UI revision/token support is preferable.
3. If user clears `Normal Action` but leaves `Hold Days` positive, the app intentionally interprets that as `Hold` (legacy rule), not a blank re-arm. Clear both fields.
4. `overview_control_receipts` is a **new persistent table**. A source-only rollback may leave the extra table in the DB; do not drop it automatically because deletion would re-enable old commands. A future migration should specify table lifecycle and retention.
5. Test races use **two genuine processes and connections**, with deterministic holds around SQLite writers. They do not stress the live systemd timer/mailer, all external-network APIs, or a concurrent edit of the actual Google Sheet during a refresh.
6. Conditional SQLite receipt insertion is atomic on its connection, but a user editing a Google Sheet cell after the `batch_get` snapshot is still a separate optimistic concurrency risk. Do not claim that full UI isolation has passed.

## Status

The PR remains Draft. Production CSS source, live SQLite, Google Sheets, services and Google Drive backup files were **not changed**. Any release still requires scoped approval, a per-cycle write audit, rollback verification, and post-deploy health checks.
