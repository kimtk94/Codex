# SFDC Contact expansion + one-click PC web readback (2026-11-04)

## Live CRM data coverage
- Existing Salesforce Opportunity inventory: 1,039 rows; 1,013 in-scope after KAIST and Hannam institutional exclusions.
- Beyond the original 180 Opportunity sample: 362 Opportunity rows with explicit Korean-name Contact candidates, 209 distinct Contact IDs.
- Fourteen overlap prior approved Contacts; 195 new candidate Contact IDs.
- First 12 new live checks: 10 PASS, 1 UI timeout HOLD, 1 Email identity HOLD.
- Next 10 new live checks: 10 PASS.
- Total newly approved 20; previously approved 38; **58 approved unique Contacts**.
- New untested 173; new HOLD 2. Older cohort HOLD 10 remains separate.
- Actual local web parser: 58/58 approved aliases searchable, 55 Korean names, 3 homonym groups, 0 name+institution+ID-suffix display collisions.
- For any Contact with multiple Opportunities, only the Opportunity independently live checked is approved.
- No Salesforce Create, Update or Save.

## Web implementation
Local address: http://127.0.0.1:31889/sales/oppo-quote on NGKR-SAL-TH.

Browser selection: Korean name -> institution + Contact identity -> PMP mode + sample quantity and per-sample depth -> private review packet. New read-only action: 이 PC에서 Salesforce 신원 재확인.

This action makes one POST to the *PC-local* route /api/sfdc/review-local, not a Salesforce write. Only a Windows, opt-in, loopback-bound, same-origin, JSON browser request with a user-initiated custom header is accepted. The route runs the local Python validator with --live-readonly and deletes a temporary request file. No Contact details are echoed into GitHub, cloud logs or URL query strings. The endpoint is disabled on Vercel.

The live validator now reads the entire **independently approved private Contact evidence**, not only the obsolete historical 180-Opportunity sample. This was necessary to support expansion. Actual browser smoke: local query -> exact Contact choice -> local live CRM link verification PASS, Salesforce write requests 0. Prices, Products and quote duplication remain HOLD and Save stays disallowed.

## Private workstation evidence
- .sfdc_desktop/private_verified_contact_details_evidence.json
- .sfdc_desktop/expanded_contact_alias_attempts_PRIVATE.json
- .sfdc_desktop/web_contact_aliases_PRIVATE.json

The repo contains implementation and synthetic tests, never customer identifiers.

## Deployment state and next work
Feature branch feat/sfdc-playwright-desktop-p0 (PR #263). The last directly verified Vercel Preview reached READY at dd9f3dc9; one-click live review changes were run and verified on the local PC and CI. Do not claim latest cloud deployment without matching commit.

Remaining: 173 new expansion candidates, 2 new expansion HOLDs, 10 earlier HOLDs; separately design a properly authenticated Salesforce read-only integration for the remote Vercel web. No Production promotion or CRM saving was performed.
