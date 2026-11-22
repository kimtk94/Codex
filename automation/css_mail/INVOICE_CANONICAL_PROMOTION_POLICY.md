# QQ → CSS Canonical Invoice: Promotion Contract (READ-ONLY DESIGN)

**Status:** HOLD — no canonical writer or Revenue updater authorized by this document.
**Scope:** 2026 QQ original CSS Tax Invoice issued notices only.
**Version:** 2026-11-22. Tracked by GitHub issue #942.

## Baseline: independent checks, not posting authorization
- QQ 2026 Backfill 364 versus canonical CSS Tax Invoice List 303. The 61 key gaps **are not 61 unpaid invoices**.
- QQ-only 25/25 were classified nonofficial in the authenticated original mail audit. Exclude from promotion.
- Extract overlap 36: independent original IMAP MIME verification passed for 34/34 eligible records. Two QQ ↔ Extract UID conflicts remain HOLD (one also has a blank QQ PO). Never auto-rewrite QQ source UID.
- CSS Git Ingest sender, notice title, inbox scope and Extract UID match 36/36. Header-only matches are not sufficient for actual financial writes.
- Additional 8 Extract invoice numbers are absent from QQ Backfill and canonical CSS across **all** years: 7 collected before, 1 after the latest reported QQ scan.
- Another 14 QQ rows with blank issued_month do match Extract. Blank-year rows must not be misclassified as missing from QQ.
- Counts are a point-in-time snapshot. The scheduled monitor recalculates without storing identifiers.

## Gate A — original issued evidence
1. Actual QQ INBOX original MIME with correct issuer, specific issued-notice subject, no reply/forward, UID, UIDVALIDITY, Message-ID, and verified attachment filename.
2. Attachment invoice number, positive KRW gross amount, AMEA, H project, and PO correspond to that exact source message.
3. Evidence is traceable by immutable source hash, verification timestamp, and invoice-level receipt held **privately**, never in a public GitHub log or artifact.
4. Previous aggregate 34/34 verification alone does not authorize writing without a per-invoice proof receipt.

## Gate B — authorization and business scope
1. Explicit verified accountable owner, organization, Account/Contact and project scope. Canonical CSS Tax Invoice List currently has no owner approval field; do **not** infer ownership.
2. Per-record reviewer approval explicitly binds invoice identity, source hash, gross amount, VAT, issue date, project and proposed destination/version.
3. Verify source reflects a **Tax Invoice Issued** event, not Pending, Statement or Forecast. Revenue excludes VAT; Tax Invoice amount includes VAT (normally 10%).
4. Check duplicates by invoice ID across all years, canonical, Extract, QQ and idempotency registry, including differing amounts or project identities.
5. Freeze existing destination revision before a separately approved sequential/atomic write. After save, re-read source and destination; stop and flag partial failures without duplicate retries.

## Event-time and pipeline status
- SOURCE_UNAVAILABLE: authoritative source unreachable, incomplete scan or authentication failure.
- STALE: last QQ Backfill source scan exceeds 36h freshness threshold.
- NOT_VERIFIED: Extract first collected **after** last QQ Backfill scan; do not infer a sink error until next scan.
- HOLD: prior-scan unlinked Extract, blank QQ month, inconsistent UID/PO or independently verified official record awaiting owner approval.
- SINK_LAG: only after individual official source, owner, permitted scope and destination SLA are verified, not from derived Extract alone.
- BLOCK: duplicate invoice ID, invalid schema, amount conflict or contradictory evidence.
- PASS: audit checks complete; not proof of actual Revenue recording.
- NO_NEW_DATA: only if comparison proves no new eligible source event, not an empty table.

## Monitoring and storage
- Reuse existing GitHub Actions daily 02:20 UTC QQ/CSS parity workflow; no new server or duplicate scheduled job.
- Monitor reads Google Sheets with a readonly service-account scope. Original MIME verification remains in the existing authenticated QQ read-only workflow.
- Retain aggregate-only event timestamps and stage counts for 30 days in Actions artifacts; never publish customer, invoice ID, email, UID, Message-ID, filename or amount.
- Capture source_event_at, collected_at, verified_at, missing_count; sink_updated_at remains null until a genuine destination update timestamp can be proven.
- No automated CSS Tax Invoice List, Revenue, Payment, SFDC write or mail delivery is allowed by this design.
