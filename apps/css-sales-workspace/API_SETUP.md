# CSS private Google Sheets API setup

This app keeps the existing static navigation dashboard. The `/api/dashboard` endpoint is **read only**, and refuses requests without verified Google sign-in credentials. Never put credentials in Git or in browser JavaScript.

## Configuration for Vercel css-sales-workspace-git

1. Open Vercel > Project > Settings > Environment Variables.
2. Add `GOOGLE_SERVICE_ACCOUNT_JSON` as a **sensitive** server-only environment variable. Use the complete JSON credential for `novogene-css-server@novogene-css-automation.iam.gserviceaccount.com`. **Do not paste it into tickets, chats, Git, or client-side code.** If you use Workload Identity Federation instead of a JSON key, adjust `api/dashboard.js` credentials initialization.
3. Add `GOOGLE_OAUTH_CLIENT_ID`: the authorized Google OAuth **Web application** client ID, created in Google Cloud Credentials for this deployed site's domain (public client ID; not client secret).
4. Add `ALLOWED_OWNER_EMAILS`: comma-separated Google-account emails authorized to see this owner's data, starting with the owner's actual Google sign-in email. This must not be taken from client input.
5. Ensure Google Sheets API is enabled in `novogene-css-automation`.
6. Confirm the target spreadsheet grants access to the service account. It already has Writer permission; Viewer is sufficient for this API.
7. Deploy to preview. Without an OAuth ID token from an allowed Google account, requests return HTTP 401; wrong owner returns 403.
8. Configure the Google Identity Services browser sign-in widget later to obtain ID tokens and call `/api/dashboard` using `Authorization: Bearer <ID_TOKEN>`. **Don't send a service account credential to the browser.**

### Security
- This endpoint is intentionally inactive (`503 NOT_CONFIGURED`) until ALL THREE environment variables exist.
- Authorization enforces verified Google sign-in and an owner email allowlist.
- The sheet ID is server-side and not selected by the caller; other owners require an explicit server-authorized mapping.
- Limit exposed rows to the first 150 per sheet until data minimization and field-level redaction are reviewed.
- Never publicly expose mail bodies, personal contact details, invoice specifics, or bulk exports without additional minimization and auditing.
- Do not connect `index.html` to the API until Google Identity sign-in and correct owner access are tested.

### API response
Returns four capped tables: `unanswered`, `priority`, `leads`, and `health`. No data is loaded if authentication is missing.
