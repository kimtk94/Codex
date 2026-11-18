# SFDC automation: mandatory operator contract

Before changing any Salesforce-facing API, UI, draft/queue, pricing or Save code in this directory, read **`../../../automation/sfdc_desktop/SFDC_OPERATOR_RULES.md`** and run its 20-rule change-control checklist.

**Established workflow:** existing native Contact `003` and its matching Account `001` → **Contact-origin** New Opportunity → independently verified newly created Opportunity `006` → its **Related** → New Quotation → uniquely verified new `a0P`. Never silently replace this with Opportunity List/New or Quotation List/New. Retain the exact Opportunity/Quote name; repeated names are allowed and native IDs identify records.

**Description convention:** newly generated Oppo–Quote Progress Description uses **`Quote Issued`**, not `Quote Draft`. This internal wording is not evidence of customer email delivery; maintain separate delivery evidence.

**All other standing rules:** 2026-only native KRW price and Process/Pack source, existing customer-first price preference, 10% VAT with net Opportunity Amount, verified AliCloud/Data release, unchanged name, 1-month Close Date KST, newly composed description, separately verified fees, no guessed PO/SIF/receipt, user approval and journal/readback before Save. GitHub Actions synthetic only, Salesforce writes only on authenticated operator laptop, no Vercel.

**Before merging:** run `python3 -m unittest discover -s ../../automation/sfdc_desktop -p 'test_sfdc_operator_contract.py' -v` from `masteros/web`, `npm run test:sfdc`, the web preview workflow, and live read-only operator-laptop checks. A mismatch or unverified Contact-first native action must return HOLD, not switch to another entrypoint or claim success.
