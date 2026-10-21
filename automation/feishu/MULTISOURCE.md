# Feishu multi-source integration (P0)
Target: Base table `표`, view `Taehoon`. P0 does not change Feishu.
- Existing Salesforce pipeline: `automation/sfdc/followup_stage1.py` reads Google Sheets tabs Salesforce Lead Tracker, Salesforce Enquiry Queue, Salesforce Engagements. This is not direct Salesforce API access.
- Email source is not connected to Feishu; emailed/sent state must be evidence-based.
- This preflight reads Feishu field/view metadata, prints field-type counts only, and stops without writing.
- **Write scope is unverified.** A successful read token does not establish permission for records.update/create.
- Before making a real diff: map source identifiers to Feishu field IDs/types, determine existing record ownership and view-scoped matching, verify sheet credential, and inspect anonymized mapping. Do not create records based on customer names alone.
- Future apply mode: explicitly authorized update/create scopes, dry-run review, guarded idempotency keys, no destructive deletes, and separately approved external email sends. Never print customer data or send diffs to public GitHub artifacts/logs.
- Environment: TaehoonServer (FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BASE_APP_TOKEN).
