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

## Follow-up execution: 10 more live Contacts
- Remote desktop reconnected, the redundant local Email-exact-match commit reconciled with the upstream branch (no force push), and the clean branch was synchronized.
- New resumable read-only batch tool: `resume_contact_alias_verification_private.py`, with atomic, local-only `contact_alias_attempts_PRIVATE.json` to prevent redoing completed checks on a retry.
- Next ten previously untested Contacts: **8 PASS_ALL_IDENTITY_CHECKS, 1 HOLD_ACCOUNT_RELATION_MISMATCH, 1 HOLD_CONTACT_DETAIL_DISPLAY**; Salesforce Save/Update/Create **0**.
- Total 48 Korean-name candidate Contact IDs from historical 180-Opportunity cohort: **15 independently verified, 5 HOLD, 28 not checked**. Success rate among reviewed Contacts 15/20 (75%), coverage 15/48 (31.25%). Never use 15/48 as a rate for all SFDC Contacts.
- The workstation private JSON now contains **15 verified aliases**, and the actual web module's strict local parsing and lookup recognized **15/15**. There are **12 distinct Korean name strings and 3 homonym groups**. Some same-name Contacts share an institution; native Contact ID remains mandatory to distinguish them.
- Explicit GitHub Actions Desktop three-pass regression: https://github.com/kimtk94/Codex/actions/runs/41824361609 (**SUCCESS**).
- Explicit web browser E2E workflow: https://github.com/kimtk94/Codex/actions/runs/41824684066 (**SUCCESS**).
- No personal data is copied into this document or GitHub.

### Next gates
- Continue the remaining 28 untested IDs using the resumable batch runner. Revisit the five HOLD IDs separately; never silently lower identity thresholds.
- The latest in-browser import is local JSON only. Authenticated real-time Salesforce search and web production rollout are separate unfinished steps.
