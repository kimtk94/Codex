# Write Safety Policy v1
Date: 2026-10-26. Must be satisfied before production data modifications.

## Global
- Data retrieval/analytics are read-only by default. Never commit credentials, tokens, customer records or invoice attachment bodies to Git.
- Restrict service accounts to required Sheets, and Google dashboard reads to authenticated allowlisted users and approved fields.
- Existing NBA done, exclude, restore, owner edits, approved invoices, existing financial data must not be overwritten by refresh. Reconciliation should propose review records instead of mutating uncertain facts.
- Require explicit allowlisted target, exact source ID, dry-run diff, stable idempotency key, nonexpired upstream snapshot, actor/audit receipt, and verification after write.
- On uncertainty STOP; no guessed amounts, guessed customer replies, or guessed invoice↔payment match.

## SFDC UI RPA (separate execution owner)
- Use only authenticated authorized Windows Chrome session, not guessed URLs or unsafe DOM shortcuts. Verify active window and context; maximizing can aid visibility but is not identity proof.
- Account/Contact lookup is VERIFIED only if selected pill/record ID and Account affiliation are checked, not CLICKED_NOT_VERIFIED.
- Fill required seven fields with field-level before/after readback. Record Detail/Related identity must be verified before edit.
- Default fill-only/no-save. Save requires specific user-approved test scope, duplicate search, exact payload preview, passed checks, one-shot queue claim and bounded retry.
- After Save, require exact record ID + page identity verification and persistent receipt in Sheets. Uncertain Save outcome must block retry until search for preexisting record (avoid duplicates).
- Never auto-send customer email, auto-close an Opportunity from weak QQ evidence, or infer paid from invoice issued.

## Emergency procedures
Pause affected writer, preserve raw snapshots and manual ledgers, retain last good views, export safe aggregate incident details, manually approve remediation. Do not use force-push or blind tab replacement.
