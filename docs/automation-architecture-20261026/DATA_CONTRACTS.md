# Data Contracts v1
Date: 2026-10-26. This is a normative design proposal, not an assertion that every source currently conforms.

## Layers
1. Raw append-only snapshots: QQ mail UID; SFDC emailed report and content hash; CSS event/project; Feishu project/payment status; invoice evidence. Preserve source bytes/hash, extraction timestamps, source identifiers and timezone.
2. Staging: validate columns, parser version, date/amount/ID types, unique identity and source freshness. Invalid or partial report must not overwrite the last valid snapshot.
3. Verified relations: source ID joins and explicit proof; ambiguous, missing, multi-match → REVIEW_ONLY.
4. Derived marts: NBA, TAT, forecast, revenue. Manual decisions/overrides are authoritative separate ledgers, not columns overwritten by rebuilds.
5. Web consumption: read-only authenticated API over approved summaries, not raw mailbox contents.

## Minimum entities and primary identifiers
- MailMessage: (mailbox, uidvalidity, uid) preferred; message-id and normalized subject are supplementary only. Retain sender, recipients, KST received/sent, direction, subject, thread-evidence provenance. Same email address or normalized subject NEVER proves a reply.
- Account: SFDC Account ID; alias normalization is an enrichment only.
- Contact: SFDC Contact ID and verified parent Account ID; one email may represent multiple contacts/opportunities.
- Lead: SFDC Lead ID; Lead conversion join must use correct source-specific converted ID, not an unrelated CRM 00Q key.
- Opportunity: SFDC Opportunity ID; stage, account/contact, owner, close date, currency, observed_at.
- Quote: SFDC Quote ID plus associated Opportunity ID; multiple quotation process rows per Quote ID are allowed, and cannot be counted as independent quotes. Active/approved fields must be independently verified. Missing Active → UNKNOWN.
- Project: authoritative source Project ID (e.g. AMEA) plus CSS/Feishu X/H crosswalk only with supporting evidence.
- Invoice: issuer's invoice number, amount KRW, issue date, project links with provenance, unique evidence key. An issued invoice is not a receipt.
- Decision: immutable (decision_id, source_entity_key, decision_kind, actor, effective_at, supersedes, evidence). Done/excluded/manual forecast override survives recomputation.

## Financial policies
- Revenue actual comes from confirmed invoice facts with exact identity; do not sum both quote and invoice for the same project. Forecast is a separate, visibly differentiated measure.
- Unissued = no verified issued invoice evidence; not the same as unpaid. Outstanding project-level balance ≠ verified unpaid invoice; payment received status remains UNKNOWN until reconciled to receipt evidence.
- Display KRW and K USD; when conversion is required use configured exchange-rate provenance (current requested default 1 USD=1,500 KRW); never silently substitute spot FX for reporting baselines.
- Handle same customer aliases and WGS/WES normalization via reviewed lookup tables; never mutate raw category.

## Data validity
- Every fact has source_system, source_key, observed_at_KST, ingested_at_KST, content_sha256 or snapshot_id, relationship_state and last_qc_result.
- Classify VALIDATED, PARTIAL, STALE, UNKNOWN, CONFLICT, QUARANTINED. No extrapolated amount or inferred close/reply is VALIDATED.
- Fail closed on ambiguous IDs, conflicts, missing schema, missing source, stale snapshot or absent write permission.
