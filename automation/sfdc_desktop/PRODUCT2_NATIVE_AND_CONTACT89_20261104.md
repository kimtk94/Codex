# SFDC Contact expansion and existing Product2 native link audit — 2026-11-04

## Read-only Salesforce results

The authorized Windows Salesforce browser was used for two additional independent Korean Contact batches.

- Prior vetted Contact aliases: **74**
- Batch A: 12 candidates; **8 PASS**, **3 Contact display HOLD**, **1 email identity HOLD**
- Batch B: 10 candidates; **7 PASS**, **2 Contact display HOLD**, **1 genuinely different Account ID HOLD**
- Total: **89 approved Contacts** (38 original + 51 expansion PASS).
- Expansion cohort of 195 distinct new candidates: 66 examined, 51 PASS, 15 HOLD, 129 unexamined.
- Original Korean-name cohort still has 10 HOLD, so 25 total unapproved HOLD cases across the two cohorts.
- All 89 approved records were parsed and exactly matched in the local browser Contact search module: 89/89 PASS, 85 unique Korean names, 4 homonym groups, 0 name+institution+Contact ID suffix collisions.
- Some homonyms are at the same institution; never select by name/institution alone.
- No Salesforce Create, Update, Save, Quote duplicate, Product creation, or CRM write requests were made.
- Customer identifiers, raw Salesforce links, names and emails remain exclusively in the private PC folder, not this repository.

## Existing Product2 identity audit

A previously saved Quotation Product (Salesforce custom `Quotation_Products__c`) was visited in an authenticated browser and independently compared to existing local private baseline evidence in **three read-only rounds**. All three rounds:

- Native `a0N` existing Quotation Product link matched.
- Native `01t` existing Product2 link matched.
- Native `a0P` parent Quotation link matched.
- No modal Save or data modification.

`audit_existing_quote_product2_link_readonly.py`: **3/3 existing Product2/parent Quote link PASS**. Ten synthetic identity/fail-closed tests PASS.

An additional authenticated Product2 Details / Related page inspection found **no visible Pricebook Entry (01u) native links** and no current price in either displayed tab. Product2 Details displayed field labels including name, description, and Active, but no current value was independently approved. This establishes only that the **existing saved Quote line references an identifiable Product2**. It does **NOT** prove PricebookEntry, current availability, unit price, discount, quantity, currency, tax, Quotation required picklists, or eligibility to reuse that Product in a new Quote. The custom quotation form may use additional Product Template/process pricing mechanisms; do not automatically assume a standard Salesforce PricebookEntry applies without inspecting the actual creation flow.

Existing saved Quote product/process display also passed the earlier read-only 3-round, 10-check-per-round audit. Those historical amounts are references, never automatically reused for new customer quotations.

## CI and remaining gates

Latest code-validation commit: `910941e3`.

- Desktop safety CI: https://github.com/kimtk94/Codex/actions/runs/41842839691 — SUCCESS.
- Web browser build/E2E: https://github.com/kimtk94/Codex/actions/runs/41842844906 — SUCCESS.

Remaining work: 129 expanded candidates, 25 HOLDs, authenticated hosted Salesforce read-only search, fresh Product catalog/price source identity and quote fields. The latest local Windows web remains read-only for CRM and the hosted web must not expose private workstation records. No Production deployment or Salesforce Save in this turn.
