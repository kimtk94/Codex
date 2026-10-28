# CSS Mail — Single Source Migration Contract

## Canonical destination
One authoritative raw mailbox table in Novogene_All_Emails workbook (ID: 1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY). Target CSS Git Ingest after attachment/provenance schema enrichment; archive All Emails only after lossless verified migration. SFDC spreadsheet holds DERIVED views, never an independent raw mail source.

## Fail-closed migration requirements
1. Snapshot both existing tables first. No deletion, blind overwrite, or reset of IMAP UID checkpoints.
2. Key by mailbox + folder + UIDVALIDITY + UID. For legacy records missing UIDVALIDITY, preserve source-row identity, label uncertain, and reconcile safely.
3. Preserve original From/To/Cc, sender, received timestamp and zone, subject, all attachments, Message-ID, In-Reply-To, References, direction, and fetch time.
4. One mail may contain multiple distinct TAX INVOICE numbers. Index invoice number independently, not by message or AMEA.
5. Separate mail receipt from SFDC sales ownership; shared sales.korea recipient does not prove personal ownership.
6. Switch ALL downstream consumers together only after record-level parity and attachment coverage pass; old table becomes read-only archive.
7. Distinguish INGEST_SUCCESS from SOURCE_FRESH, PARITY_PASS, OWNER_VERIFIED and WEB_FRESH.

## Existing readers to update BEFORE switching
incremental_sync.py writer, mail_health.py, mail_operations.py, unanswered_auto.py, tax_invoice_extract.py, quotation_approval_extract.py, thread_header_backfill.py, personal_invoice_receipt_audit.py, and SFDC/BI/web derived consumers.

## Rollout gates
Backup -> schema extension -> historical migration with explicit provenance -> parity/ownership tests -> atomic consumer cutover -> stale writer removal -> monitored rollback window.
Migration is NOT complete merely because this contract is committed.
