# G12 — Sheets ↔ SQLite Recovery / Manual-Control Ownership Contract
**As of 2026-10-17 | STAGING / READ-ONLY AUDIT | NOT APPROVED FOR PRODUCTION**

## 1. Observed operational Sheets schema (header-only verification)

The connected Novogene CSS workbook metadata and bounded first-row reads showed these surfaces. These are **field names, not customer records**:

| Existing tab | Manual/user-control candidates | Classification and consequence |
|---|---|---|
| CSS Project Dashboard | `exclude` (A), possibly `exclude_reason` (B) | The automation must preserve operator exclusion decisions across updates. |
| CSS Contract-SIF Tracker | `skip` (A), `Prepayment` (B), possibly `skip_reason` (C) | SIF state controls may be edited by users; do not overwrite while regenerating the project display. |
| CSS Contract-SIF Skipped | `restore` (A); `Prepayment` (C) requires ownership confirmation | A restore click must not be silently reverted by a renderer. |
| CSS Manual Exclusions | `restore` (A) | Explicit restore decisions must persist across a refresh. |

This table **does not prove** each cell's validation, permission, onEdit persistence, or its exact current business owner. It inventories existing control candidates for targeted acceptance testing. Actual values were not exported. Under uncertainty, mark these columns **protected pending review**, not system-owned by default.

## 2. Concurrency hazard

A naive workflow:
1. read a row;
2. user changes `skip` or `restore`;
3. background engine overwrites the entire row from the stale snapshot.

This can erase the newest user edit. **Two or three reads before writing reduce some risk but cannot eliminate the read-to-write race** because Google Sheets does not provide a SQLite-shared transaction. A fake `compare-and-swap` operation plus a receipt inside one memory object is not a faithful representation of the real API.

The existing CSS data-frame writer and its snapshot-conflict guard must therefore be evaluated against actual request ranges and structural sheet operations (clear, resize, sort, rewrite). A generated dashboard row is not a safe durable home for operator controls unless those cells are fully outside the engine's write surface.

## 3. Proposed release architecture (requires design review)

**Separate owners, not merely additional retries:**

- **User-owned controls:** a dedicated, keyed, append-only/manual input surface by immutable `record_id` (or, for project-only exclusions, immutable `project_id`). The CSS output renderer must have **no write authority** to these control cells. Operator changes flow into durable SQLite manual state with monotonic receipt/command IDs.
- **System-owned output:** separate read-only/display surfaces derived from SQLite. Engine may update only explicitly system-owned fields. It must never copy stale `skip`, `Prepayment`, `restore`, `exclude`, or operator notes back over input cells.
- **Row identity:** use immutable record keys; do not assume physical row indexes survive sorting, filtering, deletion or sheet rebuild. If records need structural insertion/removal, use a separately authorized protocol; an update-only patch may not reorder or clear user inputs.
- **Durable SQLite outbox:** commit delivery intents locally and process them separately. After an unknown Sheet response, **read back the current keyed state** and either recognize a matching observed state, identify a conflict, or preserve the intent as unknown. Do not claim exactly-once delivery based only on a missing HTTP response.
- **Conflict policy:** if any latest manual receipt differs from the snapshot used to calculate an action, abandon or recompute the automatic action; manual Hold/Skip/Release is authoritative. The source of truth must be declared for Prepayment before production approval.
- **Runtime isolation:** no production auth, live sheet, mailbox, project database, live logger, cron or backup mounts during G12. G16 all-sink and failure-path proofs are independent release gates.

## 4. Tests and evidence

- Synthetic SQLite Outbox model: 20/20 PASS. Includes write-before-ack uncertainty, lost response, restarts and fake CAS conflicts: https://github.com/kimtk94/Codex/actions/runs/39014723532.
- Additional synthetic ownership/race tests: 24/24 PASS (101/101 complete offline suite): https://github.com/kimtk94/Codex/actions/runs/39016498256.
- 24 tests include a **negative control proving that stale full-row rewrite loses user edits**. Positive tests protect controls by forbidding the test engine from writing user-owned state, block moved row keys/unknown IDs, and treat readback merely as an *observation*, not exactly-once evidence.
- Actual staged SIF / Action handoff inside private rootless Bubblewrap: 22/22 PASS, source SHA pinned: https://github.com/kimtk94/Codex/actions/runs/39014961981.
- **Nothing here validates a real Google Sheets conditional transaction**, and no operational sheet was written in this phase.

## 5. Explicit blockers before release

- [ ] Confirm edit ownership and dropdown/checkbox validations for the four live tabs, including `Prepayment`, `exclude_reason`, and `skip_reason`.
- [ ] Review actual live writer field masks / ranges; show user-owned cells cannot be overwritten even after stale-snapshot reads or inserted/removed rows.
- [ ] Select an authoritative keyed manual-control storage design (possibly a dedicated tab); plan migration of existing manual state without deleting historic user input.
- [ ] Demonstrate restoration/retention of the current **five active SIF Skip records** (three Prepayment) in an isolated snapshot. Historic skipped-view retention is not the same as SQLite authoritative state.
- [ ] Verify exact page/row identity in a test-only actual Google Sheet, with concurrent user edits and a simulated lost API response; avoid falsely claiming CAS or exactly-once guarantees.
- [ ] Run G12 entire patched CSS engine with **all** G16 sinks intercepted and no external egress; test normal and injected-failure paths, mail-collector boundaries, backup/log paths and post-retry consistency.
- [ ] Produce an operator-acknowledged rollout plan with DB migration, immutable snapshots, reversible source patch, live-rollback strategy and explicit approval.

**Release conclusion: G12 NOT_RUN; G16 BLOCKED/PARTIAL. Draft PR only; no live deployment.**
