# Salesforce report readiness / UI field discovery — 2026-10-24

This audit is based on existing **read-only** Google Sheets values and user-supplied
Lightning screenshots. It does not establish Salesforce permissions or actual record
creation. The live browser has not been inspected through Playwright.

## Verified workbook

`SFDC_Automation_Followup_2026`
Spreadsheet ID: `1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI`

Read-only observations:

| Dataset | Existing evidence | Readiness |
| --- | --- | --- |
| SFDC Opportunity Raw | snapshot 332, no verified Opportunity ID or Last Modified Date | HOLD |
| SFDC Contacts | snapshot 187, no verified Contact ID or Last Modified Date | HOLD |
| SFDC Quote Export | Import QC: 814 records, 814 unique identifiers, 0 missing, PASS | CANDIDATE (verify individual links) |
| Quote approvals | Import QC: 551 unique IDs, partial field coverage | PARTIAL |
| SFDC Raw - Account/Contact/Opportunity/Quote | headers present but no rows at A2 in latest read | EMPTY / DO NOT USE FOR DUP CHECK |

The Source Audit last checked snapshots on 2026-10-24 ~18:05 KST but
`freshness_verified=NO`. Last checked != freshly retrieved from Salesforce.

The Quote Export contains Salesforce Record ID, Account ID, Contact ID, plus
`Opportunity ID` values such as `Opp-2025-01-20-192374`; do not treat these
nonstandard values as verified Salesforce record IDs.

## Opportunity Lightning screenshots: required fields (visible)

- Opportunity Name (text)
- Account Name (lookup)
- Main Contact (lookup)
- Amount (numeric)
- Opportunity Currency (dropdown; KRW shown)
- Close Date (date)
- Service Line (dual-list multiselect)
- Stage (dropdown)
- Forecast Category (dropdown)
- Progress Description (textarea)
- Status (dropdown)

Also visible: Owner, Lost Reason, Country, City, end-user account/contact,
Next Step, Description, Expected Payment Amount/Date and Sample Amount/Date.

Record type: **AMEA Opportunity Type**.

### Implementation implications

1. Do NOT submit based solely on `Opportunity Name` or approximate institution text.
2. Verify real Account and Contact **lookup selection** in Lightning, not typing.
3. For Service Line, select the desired Available entry then activate the move arrow;
   do not use a normal text fill operation.
4. Read the actual allowed Stage, Forecast Category and Status dropdown values
   before defining their mapping; never infer picklist values from screenshot labels.
5. Treat AMEA quotation IDs separately from SFDC quotation record IDs; several
   quotation versions may share a business ID, and Active is record-specific.
6. Use source event UID + object type for queue dedup, then Salesforce UI lookup
   to prevent previously saved record duplication (especially after timeout).
7. Never save without human-authorized pilot, readback of record ID, and verified
   relationship. No credential or session uploads.

Next gate: obtain one **redacted UI DOM locator audit** in an approved local Windows
session; capture only element types, accessible labels, required flags and control
counts. Do not log customer input values or page screenshots.
