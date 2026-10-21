# CSS QQ Mail integration (read-only bootstrap)

This module uses QQ Mail **IMAP**, not Gmail OAuth. It is a separate,
non-destructive first stage and does not replace existing CSS summary or matching jobs.

## Actions secrets
- `CSS_QQ_MAIL_ADDRESS`: authorized full QQ Mail account address
- `CSS_QQ_MAIL_AUTH_CODE`: QQ Mail IMAP/SMTP authorization code (not the normal login password)

Open https://mail.qq.com/ and select Settings > Account >
IMAP/SMTP Service to enable IMAP and generate an authorization code.
Account security requirements may require confirmation.

Never commit authorization codes or real mail contents to GitHub.
Tencent Exmail IMAP: `imap.exmail.qq.com:993` with TLS. SMTP is intentionally NOT used.

## Operation and limitations
- Manual trigger or GitHub schedule at UTC minutes 07,37 (KST minutes 07,37).
- Uses IMAP EXAMINE/SELECT readonly and UID SEARCH; no read of bodies, subjects,
  sender addresses, or attachments, and no mutating commands or mail sending.
- Date-only IMAP SINCE is a broader range than the requested rolling 48h interval.
- Sent folder path is provider-dependent; a folder-not-found marker is reported,
  not treated as proof that there were no sent messages.
- No private mailbox data committed; sanitized aggregate count artifact kept 7 days.
- GitHub runner files are ephemeral. Migrate historical CSS SQLite state only
  with authorized persistent storage and audited idempotent checkpoints.

## Next steps
1. Set the two Actions secrets and manually test this workflow.
2. Find the existing CSS ingestion scripts and retain their data contracts.
3. Add controlled incremental IMAP UID fetch with UIDVALIDITY checkpoint,
   idempotent matching, and private durable Google Drive/Sheets storage.
4. Reconnect CSS Customer 360, unanswered mail, quotation/invoice matching,
   SFDC and Feishu derived views after staged verification.
5. Outbound email remains a separately approved operation, not part of this job.
