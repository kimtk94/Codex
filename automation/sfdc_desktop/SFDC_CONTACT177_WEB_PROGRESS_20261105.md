# SFDC Contact 177 / Quote 176 follow-up — 2026-11-05

## Source and safety

Authorized local Windows workstation NGKR-SAL-TH with authenticated Salesforce read-only browser. Customer records remain in `~/.sfdc_desktop`, outside the repository and outside hosted Vercel. No Salesforce Create, Save, Update, or new Product action was performed.

## Contact expansion

The previous approved snapshot had 168 Contacts. This turn inspected 12 additional new Contact candidates:
- 9 independently verified Contact–Account–Opportunity–email identity matches.
- 2 HOLD_CONTACT_EMAIL_IDENTITY.
- 1 HOLD_TimeoutError.
- 0 Salesforce writes.

**Current approved unique Contacts: 177** (38 from the original reviewed Contact sample plus 139 from the new 195-person expansion cohort).

Recomputed using **latest status per unique native Contact ID**, rather than counting repeated attempts as new people:

| Expansion cohort | Count |
|---|---:|
| Eligible new candidate Contacts | 195 |
| Independently reviewed | 170 |
| PASS / approved | 139 |
| HOLD / not approved | 31 |
| Never inspected | 25 |

Expansion HOLD reasons: Contact detail display 18, native Account ID mismatch 6, email identity 4, UI timeout 3. The 10 HOLDs from the original sample remain separate, so there are **41 unresolved Contact HOLDs** in the two verified cohort samples.

The 1,013 Opportunity list includes 43 two-candidate homonym rows and 44 with no Contact name match. These are **not** automatically covered by the 195-name expansion cohort. Verified Contact/Opportunity native links in the Opportunity snapshot now number 177; 836 Opportunity rows still lack the specific independent Contact-link evidence used by this workflow.

## Existing Oppo–Quote pairing

The previous full read-only reconciliation remains:
- 1,013 in-scope Opportunities (KAIST and Hannam excluded).
- 862 existing Quotations in the fully enumerated list, of which 412 are historical single-Product learning cases.
- Conservative 1:1 structural shortlist 177.
- Independent native parent check **177 attempted, 176 PASS, 1 HOLD**. The HOLD is a real two-Quote Opportunity on three read-only checks and must not be promoted.
- Among 176 parent-PASS pairs, **51** have independently verified matching Contact/Account/Opportunity evidence and **125** remain Contact identity pending.
- All 176 are historical pair training evidence only; none validates current Product PricebookEntry, Quote pricing, mandatory fields, or permission to Save.

## Automation and local web

A new pure `calculate_expansion_progress` function was added to `expand_korean_contacts_private.py`. It deduplicates retries by native Contact ID, distinguishes original approved overlaps, and emits only aggregate counts into `expanded_contact_cohort_progress_PRIVATE.json`. The `--summary-only` option refreshes the report without any Salesforce browser actions. Synthetic tests: 6/6 PASS.

The Windows loopback-only Next.js web now reads the aggregate report in `/api/sfdc/full-audit-local` and displays expansion reviewed, pass, hold, and remaining counts. Validated actual local browser action at `http://127.0.0.1:31889/sales/oppo-quote`:
- HTTP 200, cards visible
- 177 approved Contacts, 170/195 reviewed, 139 PASS, 31 HOLD, 25 unreviewed
- 177 historical Quote parent checks, 176 PASS, 1 HOLD
- 0 browser CRM write requests and Save flag false

A transient JSX markup error caused one intermediate hosted web build to fail. Fixed at commit `4fb8cc91`. Both subsequent GitHub workflows succeeded:
- Desktop CI: https://github.com/kimtk94/Codex/actions/runs/41948373664
- Web build/browser E2E: https://github.com/kimtk94/Codex/actions/runs/41948378259

Vercel feature Preview at `4fb8cc91` is READY (not Production). The hosted preview has no access to the private workstation files or browser session; the local search and audit routes remain restricted to an explicitly enabled Windows 127.0.0.1 environment.

## Next actions / unresolved gates

1. Read-only verify 25 remaining uniquely identified new Contact candidates. Keep 41 HOLDs fail-closed and investigate reasons separately.
2. Investigate 1 parent native-relationship HOLD manually (two related Quotes), **not** by weakening 1:1 automation criteria.
3. Independently verify current Novogene Product or custom Quotation Product/Process price source, applicable current prices, mandatory fields, and duplicate checks. No historical Pricebook/price authorization exists yet.
4. Architect secure authorized Salesforce read-only search for hosted web; do not export PII or Chrome credentials to GitHub or Vercel.

No automatic CRM Save. No Production promotion.
