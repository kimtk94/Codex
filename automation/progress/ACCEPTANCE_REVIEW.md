# Evidence review / sign-off protocol
- All PR/Actions evidence is candidate-only. Nothing is accepted automatically.
- Maintainers enter an explicit review record in acceptance_registry.json only after reviewing required per-task evidence keys from acceptance_manifest.json. Never paste secrets, customer PII or mailbox contents.
- Review record: task ID, exact gate ID, ACCEPTED or REJECTED, reviewer identifier, timezone-aware reviewed_at, and required evidence fields for ACCEPTED.
- A gate is ACCEPTED only when **every task** in it has a complete approved record. Schema validator rejects missing fields, unexpected tasks or wrong gate IDs. This is syntactic and completeness validation; reviewer's claims still require independent business verification.
- Changes require peer review via PR, CI, and an audit trail. No automated mutation of the registry from GitHub green workflow status.
- No Sheet D/E updates are authorized by this change. Explicit signed-review approval and a separate, protected publish path must be reviewed before reflecting acceptance in the live dashboard.
