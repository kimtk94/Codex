# SFDC Contact/Quote read-only follow-up — 2026-11-04

## Expanded Contact cohort

Authorized workstation NGKR-SAL-TH, Salesforce authenticated Chrome read-only. Original historical Opportunity inventory 1,013 in-scope, 362 Opportunity rows mapped to 209 exact Korean-labelled Contact candidates, 195 candidates not among the 14 overlapping existing approvals.

Previously approved 58 unique Contacts (38 original + 20 expansion). This turn:
- First 12 new Contact checks: 9 PASS, 2 HOLD_CONTACT_DETAIL_DISPLAY, 1 HOLD_ACCOUNT_ID_DIFFERENT.
- Second 10 new Contact checks: 7 PASS, 1 HOLD_TimeoutError, 1 HOLD_CONTACT_DETAIL_DISPLAY, 1 HOLD_ACCOUNT_ID_DIFFERENT.
- New pass this turn: 16, new holds: 6.
- Total original approved: 38. Expanded approved: 36. **Total approved: 74 unique Contacts.**
- Expanded candidates reviewed: 44/195 (36 PASS, 8 HOLD); 151 unreviewed.
- Original 48 cohort HOLD: 10 separate from 8 expansion HOLDs. Total unresolved Contact HOLD: 18.
- Two transient timeout HOLDs from expanded cohort were retried strictly using the new retry tool. Both remained HOLD_TimeoutError. Neither was promoted; no source identity rules relaxed.

Web local private JSON matched **74/74** independently approved Contacts, 70 distinct Korean name strings and four same-name groups. Name+institution+Contact ID suffix labels had zero collisions; some homonyms share institutions so the Salesforce Contact ID is mandatory. Customer identifiers and private records never uploaded to GitHub.

## Code and safety

- expand_korean_contacts_private.py now rejects Contact IDs with inconsistent Korean display labels across Opportunity rows, even if one row matches a Contact name list. Synthetic tests pass.
- retry_transient_contact_holds_private.py only retries explicit transient UI errors; Contact name, email and Account ID discrepancies remain HOLD. Synthetic tests pass.
- 3-round saved Quote product/process UI reference re-audited live: 3/3 rounds PASS, 10/10 expected read-only checks per round, no Salesforce Save.
- quote_product_reference_readonly.py distinguishes **historical product reference verified** from **current Product catalog ID/PricebookEntry/current pricing** (all unverified). Never creates new Product or authorizes Save. Synthetic tests pass.

No CRM writes. No automatic Opportunity/Quote new creation. No current approved price, Product2 catalog identity or pricebook claim.

## Remaining

1. 151 untested unique expanded Contact candidates.
2. 18 Contact HOLD cases (10 original + 8 expanded), including two persistent timeout HOLDs; investigate Salesforce session/UI stability without relaxed identification checks.
3. Hosted Vercel's authenticated, read-only Salesforce search is still not connected. The Windows loopback web is functional and verifies Contacts with a local authenticated Salesforce browser; hosted features remain no-Save.
4. Existing Product catalog / PricebookEntry, current Quote pricing, required fields, duplicate opportunity/quote evidence remain separate Save gates.

Follow up by continuing read-only live Contact verification in small batches with synthetic CI and by first proving native existing Product/PricebookEntry relationships before any Quote price-authorization workflow.
