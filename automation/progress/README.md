# Progress tracker (read-only)

Proposed on feature branch. Runs once daily at 09:15 KST (00:15 UTC) and manually after merge, without modifying Salesforce, Sheets, CSS or QQ Mail.

Run offline: `python automation/progress/tracker.py --offline`
Test: `python -m unittest discover -s automation/progress -p 'test_*.py'`

Uses the canonical 50-row Markdown master ledger. GitHub PR/Actions evidence is gathered via read-only REST APIs, recent first 100 PRs/runs (older entries can be absent). Matching is based on manually curated PR candidate mapping, **never automatic completion**. Optional service account checks target Google Sheets tab metadata only. For secret availability: `CKD_DRIVE_SA_JSON` or `GOOGLE_SERVICE_ACCOUNT_JSON`. Do not log auth data. Missing optional Sheets credentials is NOT_CHECKED, not PASS.

Outputs two workflow artifacts: report.json and report.md. Historical status weighted progress is separate from strict operational acceptance, which must be signed with E2E evidence and is not calculated yet. No users' manual decisions or business amounts are written.

Expected P1 follow-up: add approved task-to-gate map, record verified acceptance evidence, and publish to a dedicated Sheet tab only after read-only QC and a separate write authorization. 
