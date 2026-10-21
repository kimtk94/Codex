# TAX INVOICE × Payment Outstanding (read-only P0)

Source workbook fields verified from `SFDC_Automation_Followup_2026.xlsx`:
- `CSS Tax Invoices`: invoice_month, issued_at, invoice_number, amount_krw, project_id, h_project_number, po_reference, institution, service, project_description.
- `Quotation Invoice Match`: quotation_id, approved_at_kst, invoice_number, issued_at, amount_krw, match_type, matched_project_id.
- `SFDC Invoice Index`: Invoice Name (not yet guaranteed identical to invoice_number).

Matching policy:
1. Exact normalized invoice_number => matched candidate.
2. If both sides expose billed total, mismatch => manual review.
3. Missing/duplicate invoice ID => review, never infer paid.
4. project_id, PO, institution, amount and service are only candidate discovery clues when explicitly mapped; no automatic merges.
5. Only Active SFDC Quotes are valid for future SFDC direct matching; CSS historical quotation rows must not be interpreted as live Active status.
6. Include payment-only records in review; do not silently drop them.
7. Do not perform network calls, mutate spreadsheets/Base, send mail, or log row-level customer data.

Current blockers: Feishu Sheets 99991672 missing scope and actual Base Payment table field mapping. Existing `Payment Outstanding 10.20` Base table must be audited. Feed its real invoice identifiers only once verified. Unmatched rows must not be automatically marked paid.

Proposed user-facing consolidated view: `Payment & Tax Invoice` with invoice, project, institution, issued amount, outstanding amount, evidence, status, followup owner/date; show private per-record information only in an authorized spreadsheet or dashboard, not GitHub logs.
