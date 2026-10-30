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

## Central automation control tower

The existing owner-authenticated `/api/lifecycle` now projects two more
read-only Google Sheets sources into `automation` in its JSON response:

- `Automation Master Progress!A5:K55`: authoritative **baseline** task counts.
  A `done` task is **not** formally accepted until separate evidence is
  reviewed; the dashboard never upgrades it by inference.
- `Parallel Track Status!A1:G5`: four **CI-test** tracks (A Report/Lead,
  B Revenue, C SFDC desktop mocks, D web). `SUCCESS` means the listed test
  scope passed, not production CRM Save, cash receipt, or browser E2E.
- `Automation Health!A1:D60`: operational snapshots and unresolved review flags.

The control tower lives under the existing sidebar's **자동화 컨트롤 타워** view
and is only accessible through the same authorization checks as the rest of
the sales workspace. GitHub run links are restricted to the
`kimtk94/Codex/actions/runs/<numeric>` path; no arbitrary destinations.

Failure behavior: missing/invalid master or track data becomes
`available:false` with an explicit issue, without breaking the other
authenticated Sales views. All source records, manual Decision exclusions,
Invoice/Pending/Forecast classification, and source ownership are unchanged.

GitHub Actions remains the execution plane. Google Sheets remains the
operational data plane and audit ledger. Vercel is a protected presentation
plane. **No execution button, sales email sending or Salesforce Save is
enabled by this change.**

Offline smoke tests: `node --test test/*.test.js` from
`apps/css-sales-workspace`; CI automatically runs on changes to this app.
An authenticated end-to-end production browser acceptance test is still
required before treating web deployment as fully validated.

### Live GitHub Actions status source

`Automation Workflow Runs!A1:J20` is automatically maintained by the
`CSS Central Workflow Health Publisher` GitHub Action. It tracks ten
allowlisted `main` workflow filenames, twice hourly and after key workflows
complete. The protected CSS Web lifecycle API reads this tab alongside the
existing master and QA sources.

The UI distinguishes `PASS_EXECUTION_ONLY`, `FAILED`, `STALE`,
`IN_PROGRESS`, `NOT_RUN` and other inconclusive outcomes, and shows
actionable GitHub run links. Notably, a failed Feishu schema audit must NOT
be obscured by an unrelated or stale Feishu Health PASS. No client data is
contained in this status source.

## QQ checkpoint audit and Preview acceptance
The authoritative live mail stream is `CSS Git Ingest` and its
`folder|uidvalidity|imap_uid` checkpoint (e.g. INBOX|12345|678).
The legacy `All Emails` collection is retained as an archive/backfill source;
its old last received date must be separately reported as
`LEGACY_ARCHIVE_STALE_REVIEW`, not presented as a failure of the live IMAP stream.
A healthy live fetch timestamp alone is insufficient: the latest received mail
must also be recent, and all ingest keys must be well formed and nonduplicated.
The raw checkpoint GitHub job is included in the 12-workflow central console
status list. This is a read-only audit, not an importer or backfill.
Preview must pass unit tests and status-display regression before merging to
main. Production authentication and cash/SFDC acceptance remain separate gates.
