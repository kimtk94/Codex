# SFDC complete one-to-one parent readback and Contact expansion — 2026-11-05

## Audited population and safety

Authorized Salesforce browser on workstation NGKR-SAL-TH. All actions read only. The 2026-11-03 snapshot contains **1,013 in-scope Opportunities**, **862 unique fully enumerated Quotation list rows**, **412 historical single-Product Quotation entries**, and **450 remaining manual/unclassified Quotation entries**. The 1,013 scope excludes KAIST and Hannam University according to prior scope rules.

The complete snapshot reconciliation identified:
- 390/412 historical single-Product Quote records with referenced parent Opportunity IDs present in the 1,013 in-scope inventory; 22 outside that scope.
- 381/390 parent snapshot entries also had exact Contact label agreement; 9 did not.
- 72 distinct Opportunity parents have multiple single-Product Quote rows, covering 173 Quotation entries.
- Of the 450 other Quotes, 329 have one in-scope Opportunity *name* match only, 89 have none, 32 have ambiguous multiple name matches. These are NOT native parent ID approvals.

## One-to-one structural cohort — 177 records

Conservative name-based filter across the full 862 Quote list and 1,013 Opportunity names: one historical Product record, exact Oppo name and Contact display label, unique Oppo name across in-scope Opportunity list and only one Quote with that Oppo name across the full Quotation list. This yielded **177 candidate Quote–Opportunity pairs**, 158 Ready to send and 19 Need to submit.

Every one of the **177/177 candidate pairs** has now been inspected in authenticated Salesforce. For each, open the exact native Opportunity record, inspect its Related Quotation list and require a count of exactly 1, resolve the specific native a0P Quote ID, open Quote Details and verify the parent Opportunity native 006 ID. Results:
- **176 native Opportunity–Quote parent matches (PASS)**.
- **1 HOLD** due non-unique Related Quote list, not verified as a safe one-to-one relationship.
- The HOLD was independently re-read **three times**, and the actual Opportunity Related Quotation count was **2/2/2** across those reads. This is a stable **two-Quote parent**, even though only one indexed Quote had the same Opportunity *name*. It is excluded from the one-to-one training approval cohort.
- **0 uninspected structural candidates, 0 Salesforce writes**.
- Of the 176 native parent matches, **45 had independently verified Contact–Account–Opportunity evidence** at the time of the Contact refresh. The other 131 have native Quote parent proof but require separate Contact identity checking before full customer-bound draft preparation.
- None has a currently approved Quote price/PricebookEntry or permission to auto-create or auto-save new Salesforce records. The actual historical Product identity and current Quote business fields remain separate gates.

Private evidence (never committed to GitHub):
- `~/.sfdc_desktop/one_to_one_quote_native_parent_verified_PRIVATE.json` (177 native parent readback statuses)
- `~/.sfdc_desktop/one_to_one_quote_hold_three_readback_PRIVATE.json` (3× independent non-1:1 diagnostic)
- `~/.sfdc_desktop/one_to_one_oppo_quote_learning_shortlist_PRIVATE.json`

## Contact validation

The 195 distinct new Contact candidates beyond the original 180-Opportunity source have been independently checked in batches:
- Prior 118 examined: 94 PASS, 24 HOLD.
- Current batch 20: **19 PASS, 1 Contact display HOLD**.
- **138/195 examined**, **113 PASS**, **25 HOLD**, **57 unexamined**.
- Original 48-contact sample: 38 PASS, 10 HOLD.
- Total approved Contacts: **151**, total Contact HOLD: **35**. Their verified native Contact/Account/Opportunity IDs remain private.
- Whole 1,013-Opportunity audit: 151 currently independently approved candidate links and 862 rows still unapproved; 43 homonym candidate rows and 44 no-name rows in the historical list.
- Browser-only local private Contact alias parser accepted **151/151**, 147 unique Korean names, four homonym groups and zero contact-select label collisions.

## Service mix — name hints, not Product approval

Among 177 one-to-one structural entries:
- PMP 38, mRNA 37, WGS 11, DIA 6, 16S 2, WES 1, scRNA 1.
- Remaining 81 have no unambiguous name token from this exact list and are **HOLD_UNCLASSIFIED_NAME** (not necessarily missing services).
- No historical name token grants a new Product2/PricebookEntry ID, current price or permission to Save. Current PE250 quantity remains M reads per sample; other supported modes use Gb.

## Local web and CI

Local PC Oppo–Quote web: `http://127.0.0.1:31889/sales/oppo-quote`, loopback-only.

Web source now separately displays (i) native Quote parent link matches, (ii) those with Contact link proof, (iii) parent matches still pending Contact proof. All API payloads are aggregate counts and contain **no customer names, emails, institutions, native CRM IDs or amounts**. Hosted Vercel endpoint is disabled by platform/host/opt-in gate and is not a direct Salesforce search integration.

GitHub feature branch: `feat/sfdc-playwright-desktop-p0`, PR #263. All synthetic tests run three times under the desktop GitHub Actions workflow; hosted web CI builds and performs browser E2E without authenticating to Salesforce. All CRM Save/Create/Update operations remain disallowed.

## Next gates

1. Review remaining **57** expanded Contact candidates. Revisit **35** HOLDs according to exact reason without relaxing native Account/Contact ID and email checks.
2. Match current existing Product and process definitions to an authoritative price/configuration source; previous Product2 link checks do not validate a current PricebookEntry.
3. Verify required Opportunity and Quote fields, duplicate-check behavior, and user-approved current price before any future separately authorized Salesforce Save process.
4. Design a secure authenticated hosted Salesforce read-only lookup. The Salesforce ChatGPT plugin is currently unavailable under admin policy; the local Chrome-based verification is in place and does not imply web-hosted credentials.
