# BI Mail Review Sync — GitHub CI authentication

## Verified on 2026-10-24
- PR unit tests passed.
- PR read-only integration check failed before calling Google Sheets:
  `Missing GOOGLE_SERVICE_ACCOUNT_JSON (or GCP_SA_KEY) secret`
- PR CI run: https://github.com/kimtk94/Codex/actions/runs/40070201354
- No production ledger writes were attempted.
- PR remains draft. Scheduled jobs remain dry-run after merge, unless explicitly changed.

## One-time setup
1. Use an existing dedicated Google service account with access to the source spreadsheet, or create one in an authorized GCP project with Google Sheets API enabled.
2. Share the spreadsheet `Novogene_All_Emails` with that service account email as **Editor**, using the existing sharing controls. Do not change other sharing permissions.
3. In `kimtk94/Codex` > Settings > Secrets and variables > Actions > New repository secret, create `GOOGLE_SERVICE_ACCOUNT_JSON` with the complete service-account JSON key. **Do not commit or send the key in chat.**
4. Re-run the CI check on the draft PR, confirming the read-only probe passes.
5. Test specific exclude/restore transitions against an isolated non-customer UID before opting into writes. Check old exclusion rows, new rows, and idempotency.
6. Only then approve live sync and merge. The workflow's schedule currently uses `DRY_RUN=true`, so it will not write until explicitly enabled.

## Rules
- Reviewer edits happen in `BI Mail Review & Exclusions`, UID keyed.
- Existing `Unanswered Email Exclusions` and `Unanswered Sender Exclusions` are historical records; avoid deletion.
- Never turn off dry-run solely to test access.
- Review any other CSS jobs that append or rewrite the same tab; workflow concurrency only serializes runs from this workflow, **not other workflows**.

## Future CI improvement
Consider Workload Identity Federation with GitHub OIDC rather than long-lived service-account keys if the Google Cloud environment permits it. This needs separate GCP trust and IAM setup.
