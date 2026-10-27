# CSS Sales Workspace

Git-managed, owner-scoped navigation for the CSS sales dashboard.

## Deployment
- Vercel root directory: `apps/css-sales-workspace`
- Framework: Other (static HTML)
- Production branch: `main`; deploy PR branches to Preview first.
- User-facing data is **not** published by this app. Navigation links open authenticated Google Sheets.
- Initial owner: `kim-taehoon`; sheet ID: `1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI`.

## Data access roadmap
- Implement Google Sheets API via server-side credentials with user authentication and owner authorization **before** enabling any private data endpoint.
- Never bundle service-account private keys or mail contents into HTML, environment responses, or Git.
- Service account `novogene-css-server@novogene-css-automation.iam.gserviceaccount.com` already has spreadsheet access. Its email is not an authentication credential.
- Preserve existing email exclusion decisions and avoid duplicating raw emails into web.
- Ensure each owner can access only their authorized spreadsheet.
- On Vercel use project environment settings for Google credentials, never repository files.

## Verification
Open the deployed preview, check each of five category groups, and confirm links open the intended tabs without bypassing Google account permissions. Existing CSS production deployment is not replaced by this PR.

## Mail reader repair (2026-10-27)
The active preview branch is `feat/css-web-native-data-20261027`; main still holds the earlier navigation hub. The mail list defaults to a compact sender/subject/age view with a keyboard-accessible reading drawer. Search and age filters apply to the loaded server page.

`CSS Web Mail Body Sync` fetches only current Unanswered queue messages through read-only IMAP BODY.PEEK and writes their text to the private `CSS Mail Inbox Raw` cache. It validates UIDVALIDITY and Message-ID against CSS Git Ingest, preserves review decisions, and logs counts only. Runs on demand/on this repair branch push; the 30-minute schedule becomes active once merged to main.

The historical fallback uses IMAP UID in column R plus inbox key in T; column A is a different local sequence. Only identifier columns are scanned, then one matching row including body_1 through body_13 is read. Pending source bodies are explicitly labeled.

Validation: `node --test apps/css-sales-workspace/test-data.cjs` and `python automation/css_mail/test_web_body_sync.py`. Vercel Deployment Protection must remain enabled for the preview data endpoint.

## Uploaded proposal review (2026-10-27)
Selectively integrated bounded server search (first 5,000 data rows, explicitly labeled), accessible page-local numeric/text sorting, batched header/data reads with lookahead pagination, KST current-month calculation, missing KPI warnings, dedicated app credentials, and graceful optional Feishu failures. The uploaded auth replacement is not enabled: it needs an OAuth client/session secret and its domain-wide authorization is broader than this single-owner workbook. The uploaded historical UID lookup and index string-replacement patch are intentionally not used because they regress the corrected reader and target an obsolete frontend. Existing Vercel access restrictions and uncached current-queue membership checks remain.

Run `node --test apps/css-sales-workspace/test-*.cjs` for all twelve API regression tests.
