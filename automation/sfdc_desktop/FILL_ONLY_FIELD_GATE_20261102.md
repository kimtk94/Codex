# SFDC Existing Opportunity — Field Gate & Change Review (2026-11-02)

## Status
The existing Salesforce Opportunity is uniquely matched to its Novogene business Opportunity ID via the authenticated Salesforce Related Quotation and exact-QID Quotation report. The same Salesforce record's Account and Main Contact IDs were independently resolved from exact Details field links.

This checkpoint verifies **fill-only readiness**, not an actual business-value change or Salesforce Save approval.

## Live desktop verification (NGKR-SAL-TH)
- Opened the exact existing Opportunity inline editor on an authenticated Chrome session.
- Inspected Amount (numeric spinbutton), Close Date (text date field), Stage (picklist combobox), and native Account/Main Contact lookups.
- Located Amount and Close Date **by exact field label**, avoiding ambiguous global field indexes.
- Reentered each of the existing Amount and Close Date values unchanged; each form was dismissed with **Cancel**.
- Before the no-change tests, the current Account/Contact field-link record IDs were re-read and compared with previously verified private IDs. No mismatch detected.
- **No changed deal values were entered**, no lookup selection was made, and no Salesforce Save was clicked.
- The stage selector was **not modified**; its option-value mapping and downstream effects remain unverified.

## New code
- `audit_existing_numeric_date_nochange.py`: validate exact source/lookup identity, same-value Amount/Close Date fill and Cancel.
- `test_existing_numeric_date_nochange.py`: exact label / stale lookup ID regressions.
- `prepare_existing_change_review.py`: offline-only, fail-closed review preflight. Requires stable request UID, explicit reviewed current values, exact Opportunity business/native ID, correct Account/Contact IDs, one before-value per changed field, and only allowlisted fields (Name, Amount, Close Date, Progress Description). Duplicate request UIDs are blocked when supplied in a private ledger. The preparer never writes Salesforce and does not certify live before-value equality.
- `test_prepare_existing_change_review.py`: synthetic UID, wrong target/lookup, invalid amounts/dates, no-review and no-Save tests.
- `make_existing_change_template.py`: captures current Opportunity Name, Amount and Close Date **on the Windows PC only** into a private JSON review template. Proposed changes are initially empty, reviewed flag is false, and Save is prohibited.
- `test_make_existing_change_template.py`: guards that templates cannot silently inherit historical values as new changes.

## Verified results
- Windows full Desktop RPA suite: **149/149 PASS**.
- Direct Account/Contact plus Amount/Close Date no-change audit: exit code 0, both forms Cancelled.
- Private change-review template created: `%USERPROFILE%\.sfdc_desktop\existing_change_review_TEMPLATE_PRIVATE.json`.
- Code synced to Windows Git checkout HEAD `6f915ad`.
- The template and private Salesforce IDs are NOT stored in GitHub or CI artifacts.

## Next blocking gates
1. **Actual changed-value fill-only pilot**: user reviews/selects intended new values in private template, sets explicit review flag, then run the offline preflight; immediately before any actual fill, compare expected-before values with the current Salesforce visible controls. Never automatically copy historical Amount/Stage/Close Date to a new deal.
2. **Salesforce Save**: not authorized. Requires an explicit pilot authorization, authoritative ID and lookup readback, idempotent request ledger, duplicate record checks, safe retry semantics, post-save detail readback and ledger verification.

This checkpoint does not claim production write readiness. The draft report source-schema fix remains independently tracked under PR #508. Existing report email subscriptions are unchanged.
