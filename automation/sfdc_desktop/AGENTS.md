# Salesforce operator desktop automation

**Read [SFDC_OPERATOR_RULES.md](./SFDC_OPERATOR_RULES.md) before modifying any file in this folder or any related SFDC web worker.** User decisions are binding and supersede assumptions made in legacy helper scripts.

Mandatory: existing Contact-first Opportunity and newly created Opportunity Related-first Quotation; retain exact names; identify by 003/001/006/a0P native IDs, not by name uniqueness; use user-selected `Quote Issued` Progress Description, never default `Quote Draft`. Quote Issued alone is not proof of customer email delivery. Verify current 2026 native KRW Product/Process, quantity, Pack, fees, Cloud, VAT; source and target readbacks must agree.

No save without per-record current source evidence, approval, one-use nonce, immutable journal and independent readback. GitHub Actions only synthetic/read-only. No CRM writes from CI, no secret/customer data in Git, no Vercel. If native UI workflow differs from recorded rules, HOLD and document exact evidence instead of improvising.

After each change, run `python3 -m unittest discover -s automation/sfdc_desktop -p 'test_sfdc_operator_contract.py' -v` from repository root plus the existing Python/JS SFDC suites. Update operator contract and tests together with explicit user rule changes.
