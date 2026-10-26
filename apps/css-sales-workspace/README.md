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
