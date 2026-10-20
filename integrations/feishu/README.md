# Feishu Wiki Base — read-only connection probe

Target: Wiki node `BUHTwWF5GidC3ekjWmEcMYFhnZc`, table `wbpD7kQYkQ`.

## Security
- This is a **manual** `workflow_dispatch` connectivity test. No cron, edits, exports, uploads, data persistence, or Google Sheets integration.
- App credentials must be stored in GitHub Actions secrets `FEISHU_APP_ID` and `FEISHU_APP_SECRET`. Never add credentials to this repository or logs.
- Repository is public; only stage flags and sanitized numeric error codes are logged. No records, field values, or tokens are printed.
- The Feishu app needs tenant authorization and access to the exact target Base. Wiki-node resolution may require a separate Wiki read scope (for example `wiki:wiki:readonly`) in addition to Base read permissions.
- Do **not** export company data to external services without organization approval.

## Procedure
1. Ensure the Feishu app is released and granted only the minimum necessary read scopes and target Base authorization.
2. Add both secrets to repository **Settings → Secrets and variables → Actions**.
3. After merging this PR, open **Actions → Feishu read-only connection probe → Run workflow**.
4. Expected flags: `CONFIG_OK`, `AUTH_OK`, `WIKI_BASE_RESOLVED`, `FIELDS_READ_OK`, `RECORDS_READ_OK`, `PROBE_PASS`.
5. On failure, share only the sanitized stage/error code. Do not share credential or raw API responses.

Read-only API operations: tenant token issue, Wiki node lookup, Bitable fields list and records list (one record requested, content discarded).
