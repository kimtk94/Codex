# SFDC progress update — November 5, 2026 (read-only)

## Actual Salesforce Contact verification

On the authorized workstation `NGKR-SAL-TH`, authenticated Salesforce Contact/Account/Opportunity records were independently checked without creating or modifying CRM records.

- Starting approved Contacts: **151**.
- This 20-person verification batch: **17 PASS**, **3 HOLD** (1 actual Account ID mismatch and 2 Contact display-name verification holds).
- New total: **168 approved Contacts** (38 approved from original sample + 130 approved from 195 new candidates).
- New 195-candidate expansion cohort: **158 examined, 130 PASS, 28 HOLD, 37 unexamined**.
- Original cohort: 38 PASS and 10 HOLD. Combined unresolved HOLD: **38**.
- Rebuilt in-scope Opportunity relationship report: **168/1,013** Contact/Opportunity native links independently verified, zero source candidate-ID conflicts and zero missing mandatory evidence flags; **845 Opportunity rows** remain without native Contact link proof.
- Local web Contact alias validation: **168/168 accepted and searchable**, 164 distinct Korean names, four homonym groups, zero selection-label collisions, zero network calls during alias parsing.
- No raw personal identifiers, Contact names, emails, institutions, native Salesforce record IDs or prices are committed to GitHub.

## Existing 1:1 Opportunity–Quote learning cohort

From full previously enumerated 1,013 in-scope Opportunities and 862 Quotes, the structural 1:1 learning candidate cohort remains 177, with exactly one historically indexed Product and matching names. Actual authenticated Salesforce native-parent verification is complete for **177/177**:

- **176 PASS** exact existing Opportunity Related list Quotation a0P ID and labelled native Quote parent 006 ID.
- **1 HOLD**: Opportunity has two related Quotation records, confirmed in three independent read-only checks. This cannot be treated as a safe one-to-one training pair even if one name matches.
- Among the 176 native-parent successes, the latest approved Contact evidence intersects **48 Quote/Opportunity pairs**; 128 native-parent-verified pairs still require independent Contact proof.
- Historical identifiers are training references, not permission to copy pricing or create/save a new Quote.

## Local web and automated validation

The local PC web `http://127.0.0.1:31889/sales/oppo-quote` was rebuilt at feature commit `0d969a37`, restarted, and the private aggregate endpoint returned:
- Contacts 168
- Native Quote parent checks 177
- Quote native parent PASS 176
- HOLD 1
- Quote parent PASS with verified Contact 48
- Salesforce Save permission false

The UI now explicitly distinguishes native-parent attempts, PASS, and HOLD. The private audit endpoint is available only on the authorized Windows loopback web and does not return customer identities or raw CRM IDs; Vercel's hosted variant is disabled by platform and localhost checks. GitHub Actions runs `41943232988` (Desktop) and `41943238118` (web E2E) were SUCCESS on `0d969a37`.

## Remaining gates

1. Finish **37** expanded Contact candidates. Re-examine **38 HOLDs** only on independent evidence, never by bypassing Contact name, email, or native Account ID validation.
2. Audit the one existing two-Quote Opportunity manually if the user needs it, but do not promote it into one-to-one automated training.
3. Obtain independently verified currently applicable Product/PricebookEntry or custom Quotation Product/Process pricing and required Quote fields. The historical Product2 link is known for one saved Quote; its current price is **not** approved.
4. Hosted Vercel still lacks authorized Salesforce live read-only search. Do not expose private workstation data/Chrome session or enable CRM Create/Save without separate security review and user authorization.

No CRM writes. No new Products. No Production promotion.
