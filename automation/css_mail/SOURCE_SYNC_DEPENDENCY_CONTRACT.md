# CSS source-first dependency contract (2026-10-30)

## Ordered dataflow

1. QQ IMAP Inbox/Sent -> CSS Git Ingest + Canonical Mail Ledger -> UID, body, timestamp and archive-handoff QC.
2. Original Invoice Issued email (never reply/forward) -> attachment filename, invoice number, X/J, AMEA and gross KRW validation -> Tax Invoice Extract.
3. Original Statement email -> J+X unique key, amount, currency, UID, date -> Statement Amount Extract.
4. Feishu Online-Project TAT + month controls + verified mail/invoice/statement inputs -> BI Project Lifecycle Overview.
5. Reconcile issued J+X and unissued verified J+X against lifecycle; missing source mapping BLOCKS the monthly publisher.
6. Publish monthly Invoice Actual, verified Statement Pending and forecast as separate concepts, with source quality and timestamp.
7. After source and readback QC, expose data through authenticated Google Sheets API and Vercel web; E2E Preview before Production.
8. Independently: SFDC three reports -> row/ID/SHA audit -> Lead/Opportunity/Quote staging. Join personal QQ Sent evidence -> Lead My Sent Audit -> NBA.
9. Independently: Feishu eTax/Outstanding/Payment -> invoice identity and payment QC -> settlement views, never inferred as cash receipt.

## Required safety contracts

- QQ All Emails is an archive and need not remain newly written if CSS Git Ingest covers or overlaps its final message. Inspect recent live message AND fetch timestamps. Reject duplicate or malformed folder|uidvalidity|uid keys.
- TAX INVOICE original amount includes 10% VAT. Preserve raw gross KRW and original evidence; per invoice Actual Net KRW = ROUND(Gross KRW / 1.1, 0). Net K USD = Actual Net KRW / FX / 1000. Never divide already ex-tax 2025 official USD revenue.
- Statement Pending and forecast VAT status are not yet proven. Do NOT divide them by 1.1 until source basis is verified. Any combined sum with Net Actual has MIXED_VAT_BASIS until resolved, and is NOT certified net Revenue.
- An original, verified J+X Statement absent in lifecycle must remain BLOCKED_SOURCE_MISMATCH, never zero/forecast/ignored.
- Pending transitions to Actual only on unique matched original invoice evidence. Reject duplicate invoice number conflicts and Re/Fw notice replies.
- A new staged SFDC Lead report or a fresh validated preserved report is acceptable only with SHA256, row/ID integrity and age below the contract. Absence of QQ personal outbound mail evidence is not proof of no other contact.
- Feishu eTax monthly source missing or ambiguous must be marked SOURCE_NOT_FOUND. Never silently use the Payment/Outstanding table as Tax Invoice evidence.
- A successful upstream GitHub workflow does not prove downstream data or authenticated web E2E. Only success + freshness + content parity + readback may publish PASS; otherwise retain the previous snapshot with STALE/BLOCKED metadata.
- No automatic customer email sending or Salesforce Save is authorized by this contract.

## Recovery order

QQ sync and checkpoint -> original invoice/statement extraction -> Feishu source freshness -> lifecycle X/J reconciliation -> monthly net Actual and Pending review -> BI parity -> protected web Preview E2E -> Production review.
SFDC report audit -> personal Sent audit -> Lead/NBA readback -> protected web Preview E2E.
Feishu Online/Payment/eTax each retains its own source-status and never substitutes for another.

## Current known incidents

- QQ checkpoint had a literal-pipe regex defect and treated historical All Emails as a live feed (PR #415).
- Lead personal audit rejected PRESERVED_NO_NEW_REPORT despite recent 493-row SHA-audited source (PR #415).
- J001-X209SC26103004-Z01 is in original Statement evidence but missing from published lifecycle: restore upstream X mapping before running Revenue monthly.
- eTax October monthly table was not found by strict name discovery; this is a source mapping question, not authorization to substitute other Feishu tables.
- Current BI Invoice Fact VAT correction was verified in the connected Sheets; monthly lifecycle and web remain subject to this net-revenue rollout.