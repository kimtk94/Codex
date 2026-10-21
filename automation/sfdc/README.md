# SFDC API-free Follow-up Automation — Stage 1

**Status:** code ready on feature branch. Scheduled execution needs merge to default branch and credential verification.

## Source and output
- Source: Novogene_All_Emails (private, read-only).
- Source tabs: Salesforce Lead Tracker, Salesforce Enquiry Queue, Salesforce Engagements.
- Output: separate private spreadsheet SFDC_Automation_Followup_2026.
- Frequency: at minute 07 and 37 of each hour (UTC); approximately every 30 minutes. GitHub cron can be delayed.
- No Salesforce API required. No automated Salesforce writes, email sending, or activity creation.

## Setup
1. Give the Google service account **Viewer** access to the source spreadsheet and **Editor** access to the output spreadsheet.
2. Use existing GitHub Actions repository secret `CKD_DRIVE_SA_JSON` to the service-account JSON (single-line or multiline JSON accepted). Do NOT commit it.
3. Merge this branch into `main`, then trigger the workflow manually once to verify the output. Scheduled workflows only run from the default branch.
4. Check action logs (counts only), output sheet records, and permission scope.

## Scoring logic (provisional)
- Follow-up candidates are Lead Tracker rows with `needs_action=yes` and open enquiries with `mail_sent_after_enquiry` not confirmed yes.
- Same SFDC `record_id` is deduplicated.
- Priority score starts at 50, adds up to 30 for age, 15 for new enquiry, subtracts 8 for missing email.
- 85+: urgent; 70–84: high; otherwise normal.
- "Unknown" sent-email state means **verification required**, never confirmed unsent.
- Engagement records are auxiliary context, never proof a customer was contacted.
- Outputs are suggestions, not verified Salesforce state.

## Safety
- Existing source workbook is never modified.
- Do not share the output spreadsheet publicly; it contains customer contact data.
- Secret missing => workflow skips instead of failing.
- Any 403 likely means service-account sharing or Google Sheets API access needs repair.
- If unexpected large result size, keep record privacy and review limits before modifying.
