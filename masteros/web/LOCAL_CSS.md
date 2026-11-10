# Local CSS project dashboard (private)

Run on an authorized Windows PC with the existing private Google service-account credentials and Node.js. This website binds **only** to `127.0.0.1`. No Vercel or public hosting is required.

## Quick start

```powershell
cd "$env:USERPROFILE\Codex\Codex-SFDC-Git\masteros\web"
npm install
npm run build
.\scripts\start-css-local.cmd
```

Then open `http://127.0.0.1:3000/sales/projects`. Reuse an existing process rather than starting a second server on the same port.

## Read-only data path

1. GitHub Actions builds the isolated `WEB_EXPORT_V4` sheet in the private `Novogene_All_Emails` spreadsheet, using the `SFDC_Automation_Followup_2026` Google Sheet mirror as source.
2. The local Next.js API `/api/css/projects-local` starts a local Python read-only check and compares original **Google Sheets mirror** rows with the V4 destination, field by field.
3. The client shows explicit `PASS_MIRROR_ONLY`, `SINK_LAG`, `STALE`, or `SOURCE_UNAVAILABLE`. The website does **not** treat a successful HTTP request or updated display time as authenticated original Feishu/QQ freshness.
4. Identifiers use project/subproject ID as the primary key; AMEA is secondary. Contact names, emails, raw mail bodies, and credentials are not part of the dashboard projection.

If a PC has Google credentials at `%USERPROFILE%\CSS_Automation\credentials\service_account.json`, local Python uses the existing file. Otherwise, set `GOOGLE_APPLICATION_CREDENTIALS` to an authorized service-account JSON **path**. Never commit credential files or put their contents into Next.js client environment variables. The GitHub secret `CKD_DRIVE_SA_JSON` is used only by Actions for the upstream mirror refresh.

The endpoint requires an explicit `CSS_LOCAL_PROJECTS_ENABLED=1` and `X-CSS-Local-Projects: 1` on loopback, rejects other origins, and is GET-only. Client and source readbacks are no-store. No SFDC Save, Feishu write, financial certification, or internet-facing server exists in this feature.

## Checks

```powershell
python -m unittest discover -s scripts -p test_css_projects_local.py -v
node --test tests/css-projects-local.test.mjs
npm run build
```

**Live operational proof** also needs a real Google auth read and independent source-to-sink row count and field parity, performed locally. Synthetic CI success alone is not data freshness certification.


## Mail and Lead review (loopback-only)

Open `http://127.0.0.1:3000/sales/mail` in the **same authorized Windows PC**.
The existing `start-css-local.cmd` now enables this private interface.

- **Unanswered review**: uses the existing `Novogene_All_Emails / Unanswered Reply Review 60D` source and its canonical IMAP keys, sorted/filterable by priority, sender, recipient role and project.
- **Skip one mail**: after an explicit confirmation, append one `SKIP_MAIL` decision to the existing `Unanswered Reply Decisions` ledger; restore from the web UI.
- **CC rules**: select a verified To-recipient or exact sender from an inbound email where the owner's address is in Cc but **not** in To. Rules are stored in the existing `Unanswered Reply Routing Rules` ledger and never affect mail directly addressed to the owner. Restore from the web UI.
- **Lead sent history**: reads the existing `SFDC_Automation_Followup_2026 / Lead Sent Dates` table; searches by lead name, institution, email or ID. First and last sent dates, actual To/CC counts and source status are displayed.
- No new Google Sheets workbook, no email sent, no remote hosting, no Salesforce write, no mail deletion. Only explicit review-ledger append/restore actions write to Google Sheets.
- Google credentials remain server side in `%USERPROFILE%\\CSS_Automation\\credentials\\service_account.json` or an existing `GOOGLE_APPLICATION_CREDENTIALS` **path**. The service account needs write permission for the two QQ decision ledger tabs. Never put its JSON into client-side variables.
- `CSS_LOCAL_MAIL_ENABLED=1` and `CSS_LOCAL_MAIL_OWNER=taehoon.kim@novogene.com` are set only by the local startup script. API access requires 127.0.0.1 host, a same-origin request and `X-CSS-Local-Mail: 1`.
- If source metadata is stale, the web UI disables new review actions and shows source freshness explicitly.

### Offline checks

```powershell
cd "$env:USERPROFILE\\Codex\\Codex-SFDC-Git\\masteros\\web"
python -m unittest discover -s scripts -p test_css_mail_local.py -v
node --test tests/css-mail-local.test.mjs
npm run build
```
