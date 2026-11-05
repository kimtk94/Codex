# Oppo–Quote Web Command MVP — 2026-11-03 KST

## Verified stage
- Historical Oppo / Quote patterns learned; owner-specific current data rule: PE250 → **M reads/sample**; other supported PE/SE modes → **Gb/sample**. Old PE250+Gb entries are historical review exceptions, never auto-converted into current draft values.
- User's requested PMP 250PE 5 samples × 1M reads/sample exists as a **private Windows-only draft**, not a CRM record.
- Live Salesforce Quotation **New Research-AMEA** form previously audited and Cancel-tested; Opportunity/Quotation Save is not authorized for any unverified customer.
- Exact email lookup in **three connected SFDC Contact sheets** returned zero matches, but a **live authenticated Salesforce Contacts → Recently Viewed list search** found **one row with the user's exact email**, containing **one 003 Contact link and one 001 Account link**. The target Account is a Kyungpook National University NGS core support-center entity, not inferred only from email domain. The native IDs, real name and email are stored **only in private Windows evidence files**. Clicking into Contact detail encountered a console-navigation timeout, so **independent detail verification and all-list duplicate checking remain HOLD**. Do not create an additional Contact or automatically pick the Account yet.

## Web implementation
- `masteros/web/app/sales/oppo-quote/page.jsx`: Next.js client-only command form, not a Salesforce writer. Inputs: customer email, service (PMP), sequencing mode, integer sample count, numeric depth per sample. Displays canonical total depth and current unit policy.
- `masteros/web/lib/sfdc-oppo-quote.mjs`: strict schema validation and draft JSON with all CRM write permissions explicitly false. Does NOT infer Account/Contact, price, Stage, Close Date, Quote options or reads-vs-read-pairs.
- `masteros/web/app/sales/oppo-quote/page.module.css`: responsive sales workspace.
- `masteros/web/tests/sfdc-oppo-quote.test.mjs`: 12 Node unit tests for PE250 vs PE150 depth units, quantity, invalid email, privacy, missing fields and no-Save.
- `.github/workflows/sfdc-oppo-quote-web-preview.yml`: GitHub Actions Node 22 test + Next.js build, with no Salesforce access, tokens or customer records.
- Main MasterOS dashboard navigation links to the new route.

## Privacy/security
- Web form initially has **empty customer email**. Browser-only React state. No POST endpoint, server storage, Salesforce API request or GitHub Actions customer-data dispatch is implemented.
- "Generate review command" shows JSON for local review/copy only; **Salesforce create button remains disabled**.
- Actual customer email and SFDC Contact identity must remain in authorized private systems; do not paste personal data into public repo PRs or CI logs.

## Build and deployment verification
- GitHub Actions: **SFDC Oppo-Quote web preview (no CRM writes) #41577184115 SUCCESS**.
- Other same-commit checks: **MasterOS CI #41577184246 SUCCESS**, Salesforce Desktop RPA tests #41577184272 SUCCESS, Vercel monorepo scope CI SUCCESS.
- Source SHA: `806e2498aa630d3c564682011d5f6817b5aecc60`, branch `feat/sfdc-playwright-desktop-p0`, PR #263.
- Separate, SSO-protected Vercel project `sfdc-oppo-quote-preview` was created. Deployment `dpl_Aka2RxtdVcAPbDdQYW9gx4mNdqt5`: **READY**; page route:
  `https://sfdc-oppo-quote-preview.vercel.app/sales/oppo-quote`.
- **Isolation:** This is a distinct project from the existing `css-sales-workspace-git`; its settings and Production deployment were NOT changed. Vercel labels the first deployment "production" *within the separate preview-named project*, despite using a non-main feature SHA; it is SSO-protected for ALL deployment targets. Do not claim it is a live CRM command endpoint.
- Browser E2E behind SSO is not yet verified independently; READY + Next.js build confirm successful deployment/build, not identity-linked UI execution.

## Next mandatory gates
1. Secure, authenticated private draft intake from web → authorized local workstation. Do not put raw customer email in GitHub Actions workflow_dispatch payloads; without that route, user can only generate/copy a draft.
2. Current Salesforce Contact exact email + Account record ID lookup; duplicate Opportunity / Quote detection; price and Business Entity / Promotion Type / Valid Thru review; sample read-vs-read-pair clarification if materially affecting quote.
3. Only after exact identity and written approval: create Opportunity, read native Salesforce `006` and business `Opp-` IDs, use verified parent for Research-AMEA Quote, create child, read native `a0P` plus QID, independently confirm Related/Quote relationship and ledger. Unknown results HOLD; never auto-retry Save.

## Current result
**Web command draft UI: implemented, built and SSO-deployed. Salesforce Opportunity/Quotation creation: NOT DONE.**
