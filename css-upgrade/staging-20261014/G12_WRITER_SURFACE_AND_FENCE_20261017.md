# G12 writer surface and control range fence — 2026-10-17

**Decision: STATIC AUDIT COMPLETE / POLICY TESTED IN STAGING / LIVE PROTECTION NOT YET PROVEN.**

## Evidence captured

1. Actual server CSS source fingerprint SHA-256 `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840`; no import, main execution, source export or file modifications.
2. Read-only AST enumeration on 2026-10-17: **28 candidate writer call sites**, including 8 structural/full-rewrite or destructive candidates, 19 unknown-effect candidate APIs and one append candidate. Example high-risk source **line numbers only**: `1673 resize`, `1871 batch_clear`, `1891 set_with_dataframe`, `2835 resize`, `6453 resize`, `17648 set_with_dataframe`, `19275 sort`, `20921 clear`. These calls may operate on helper-specific Sheets; the AST inventory cannot establish target tab or live write effect. [Pinned AST audit](https://github.com/kimtk94/Codex/actions/runs/39023826487).
3. Offline AST classifier 9/9 passing. [Regression](https://github.com/kimtk94/Codex/actions/runs/39023802370).
4. Live workbook metadata/header read confirmed the exact target sheet IDs and protected columns. [Prior live header audit](G12_LIVE_HEADER_OWNERSHIP_AUDIT_20261017.md).
5. Staged `g12_sheet_range_fence.py`: pure policy over four known sheet IDs with bounded A1 intervals; rejects protected user-control columns and record identity columns, full-row overwrites that touch these columns, structural/unknown operations, unknown IDs/titles/masks, and unbounded/header writes. Explicitly returns `row_identity_or_concurrency_proven=false` and `live_sheet_write_performed=false`.
6. [**11/11 live-schema synthetic policy tests PASS**](https://github.com/kimtk94/Codex/actions/runs/39024053936). No Google Sheets/SQLite/mail/CRM calls.

### Source audit classifications

| Category | Candidate sites | What is *not* proven |
|---|---:|---|
| Structural or full-frame risk candidates | 8 | That any specific tab or user-control cell was rewritten |
| API effect unknown | 19 | Actual request `fields`, A1 range, or whether formatting-only |
| Structural append candidate | 1 | Whether row identity remains stable |

The policy is **not installed in the operational engine**, so a direct legacy `gspread` call may bypass it. A pure function returning a safe verdict is not a transactional guarantee. This test does not inspect the private production source call arguments or customer contents and does not perform any Sheets writes.

## Release continuation

- [ ] Connect the policy to **every** relevant actual writer adapter in the isolated patched candidate; determine writer aliases, exact range/field masks and indirect paths. Do not assume 28 candidate calls are exhaustive.
- [ ] Replace unsafe full-row rewrites on four manual-input tabs with an ownership-separated input/output architecture, or a demonstrably safe keyed per-column update that cannot clear protected columns. Dry-run expected output with fresh snapshots only.
- [ ] Prove **record-key** stability, resynchronization after row reorder, manual edit-after-read, stale snapshot, lost API response, and SQLite crash recovery **in a nonproduction Sheet**. A1 mask alone does not address wrong-row writes.
- [ ] Run G16 all-sink isolation including import effects and failure handlers; then G12 full CSS main E2E on cloned databases and disposable workbook.
- [ ] Conduct rollout/rollback review and explicit approval before any production patch.

**No production deployment, automatic mail, live workbook edit, source replacement or DB change authorized.**
