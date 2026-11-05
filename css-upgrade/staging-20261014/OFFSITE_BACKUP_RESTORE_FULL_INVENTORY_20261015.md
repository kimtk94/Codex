# Novogene CSS — Latest Offsite Backup Restore & Full Inventory (2026-10-15 KST)

**Verified: Both newest Drive backups were downloaded through the server's existing rclone remote, checked against Drive MD5, and restored into disposable SQLite databases. No original backup deletion.**

## Actual remote and access policy
- Existing production backup upload wrappers: `bin/run_mail_collector.sh`, `bin/run_css_dashboard.sh` use rclone.
- Authorized remote folder: `gdrive:Novogene_CSS/server_backup`.
- Existing rclone config was used **for read-only download and inventory**, without changing Google Drive folder-sharing permissions or expanding the service account.
- Offsite backup files remain on Google Drive. Temporary local downloads and restored copies were removed when the test ended.

## Latest complete offsite restore — PASS
| Check | Project DB | Mail DB |
|---|---|---|
| Drive filename | `css_project_manager_20261015_062412.sqlite3` | `mail_sync_fast_20261015_063014.sqlite3` |
| File bytes | 85,024,768 | 340,410,368 |
| Google Drive MD5 vs local | PASS | PASS |
| Source SQLite full integrity | PASS | PASS |
| SQLite foreign key check | PASS | PASS |
| Restored SQLite full integrity | PASS | PASS |
| Restored row counts vs source | PASS | PASS |
| Table count | 26 | 3 |
| Key rows | `contract_sif_skips=5`, `mail_ledger=40444`, `project_timeline=4777` | `messages=40444`, `metadata=1` |

Evidence: [Offsite Mail + Project Restore GH Action](https://github.com/kimtk94/Codex/actions/runs/38643175074).

Important: This is **restore capability for the two selected latest offsite files**, not proof that an entire disaster-recovery process (network/DNS/OS/services/secret provisioning) has been rehearsed. No live source/DB/Scheduler/Google Sheets was updated.

## Complete remote backup inventory (not 100-file sample)

As of scan on 2026-10-15 KST, full rclone folder enumeration yielded **984 files / 271.690 GiB**, all from October 8–15, 2026.

| Type | Files | Size, GiB | Proposed protected copies | Protected GiB | Review-only candidates | Review GiB |
|---|---:|---:|---:|---:|---:|---:|
| Mail | 827 | 259.432 | 33 | 10.428 | 794 | 249.004 |
| Project | 157 | 12.258 | 31 | 2.444 | 126 | 9.814 |
| **Total** | **984** | **271.690** | **64** | **12.872** | **920** | **258.818** |

Evidence: [Full Backup Inventory and Retention Dry-Run](https://github.com/kimtk94/Codex/actions/runs/38643111610).

Dry-run tiers (no delete script involved):
- Protect **latest two files per DB type**, even if same hour.
- Most recent 24 hours: **hourly** representative.
- 24 hours to 14 days: **daily** representative.
- 14–56 days: **weekly** representative.
- 56–183 days: **monthly** representative.
- Older: keep one annual anchor (requires separate historical policy approval).

**Review candidate ≠ safe-to-delete.** This is a model over filenames/timestamps, not proof every non-selected backup is fully redundant. Before any deletion, confirm RPO/RTO, minimum historical daily coverage, legal/customer data retention, special event preservation, 2 independent full restores, at least one immutable external copy, and a rollback window. No files were removed.

## Deployment gate changes
- **G11 / Latest offsite project DB:** PASS.
- **G13 / Latest offsite mail DB:** PASS.
- **Backup retention:** audit PASS; actual cleanup **NOT AUTHORIZED**.
- **SIF patch technical check:** original + manual-override patch, 1200-record/39-assertion regression PASS; 1200-row Sheets canary PASS.
- **Still OPEN**: fully isolated whole CSS `main()` E2E covering all mail, Drive, CRM, error paths and live service overlap, or an explicitly approved narrow SIF-only controlled rollout; production deployment authorization, monitored cycles and rollback staging.

## Do not mistake these for a live deploy
At the time of testing, the production Google Sheet still showed three Prepayment SIF false follow-ups because the SIF upgrade patch had not been installed on the live engine. This report does **not** change that state.
