# CSS mail automation: GitHub Actions (read-only bootstrap)

This is a deliberately isolated first stage. It does **not** replace the existing CSS
mail database, customer 360, quotation matching, SFDC pipeline, or Google Sheets jobs.

## Schedule
The GitHub Actions workflow runs at UTC minute 07 and 37 each hour
(Asia/Seoul minute 07 and 37), subject to GitHub Actions scheduling delays.
Manual `workflow_dispatch` is also available.

## Required repository Actions secrets
- `CSS_GMAIL_CLIENT_ID`: OAuth client ID
- `CSS_GMAIL_CLIENT_SECRET`: OAuth client secret
- `CSS_GMAIL_REFRESH_TOKEN`: refresh token for the authorized mailbox

Generate the refresh token with Gmail **readonly** scope:
`https://www.googleapis.com/auth/gmail.readonly`.
Never commit OAuth credentials or tokens to Git. Verify user/company authorization
before provisioning mailbox access. Only use tokens authorized for the CSS mailbox.

## Safeguards
- Uses only Gmail GET endpoints and OAuth refresh token endpoint.
- Counts inbox, unread inbox, and sent items across the previous 48 hours.
- No message bodies, addresses, subject lines, or attachments persisted.
- No messages sent, drafted, archived, deleted, or labeled.
- Workflow has `contents: read` permissions and does not change spreadsheets.
- Artifacts retain only counts (seven days).

## Integration stages
1. Confirm this read-only probe succeeds with authorized secrets.
2. Locate and migrate the existing CSS mail-sync code into a maintained module.
3. Implement incremental message ID/history checkpointing with private durable
   storage (e.g. restricted Google Drive/Sheets) and idempotent runs.
4. Restore existing CSS summary sheets, unanswered-email matching, quotation
   matching, invoice reconciliation, and optional SFDC references behind test gates.
5. Any customer-facing send must remain a separate explicit approval workflow.

Important: GitHub-hosted runners are ephemeral. Do **not** rely on local SQLite
persisting between workflow runs; checkpoint to authorized persistent storage.

## Verification
Run `python3 -m py_compile automation/css_mail/readonly_probe.py`.
Trigger the workflow manually after secrets are configured and inspect
the workflow result and sanitized `css-mail-metrics` artifact.
