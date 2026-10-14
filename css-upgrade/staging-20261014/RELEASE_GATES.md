# Novogene CSS SIF Upgrade — Release Gate (2026-10-15)

> STAGING / DRAFT ONLY. Never merge this PR as an automatic deploy. No production source, SQLite, Google Sheet, schedule, or customer mail mutation is authorized.

## Change scope
- Existing server runtime: `/home/taehoon/services/novogene-css/app/Novogene_Mail_CSS_DashBoard_server.py`.
- Expected original SHA-256: `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840`.
- Staged candidate SHA-256: `125a0ec6ba9733660deb3828d073777d8912a19965155e58f5e16b7b4e4f367c`.
- Fix source of Prepayment follow-up suppression: permanent active SQLite skips rather than the 30-day `CSS Contract-SIF Skipped` view.
- Create a read-only `CSS Contract-SIF Skip History` tab with no edit/restore checkbox. Existing manual flags and 30-day tracker retention are unchanged.

## Evidence / completed
| ID | Gate | Result | Evidence |
|---|---|---|---|
| G01 | Server source fingerprint, AST, 433 existing functions retained | PASS | [Stage](https://github.com/kimtk94/Codex/actions/runs/38584294699) |
| G02 | Current production SQLite read-only decision cross-check | PASS | Active Skip = 5; Prepayment = 3; History = 5; [run](https://github.com/kimtk94/Codex/actions/runs/38590208433) |
| G03 | Shadow in-memory SQLite Prepayment create/release lifecycle | PASS | 3 created, 1 released on QC; manual Hold/Skip preserved; [run](https://github.com/kimtk94/Codex/actions/runs/38590606713) |
| G04 | Independent Google Sheets synthetic output 5/3 + readback | PASS | [Canary](https://docs.google.com/spreadsheets/d/1eKMPMnRYeZB8tuPE2dblcSaHXSZ58REHPQgJSq2RIjA/edit) |
| G05 | Actual server ADC gspread write to **canary only** | PASS | [run](https://github.com/kimtk94/Codex/actions/runs/38595199510) |
| G06 | Current live SQLite snapshot -> temporary DB restoration and integrity | PASS | [run](https://github.com/kimtk94/Codex/actions/runs/38595531615) |
| G07 | Historical offsite Drive project DB restore | PARTIAL | Historical 21:24 KST project DB restored, integrity PASS, latest/mail backups outstanding |

## Additional isolation findings — verified 2026-10-15

- [Production AST inventory](https://github.com/kimtk94/Codex/actions/runs/38637725484): 584 main call sites, 205 unique callees, 25 dataframe-to-sheet write sites. Counts are static call sites.
- [Module import boundary inventory](https://github.com/kimtk94/Codex/actions/runs/38637952229): CSS module can install dependencies on import; mail collector has 139 top-level call expressions including SQLite/Sheets/Drive effects, without a canonical `__main__` guard.
- [Synthetic fail-closed guard](https://github.com/kimtk94/Codex/actions/runs/38638413462): 19/19 tests PASS (production Sheet ID rejection, temp-path/symlink rejection, import side effects, and full-main refusal).
- [Real-server import/main block check](https://github.com/kimtk94/Codex/actions/runs/38638533644): CSS import, mail collector import, and full-main are blocked by the test policy; operational modules are **not actually imported or run**.
- See [isolation matrix](ISOLATION_MATRIX.md) for all required sink interception and network isolation. **Passing the guard tests does not imply the complete pipeline is isolated.**

## Large-batch integration upgrade (verified 2026-10-15)

- New **manual override collision**: on the SAME project, automatic Prepayment `skip_prepayment` previously overwrote user mode `hold` or `skip_until_new_mail`. A narrow second patch now excludes manually controlled projects from the automatic snooze writer; separate dashboard Prepayment follow-up suppression remains active.
- [1,200 synthetic project scenario CI](https://github.com/kimtk94/Codex/actions/runs/38640063806): **39/39 assertions PASS** including both patches applied in sequence and **byte-exact reversal**. Combined staged SHA-256: `a42d8d5a80dbb8effa0a9598236d1ea37d90ad0c5616e726aac9b0bd3b42400d`.
- [1,200-row actual Google Sheets writer load CI](https://github.com/kimtk94/Codex/actions/runs/38639854155): **PASS**. Dedicated synthetic Canary tab stored 1,200 unique IDs, 400 Prepayment flags; actual engine data-frame writer second identical call skipped; manual QA unchanged. Google Sheets connector independently re-read all rows.
- These tests cover selected *real SIF functions*, not full CSS `main()`. New manual-state preservation should be a mandatory rollout acceptance criterion, not merely a shadow fixture.
- [Detailed large-batch report](LARGE_SCALE_VALIDATION.md). A formal dual-patch bundle and a full E2E isolation gate remain pending.

## Offsite restore and full backup policy completed (2026-10-15)

- [Drive project **AND mail** offsite recovery PASS](https://github.com/kimtk94/Codex/actions/runs/38643175074): both newest backups copied with existing rclone credentials; MD5 matched Google Drive, `integrity_check` and foreign keys PASS before/after isolated SQLite restore, source/restored row counts agree. Project: 26 tables, 40,444 ledger / 4,777 timeline; Mail: 3 tables, 40,444 messages.
- [Full 984-file Drive backup retention analysis](https://github.com/kimtk94/Codex/actions/runs/38643111610): 271.690 GiB stored; hourly/daily/weekly/monthly model protects 64 copies (12.872 GiB) and marks 920 copies (258.818 GiB) for **review only**. **No deletion or remote write**.
- [Full restore and inventory report](OFFSITE_BACKUP_RESTORE_FULL_INVENTORY_20261015.md).
- **No additional Google Drive folder permissions** were granted. Existing authorized rclone was used.
- Latest individual project and mail backup restore condition is now **PASS**. Operational disaster recovery of an entire host, backup retention approval and a production application rollout remain separate tests.

## Unresolved release blockers
1. **Offsite backup restore completed:** Latest project and mail backups fully restored with independent checksum and integrity verification. Host-level disaster recovery is still untested; see verified section above.
2. **Production-equivalent engine canary:** Execute the patched output code against a cloned isolated DB and separate spreadsheet without touching the main Google Sheet or production sender; check source writes, skip history output, dashboard follow-ups, and manual state preservation.
3. **Safe rollout approval + rollback rehearsal (two patches):** Snapshot current source and live DB, ensure executable rollback is tested, then deploy only after explicit authorization.
4. **System service wrappers:** Confirm the `v8.92.1-server-local-adc` wrapper, systemd/cron schedules and 10-minute mail collector interactions before a controlled run.

## Backup retention — sampled dry-run only
- Scoped to the **100 most recently returned files** in the Drive `server_backup` folder, **not entire backup history**.
- 83 `mail_sync_fast` files, 17 `css_project_manager` files; sampled total **27.61 GiB**.
- With a one-per-hour representative plus latest-two policy, 65 mail DB files (about **20.57 GiB**) enter *review candidacy*. No CSS project DB file from the sample enters candidacy.
- **NO DELETE** before offsite restore PASS, coverage across entire backup inventory, last-two-by-type protection, and explicit age/size retention criteria. Never delete current raw databases, source data, or logs.
- Longer-term retention proposal: hourly 24h; daily 14d; weekly 8wk; monthly 6mo. Adjust after inventory.

## Controlled production deployment — not authorized yet
1. Verify current server source SHA, DB/Sheets health, existing Prepayment state, and version.
2. Generate tested, timestamped read-only snapshot; keep a byte-exact copy of runtime source in a private backup location.
3. Apply patch to temporary directory; `git apply --check`, `ast.parse`, and run regression suite; **do not put `set -e` in server scripts**.
4. Replace source **only** via controlled atomic swap after explicit authorization and deploy window check.
5. Run a single CSS cycle; verify health SUCCESS, History exactly matches DB, 3 Prepayment false follow-ups suppressed, legitimate QC actions retained, and manual Hold/Skip preserved.
6. On failure restore **source only** from the byte-exact backup; do not blindly roll the database back because it may discard newly synchronized mail. Restore DB only for proven corruption under separate authorization.
7. Monitor multiple cycles and confirm the next normal scheduled execution succeeds before changing backup retention.

## Output privacy
- The publicly accessible GitHub PR contains only a minimal patch, staging workflow, and aggregated test evidence.
- No client emails, private credentials, raw SQL databases, or customer-level exported history may be committed.
