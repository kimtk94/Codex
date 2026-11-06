# Salesforce source export contract — 2026-11-06

## Source authority
- SFDC's authenticated CRM record IDs, parent relationships, and Last Modified Date are authoritative.
- Google Sheets timestamps prove **copy time** only, not source update time or relationship integrity.
- QQ email reports are useful staging data, not an authenticated Contact–Account–Opportunity relation.
- Never upload customer rows or credentials to GitHub Actions, web assets, or public build logs.

## Live SFDC_Auto Sheet audit (read-only)

| Source tab | Rows in existing mirror | Missing required columns |
|---|---:|---|
| Oppo list | 332 | Opportunity ID, Last Modified Date |
| Contact | 187 | Contact ID, Account ID, Last Modified Date |
| Quotation | 23 | SFDC Quotation ID, Quotation ID, Active, Last Modified Date, linked Opportunity ID |

The source **Quotation** tab currently shows Opportunity-style headers such as
`Opportunity Name`, `Main Contact`, `Service Line`, `Stage`, and
`Amount`; this is not sufficient proof of the custom `Quotation__c` record.

## Required Salesforce report exports

1. **Opportunity**: 006 record ID, Opportunity Name, 001 Account ID, Main Contact 003 ID, Stage, Currency, Amount, Created Date, Last Modified Date.
2. **Contact**: 003 record ID, 001 Account ID, Korean full name, email, Created Date, Last Modified Date.
3. **Quotation__c**: a0P record ID, Quotation ID/AMEA number, linked 006 Opportunity ID, 001 Account ID, 003 Contact ID, Active, status, currency, Last Modified Date.
4. **Quote lines**: existing SFDC Product/Process/Pack identifiers, units, quantities and prices, linked to the same verified Quotation. Never create new Products from text-only names.

All three record exports must identify their Salesforce report timestamp, scope and owner. If export permissions do not expose stable IDs, keep the related web lookup on **HOLD** rather than infer joins from display names.

## Existing verified status

The current `SFDC Report Readiness` sheet reports required-field checks **FAIL**
for Opportunity, Contact and Quotation; `SFDC Quote Link Audit` reports
`active_validation_ready=False` and missing ID/link columns. The 2026-11-06
scheduled-readiness workflow is designed to retain BLOCK until real exported
source evidence passes. Even when its source checks pass, an authenticated
owner-only live Contact recheck remains required for web lookup and saving.

## Workflow disposition
- PR #519: web browser-only No-Save preview and source readiness contract.
- Source readiness GitHub Actions: `.github/workflows/sfdc-contact-lookup-readiness.yml`.
- CI (synthetic): https://github.com/kimtk94/Codex/actions/runs/42135799602
- No live CRM write, no Quote creation, no customer email, no automatic approval.
