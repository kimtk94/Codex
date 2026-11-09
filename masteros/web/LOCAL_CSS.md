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
