# Korean Contact Lookup — authenticated local validation (2026-11-04)

## Progress and audited sample
- Source snapshots: 1,039 Opportunities; 1,013 in scope after the previously configured institutional exclusions.
- Historical 180-row Contact-link study: 136 ID/candidate matches, 42 IDs absent from the list, 2 HOLD. Those are historical evidence, **not** independent live confirmations.
- Within that historical 180-row cohort, 48 distinct Contact IDs had explicit Korean name labels eligible for fresh verification.
- **10 fresh live Contact checks attempted: 7 PASS, 3 HOLD_CONTACT_DETAIL_DISPLAY; 38 in this cohort still untested.**
- This represents 7/48 verified Korean contacts in the candidate cohort (14.6%), not full-population coverage.

## Independent read-only proof for all 7 PASS
For each PASS, the private workstation opened a live authenticated Opportunity Details page, clicked the exactly labelled Main Contact value to confirm the native Contact ID, then navigated the separately labelled Account value on both Opportunity and Contact to confirm the same native Account ID. The Contact Detail name matched the explicitly evidenced Korean display name, and its Email field matched the private Contact registry exactly.

- Private verified records: `~/.sfdc_desktop/private_verified_contact_details_evidence.json`.
- Browser JSON (restricted to verified records): `~/.sfdc_desktop/web_contact_aliases_PRIVATE.json`.
- Real browser parsing and lookup module read-back: 7/7 accepted, 7/7 exact Contact+Account matches, six distinct Korean names and **one same-name group with distinct Account IDs**.
- No customer identifiers, real names, addresses, emails or record URLs were uploaded to GitHub. No Salesforce Save, edits or new records.

## Evidence-quality correction
Older `oppo_linked_contacts_full_PRIVATE.json` grouped 400 Opportunities, claimed 360 ID_LINKS_VERIFIED, yet contained only six distinct Contact IDs and one distinct Account ID. Its global link collection method was not field scoped and is **not** accepted as 360 independently verified relationships. Do not use it to authorize Contact selection or CRM writes.

## Gaps and next verification
1. Review the three HOLD cases without relaxing identity standards; repeat readback if the Contact header is still loading or uses a different name presentation.
2. Validate the other 38 Contact IDs in the 48-ID Korean-name candidate cohort; then expand discovery beyond the original 180-Opportunity historical sample.
3. Confirm the GitHub branch and workstation share the same exact Email label-disambiguation helper; the verified local workstation patch may be ahead of the remote branch.
4. The web command presently imports private JSON in browser memory. Direct authenticated live Salesforce search and full web-to-PC command intake are not implemented; Salesforce Save remains disabled.
5. Approved price, Product, Business Entity, Promotion Type and Valid Thru remain separate Quote validation gates.

## Continuous integration
The desktop safety workflow was explicitly dispatched against feature branch `feat/sfdc-playwright-desktop-p0` and completed successfully:
https://github.com/kimtk94/Codex/actions/runs/41820846582

This CI validates synthetic regression and schema contracts; it cannot independently prove live Salesforce records.
