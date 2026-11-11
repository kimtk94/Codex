# CSS serverless migration: phase 1

This PR adds a **read-only** scheduled inventory. It does **not** update mail, Sheets, or project databases and does **not** remove backups.

## Setup
- In GitHub repository settings, add Actions secret `NOVOGENE_CSS_GCP_SA_JSON` containing the existing Google service account JSON. Never commit credentials.
- Share the Drive folder `Novogene_CSS/server_backup` with the service account email as **Viewer**.
- After merging, use Actions > CSS Drive Backup Audit (read only) > Run workflow and check its inventory artifact. Scheduled checks run at 00:17 and 12:17 UTC.

## Why not enable updates yet?
- Source is stored in Google Drive: `Novogene_CSS/src/Novogene_Mail_Collector.py` and `Novogene_Mail_CSS_DashBoard.py`.
- These programs call `google.colab.drive.mount()` and rely on `/content/drive` plus runtime prompts; they cannot run unmodified on GitHub Actions.
- State files in `Novogene_CSS/state/` are SQLite databases; replacing them without concurrency controls, verified recovery point, and atomic publish risks data loss.
- Backup folder currently contains hundreds of snapshots, often at 10-minute intervals. File size alone cannot prove byte-identical data.

## Subsequent changes (separate reviewed PRs)
1. Refactor collector and dashboard into unattended entrypoints without Colab imports or interactive prompts; keep business logic unchanged.
2. Use explicit IMAP secret + Google SA (Drive/Sheets access), avoid printing secrets or private mail.
3. Implement exclusive job concurrency, latest validated Drive DB fetch, `PRAGMA quick_check` and transactional local processing; publish through a staging/verify/replace design with a recoverable prior version.
4. Enable mail ingestion schedule no faster than its actual runtime; dashboard after collector success, no external email sends.
5. Retention: keep latest validated full backups and sampled daily/weekly/monthly restore points; generate a deletion manifest and verify before moving excess snapshots to trash.

Security: never push SQLite files, mail messages, credentials, or customer details to GitHub or Actions artifacts.
