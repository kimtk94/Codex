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

## Consolidation status (2026-10-29)
**Canonical Vercel project:** `css-sales-workspace-git`; all other CSS Vercel projects remain rollback references, not production destinations.
- Project lifecycle, 2026-10 invoice actuals, pending Statements and forecast are unified in the authenticated `/api/lifecycle` read-only endpoint.
- Data sources are Google Sheets populated by the scheduled QQ IMAP + Feishu pipeline. The webpage refreshes its view every 5 minutes while open and authenticated.
- Production and Preview share the existing sensitive `CSS_WEB_ACCESS_TOKEN` **target setting**, without making the value public. Google credentials stay server-side. A new production deployment may be needed to apply updated environment targets.
- `css-operations-mvp` contains a standalone operations landing UI; its entrypoint remains linked from the canonical workspace while remaining capabilities are audited.
- `novogene-css-live-v4` contains an arbitrary Google Apps Script URL proxy. **Do not import** this endpoint into the canonical API without exact URL allowlisting, user authorization, and network access guards.
- `novogene-payment-draft` contains a QQ-IMAP/payment mail sending API. **Do not import or auto-send** from a dashboard without explicit recipient/attachment review and individual send approval.
- Old Vercel projects and domains are not deleted, redirected, or reconfigured until read-only and writing workflow parity is verified.
- Outstanding: verify Production API with a real authenticated user session and project SSO, move non-destructive operations UI into this workspace, implement approvals for any write/send action, and retire duplicate domains only after rollback tests.
