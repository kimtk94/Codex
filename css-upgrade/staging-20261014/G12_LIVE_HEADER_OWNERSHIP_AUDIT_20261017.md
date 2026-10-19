# G12 live Google Sheets header and validation inventory — 2026-10-17

**Scope: metadata, header row, and cell dataValidation ONLY. No customer records read back, no operational writes.**

Workbook: Novogene_All_Emails (current CSS operational workbook). Google Sheets connector reads verified the following tab IDs and control-field positions:

| Sheet | sheetId | Control / position | Key identity fields | Validation (row 2) |
|---|---:|---|---|---|
| CSS Project Dashboard | 948865119 | A: `exclude`; B: `exclude_reason` | E: `project_id` | A2 BOOLEAN strict; B2 no evidence |
| CSS Contract-SIF Tracker | 1618938211 | A: `skip`; B: `Prepayment`; C: `skip_reason` | AD: `project_id`; AH: `record_id` | A2, B2 BOOLEAN strict; C2 no evidence |
| CSS Contract-SIF Skipped | 692581491 | A: `restore`; C: `Prepayment` | N: `project_id`; U: `record_id` | A2 BOOLEAN strict; C2 no evidence |
| CSS Manual Exclusions | 1445506838 | A: `restore` | B: `project_id` | A2 BOOLEAN strict |

Note: positive checkbox validation on row 2 does not establish that validation is applied consistently to all rows, or that subsequent engine rewrites preserve it. A missing returned dataValidation object is **not** proof a cell is editable or unrestricted. No operator permissions, onEdit triggers, data consistency across a full column, or write ownership were established in this inventory.

## Live operational health cross-check (headers + bounded status rows only)

The `CSS System Health` tab is present (sheetId `1143725632`). The three recent rows read on 2026-10-17 have **SUCCESS** status for code `v8.92.1-server-local-adc`:
- 2026-10-17 09:20–09:24 UTC (254.295 seconds);
- 2026-10-17 08:20–08:24 UTC (264.946 seconds);
- 2026-10-17 07:20–07:24 UTC (227.833 seconds).

The latest read-only server audit separately confirms SQLite quick_check and foreign-key checks for both databases; the Collector's counts are consistent but do not explicitly confirm mail delivery. Evidence: https://github.com/kimtk94/Codex/actions/runs/39023060299

## G12 safety decision

**FAIL CLOSED: current header + checkbox inspection does not prove manual control protection.**

- Operator-owned fields (`exclude`, `exclude_reason`, `skip`, `skip_reason`, `Prepayment` pending business-owner confirmation, and `restore`) must be treated as protected.
- Writers using full-row replace, clear, sort, or resize can still erase those control fields. Header correctness alone is insufficient; inspect actual engine writer ranges/field masks.
- Use immutable `project_id` or `record_id` (not physical row number) for command identity and migration design. Record keys must be validated for uniqueness and stability before rollout.
- Required next: nonproduction test sheet with concurrent edit-after-read, lost API response, structural row reorder and restoration acceptance; compare exact output to durable SQLite manual controls. Do not claim Sheets↔SQLite atomic CAS or exactly-once without a suitable protocol.
- G12 complete patched CSS main still **NOT_RUN**; G16 whole-engine sink interception still **BLOCKED/PARTIAL**; production deployment **NOT_AUTHORIZED**.

This inventory complements the existing G12 recovery contract and does not change any production system configuration.
