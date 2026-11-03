# Opportunity / Quotation historical case learning — 2026-11-03

## Sources and hygiene
- Connected Google Sheet `SFDC_Automation_Followup_2026` → `SFDC Quote Export`: 814 historical Quote export rows. Case labels read from **Quotation Name** and paired **Opportunity Name**, never price/name inferred from unrelated customers.
- Connected `SFDC_Auto` → `Oppo list`: 332 Opportunity rows, used to compare naming habits (not independent matched Quote evidence).
- `SFDC_Auto` → `Quotation`: 23 rows but **Opportunity-shaped columns**, not authoritative Quote records. **EXCLUDE** from Quote pattern training and source-of-truth linkage.
- Historical exports may lag the live Salesforce Report and contain mixed product services. Their names alone cannot prove a current customer, currency, price, native parent `006` ID, or newly created Quote `a0P` record.
- These are **aggregate counts only**; no customer names, contact emails, CRM IDs, raw rows, quote numbers, customer prices, authenticated browser tokens or private data are committed to GitHub.

## Actual observed quote-name cases

| Classification | Cases |
|---|---:|
| Total Quote export rows inspected | 814 |
| Quote names containing PE250/250PE | 29 |
| PE250 Quote names with M reads only | 12 |
| PE250 Quote names with Gb only | 12 |
| PE250 Quote names mentioning **both** units | 2 |
| PE250 Quote names without a readable depth unit | 3 |
| PE150 Quote names | 61 |
| PE150 Quote names with Gb | 49 |
| PE150 Quote names with M reads | 0 |
| PMP + PE250 Quote names | 23 |
| PMP + PE250 with one distinct PMP token | 21 |
| Single PMP names with a numeric token immediately **before** PMP | 19 |
| Multiple PMP tokens requiring manual multi-service review | 2 |

### Time trend (Quote QID year)
- **2025:** 10 PE250 Quote names: 9 Gb-only and 1 unspecified; no M-reads-only examples in this export slice.
- **2026:** 19 PE250 Quote names: 12 M-reads-only, 3 Gb-only, 2 mixed and 2 unspecified.
- Paired Quote/Opportunity names among these 29 PE250 cases: 24 had the same nonempty set of unit tokens; 2 had a unit only on Quote Name; 3 had no unit on either. These are paired **names**, not independent scientific measurement.

This shows historical naming drift and prevents unsafe majority-vote training. It does not disprove the current owner-specified operational rule.

## Current field policy (explicit priority above historical names)
1. `PE250` and `250PE` normalize to **PE250**, and the input unit is **M reads per sample**.
2. Other supported PE/SE sequencing modes use **Gb per sample**.
3. Read depth and sample quantity are **different fields**. Never parse `250` as sample quantity or silently convert M reads to Gb.
4. A mixed-unit/mixed-service quotation, missing unit, an old PE250+Gb name, ambiguous count or non-supported sequencing mode is flagged for review rather than auto-corrected or guessed.
5. A lone numeric token immediately before a single `-PMP-` may suggest sample count, but remains **hint only** until confirmed against current request.
6. Never infer **reads vs read pairs**, existing Account/Contact identity, Business Entity, Promotion Type, Valid Thru, price, Stage, Close Date or native parent association from a historical name.

## Current user request — private preview only
- Service: PMP
- Sequencing: `250PE` → `PE250`
- Samples: 5
- Target depth: **1 M reads per sample**
- Nominal total: **5 M reads** across samples, not a pricing conversion or paired-read estimate
- Status: `DRAFT_REQUIRES_CONTACT_ACCOUNT_AND_QUOTE_REVIEW`
- Client email and the actual draft are stored exclusively in the authenticated Windows workstation's private `~/.sfdc_desktop` directory.
- No Opportunity or Quotation was created and Save remains prohibited.

## Implemented and tested
- `oppo_quote_case_learning.py`: case-name sequence-unit classifier, historical exception detection, conservative sample-count hint, aggregate-only case analysis, and present-day PMP web request schema.
- `test_oppo_quote_case_learning.py`: synthetic regression tests covering historical PE250 Gb drift, 2026 1M reads, PE150 Gb, dual services, ambiguous sample quantities and web draft rejection of wrong units.
- Windows full `automation/sfdc_desktop` tests: **356 tests OK, 2 skipped** (Windows symlink test restrictions), latest implementation commit `e48409f`.
- GitHub Actions `Salesforce Desktop RPA P0 tests`: run **41570193523 SUCCESS**.

## Next implementation gates
1. Build a CSS web entry surface with email, sample count, sequencing mode, and depth. Unit changes automatically based on exact normalized mode; preview shows no inferred customer or price.
2. Verify current Salesforce Contact by exact email, its intended Account and active duplicates; require reviewed Quote picklist values and quote item prices.
3. Only then, with explicit authorization, create the new Opportunity and read its **native Salesforce 006 ID**. Use that actual parent record ID to initiate a Research-AMEA Quotation, then verify the new `a0P` child and parent Related linkage and record the operation ledger. **Historical naming similarity is never sufficient.**
