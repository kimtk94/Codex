# SFDC full Opportunity / Quotation snapshot audit (read-only)

## Scope and provenance

Authorized Windows PC `NGKR-SAL-TH`, private Salesforce snapshots originally enumerated 2026-11-03 and newly cross-checked on 2026-11-04. Full list enumeration is **not the same as opening and independently validating every existing record live**.

- In-scope Opportunities: **1,013**, with KAIST/Hannam excluded.
- Fully enumerated Quote-list IDs: **862/862** unique, 16-column rows, no reported list cap.
- Single-Product Quote manifest: **412** unique Quote IDs, all members of the 862-Quote list.
- Other or not-yet-classified Quotes: **450**. These are retained for manual processing, not silently included in automation training.

## Entire 1,013-Opportunity Contact linkage

| Contact candidate relation from existing name-based list | Opportunity count |
|---|---:|
| One candidate Contact ID, still pending live proof unless separately verified | 926 |
| Two same-name Contact candidates; institution/Contact ID selection required | 43 |
| Contact name not found | 44 |
| **Total** | **1,013** |

Approved native Contact–Account–Opportunity links at this audit: **132 distinct Contacts / 132 distinct Opportunity IDs**, with zero conflicts against the Opportunity candidate roster and zero approved records missing full identity flags. **881 Opportunity rows still lack independently verified Contact links**. These figures do not imply all 1,013 have an eligible Contact.

Contact program:
- Original Korean-name candidate cohort: 48 reviewed, 38 approved and 10 HOLD.
- Expansion from the historical 180-Opportunity source: 195 new unique Korean Contact candidates; 118 reviewed, **94 PASS**, **24 HOLD**, **77 unreviewed**.
- Total approved native Contacts **132**; total unresolved Contact HOLD **34** (10 original + 24 expanded).
- The web's private approved alias JSON contains only verified native Contacts. No customer name, email, institution or Salesforce ID was copied into GitHub.

## Entire 862-Quote reconciliation

**412 single-Product historical quote records:**
- 390 historical `006` parent references exist in the 1,013-Opportunity snapshot; 22 absent from that in-scope list.
- For those 390 rows, name of the Opportunity matches the indexed Opportunity name in 390/390, while Contact label matches in 381/390; 9 label mismatches/missing.
- 311 distinct parent Opportunity IDs appear across the 412 quote rows. 72 parents have multiple Quote rows, accounting for 173 Quotes.
- Statuses: Ready to send 332; Need to submit 70; Draft 9; Rejected 1.
- Historical Oppo-name policy parsing finds 13 explicitly PE250-labeled cases: 8 compatible with the current M reads-per-sample rule, **5 historical conflicts**. Other names that do not specify sequencing mode cannot authorize a guessed unit.

**450 non-training/unclassified Quote records:**
- Statuses: Ready to send 334; Need to submit 89; Draft 25; Rejected 2.
- Opportunity name uniquely matches one in-scope Opportunity in 329 cases, matches no in-scope Opportunity name in 89, and matches multiple Opportunity names in 32.
- None of these 450 has a live native parent Quote relationship established by name matching alone; they remain manually handled according to the user's workflow.

## Strict same Oppo–Quote learning shortlist

Across **all 862 Quotes and 1,013 Opportunities**, require one Product on the Quote manifest, exact Opportunity name match, exact Contact display-label match, Opportunity name unique in 1,013, and only one Quote having that Opportunity name anywhere in 862. Result: **177 structural 1:1 candidates** (Ready to send 158; Need to submit 19).

For these 177:
- **40** had an independently verified native Contact–Opportunity link when the shortlist was generated.
- All **40/40** were then opened in authenticated Salesforce: existing Opportunity Related Quotation list was 1:1, its exact native `a0P` Quote ID matched the expected historical Quote, and the Quote's labelled parent Opportunity `006` matched the expected record. **40 native-parent checks PASS, 0 HOLD**.
- The other 137 structural candidates do **not** receive native-parent PASS without independent live evidence.
- This validates historical pair identity for learning. It does **not** approve new Opportunity/Quote creation, historical price reuse or current Product catalog identity.

## Product, Pricebook and web restrictions

- Existing Quote line's native Product2 ID and parent Quote were rechecked in 3 read-only rounds in a previous stage. That verifies the original saved Product relation only.
- Existing Product2 Details and Product Template UI did not supply independent current PricebookEntry or current price evidence. On one Quote the Add/Edit action was present but disabled; six different preexisting Quotes across Draft, Need to submit and Ready to send showed enabled Add/Edit. No force click, Save, Pack or product creation.
- Current PricebookEntry, approved price, Quote Product/Process configuration, mandatory fields, duplicate check and authorized Save remain **HOLD**.
- User's local PC-only Next.js Oppo–Quote workspace now shows an **all-record aggregate audit bar**. It reads only whitelisted counts from the PC's private snapshot reports; customer IDs, names, emails and prices never leave the PC. The new local endpoint is disabled by default on hosted Vercel.
- Local browser smoke: HTTP 200, exact displayed totals (1,013 Opportunity, 862 Quote, 177 structural candidates, 132 approved Contacts, 40 native Quote parent PASS), CRM writes 0, Save disabled.
- Salesforce production records modified: **0**. Production web deployment: **none in this audit**.

## Private evidence and repeatable commands

Local-only files under `~/.sfdc_desktop`:
- `full_oppo_quote_snapshot_reconciliation_PRIVATE.json`
- `all_opportunity_contact_reconciliation_PRIVATE.json`
- `one_to_one_oppo_quote_learning_shortlist_PRIVATE.json`
- `one_to_one_quote_native_parent_verified_PRIVATE.json`
- `web_contact_aliases_PRIVATE.json`

Committed scripts:
- `audit_complete_sfdc_oppo_quote_snapshot_private.py`
- `audit_all_opportunity_contact_snapshot_private.py`
- `audit_one_to_one_oppo_quote_shortlist_private.py`
- `verify_one_to_one_quote_native_parents_private.py`

GitHub CI checks synthetic safety, schema, and web browser E2E without using or exporting private Salesforce records. Future work: verify remaining 77 new Contact candidates and re-review 34 HOLDs; verify the other 137 structurally eligible Oppo–Quote parents as permitted by independently verified Contact sources; inspect Quote Product/Pricebook and approved current prices before any future separately authorized Save automation.
