# Novogene CSS SIF Upgrade — Release Gate (2026-10-15)

> STAGING / DRAFT ONLY. Never merge this PR as an automatic deploy. No production source, SQLite, Google Sheet, schedule, or customer mail mutation is authorized.

## Change scope
- Existing server runtime: `/home/taehoon/services/novogene-css/app/Novogene_Mail_CSS_DashBoard_server.py`.
- Expected original SHA-256: `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840`.
- **Historical four-patch** staged SHA-256 (superseded): `851469d0aa53757fd55d5d31357d06068952d3983e79d8ee8b2d15ccb2cbf4fb`. **Current release candidate is seven patches; see latest gate below.**
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
| G07 | Latest offsite Drive project AND mail DB restore | PASS | [Drive checksum and independent restores](https://github.com/kimtk94/Codex/actions/runs/38643175074) |

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

## Consolidated preflight + production branch regression (2026-10-15)

- [Server-wide SIF release preflight](https://github.com/kimtk94/Codex/actions/runs/38644135441): **22/22 PASS**. Exact source hash, both patches staged, expected combined SHA `a42d8d5a80dbb8effa0a9598236d1ea37d90ad0c5616e726aac9b0bd3b42400d`, Python compile, preservation of **433** functions, byte-exact two-patch reverse, latest SQLite `quick_check`, FK check and five active skips. Source and live DB unchanged.
- [1,200-record real-main-branch regression](https://github.com/kimtk94/Codex/actions/runs/38644452604): **51/51 PASS**. Extracts the **exact Prepayment `if` branch from server's `main()` AST**, never calls `main()`. Ensures only Prepayment projects in `SIF requested` / `SIF revision required` are **removed from Active Dashboard/Action Center input**, no unrelated rows disappear, Sample QC projects stay included and stage advancement restores the row; repeats are idempotent; empty Prepayment set leaves input unchanged. Manual Hold/Skip collision and output retry tests remain PASS.
- Current live `overview_project_snoozes` had **0 rows** at preflight; this corroborates that no Prepayment snooze has been created in production yet. This is a pre-deployment baseline, **not** a user-state change.
- **Important product behavior:** Prepayment SIF projects will **not appear in Active Dashboard** while in SIF stage; the fix does *not* merely flip `attention=Yes` to `No`. Such projects should reappear when a subsequent QC / Library / Data stage occurs. Verify this is acceptable before approved rollout.
- [Detailed large-batch report](LARGE_SCALE_VALIDATION.md).

## Portfolio-visible SIF suppression — latest release candidate

- [43/43 portfolio/action integration checks PASS](https://github.com/kimtk94/Codex/actions/runs/38656873265) using **1,200 synthetic projects**, all three patches, exact main AST branch and output-builder arguments, QC re-entry, unchanged non-Prepayment attention, and byte-exact triple-patch rollback.
- [26/26 consolidated server release preflight PASS](https://github.com/kimtk94/Codex/actions/runs/38656996540) for the three-patch staged SHA `d675a490007a75c69b7fa408076879e9a52a1078bcc62a32f6fe093da0a32555`; live DB read-only `quick_check`/FK PASS and five Skip records. **Still no live deployment.**
- Updated policy: **Keep Prepayment SIF projects visible on Dashboard and in Customer 360 / Summary; mark their SIF attention No and exclude them from action-only inputs until QC**. This avoids portfolio undercounting in the earlier two-patch candidate. See [Portfolio Visibility Policy](PORTFOLIO_VISIBILITY_POLICY.md).
- The third patch does not authorize any production writes. **Business acceptance of display semantics remains an approval gate.**

## Production-safe action metadata refinement — four-patch candidate (2026-10-15)

- [**51/51 four-patch portfolio and action-source regression**](https://github.com/kimtk94/Codex/actions/runs/38657405886) on 1,200 synthetic projects: Dashboard / Customer 360 / Summary retain portfolio, SIF attention is No only on Prepayment SIF stages, **Action Center and Review Queue builders receive full portfolio context** to preserve independent mail/CRM/manual tasks and project metadata; QC recovery and all four reverse patches byte-exact.
- [**30/30 integrated server preflight PASS**](https://github.com/kimtk94/Codex/actions/runs/38657533752) for SHA `851469d0aa53757fd55d5d31357d06068952d3983e79d8ee8b2d15ccb2cbf4fb`; 433 original functions preserved, production source unchanged, live SQLite read-only quick/FK checks.
- The previous three-patch candidate SHA and tests remain historical evidence only, **not** the approved final artifact. The fourth patch is `novogene_sif_independent_actions.patch`. No actual end-to-end CRM/mail refresh has been run.
- [Policy rationale and limitations](PORTFOLIO_VISIBILITY_POLICY.md).

## Real Action Center and Review Queue generator regression (2026-10-15)

- [**23/23 real-generator assertions PASS**](https://github.com/kimtk94/Codex/actions/runs/38658186666): exact production CSS SHA checked, actual `build_action_center_output` and `build_review_queue_output` AST bodies executed with **1,200 synthetic projects** and stubbed effectful helpers. Output was **861 Action Center tasks**, **one review**, **342 active SIF Prepayment projects**, and **zero generic SIF tasks for those 342 projects**.
- On the **same Prepayment project**, an unanswered customer email and separate manual issue remained actionable. A Salesforce inquiry and a Quotation-Invoice review were retained. All task/review IDs were unique and deterministic across reruns.
- **Source-level regression demonstration:** Feeding the previously filtered dashboard to the *real generator* loses the unanswered inquiry's customer name (becomes `확인 필요`) and omits the Quotation-Invoice review's institution; feeding the full, SIF-attention-suppressed portfolio preserves them without increasing the number of tasks.
- These are real function bodies but **supporting mail, CRM, calendar, ID and merge helper implementations were stubbed** to ensure no outbound effects. It is not a full CSS main E2E or proof that every external connector state persists correctly.
- Action outputs were synthetic only; the production Action Center / Review Queue sheets were not written. See [script](real_action_review_generator_regression.py).

## Latest seven-patch gate — 2026-10-15

- **185/185 one-shot and two-process tests PASS:** 24 true two-process SQLite file/WAL race rounds, expiry/replay, read failures, manual Hold/Skip and receipt durability. [Actions](https://github.com/kimtk94/Codex/actions/runs/38660918748).
- **42/42 seven-patch read-only production-source preflight PASS.** [Actions](https://github.com/kimtk94/Codex/actions/runs/38661084055).
- **72/72 seven-patch 1,200-synthetic-record regression PASS.** [Actions](https://github.com/kimtk94/Codex/actions/runs/38661130690).
- **Historical seven-patch SHA-256 (superseded):** `2c45c940e35790944a1e0abde9b0312161e3b49a2b7d31993643d2d864fa338a`.
- Patch 7, `novogene_css_one_shot_receipts.patch`, creates SQLite `overview_control_receipts` to block stale identical Hold/Skip/Release inputs even after expiry. This **adds a table** when manual controls run, which must be accounted for in the migration and rollback plan.
- **UI acceptance needed:** to reissue identical Hold, clear both Action and Hold Days in an observed cycle, or Release then Hold. Editing the Hold duration while the current Hold remains valid is not currently a supported extension path.
- Actual Google Sheet edit-after-read synchronization and full CSS `main()` isolation remain unresolved. [Details](ONESHOT_7_PATCH_VALIDATION.md); [Issue 165](https://github.com/kimtk94/Codex/issues/165).

## Eighth patch: actual Google Sheets snapshot race hardening (2026-10-15)

- **[200/200 eight-patch manual/mail/SQLite/Sheets conflict tests PASS](https://github.com/kimtk94/Codex/actions/runs/38701293956)**, including synthetic edits before and after DB writes, one-shot receipt rollback, 24 genuine two-process file-based WAL race rounds and full reverse patch.
- **[46/46 eight-patch exact-source preflight PASS](https://github.com/kimtk94/Codex/actions/runs/38701555123)** with 433 original functions preserved, source unchanged, live DB query-only integrity/FK and byte-exact rollback.
- **[76/76 eight-patch 1,200-project regression PASS](https://github.com/kimtk94/Codex/actions/runs/38701659819)**.
- **[19/19 actual Google Sheets API Canary edit-race checks PASS](https://github.com/kimtk94/Codex/actions/runs/38702155598)**: dedicated synthetic tab was edited on the second and third `batch_get`. The real CSS sync function detected the changed snapshot, rolled back the corresponding synthetic snooze / receipt and committed only when the three reads remained unchanged.
- Patch 8 `novogene_css_snapshot_conflict_guard.patch` detects changes **between** observations, but **does not give Google Sheets and SQLite one atomic commit**. A change after the final read but before DB commit, or an A→B→A change between samples, remains a theoretical risk. Two extra Sheets API reads per cycle require quota/latency assessment.
- **Current eight-patch candidate SHA-256**: `3963b6cbd60205c2738943e4b28e2a88a1987776bfdda05ee8cba269d6ea3806`. Prior seven-patch SHA is superseded, not a current deployment artifact. [Full report](SHEET_SNAPSHOT_RACE_8_PATCH.md).

## Operational readiness — 2026-10-17 (read-only)

- [Server schedule/API budget audit PASS](https://github.com/kimtk94/Codex/actions/runs/39041451785): operating source SHA still matches baseline, project SQLite `PRAGMA quick_check=ok`, service user's crontab has **two jobs** (`*/10 * * * *` and `20 * * * *`), temporary storage available, no live source/DB changes.
- The current manual control synchronization reads Google Sheets controls via **one batch snapshot**; staged patch 8 makes **three snapshots** per invocation (two additional batch reads). At a nominal hourly CSS run, this implies **48 more reads/day** or **1,440 per 30-day month**. This is a **modelled request budget**, not measurement of actual requests nor proof that Google API quotas have sufficient headroom.
- Production `overview_control_receipts` **does not exist** yet, consistent with no schema deployment. The migration must be rehearsed against a cloned project SQLite and the table **retained after source-only rollback**.
- Monitoring and changes to schedules are **not** authorized. `main()` end-to-end / actual production Google Sheets write remains BLOCKED.
- The 2026-10-17 audit is the newest *operational* baseline; older fixture tests remain targeted verification, not current production acceptance.

## Unresolved release blockers
1. **Offsite backup restore completed:** Latest project and mail backups fully restored with independent checksum and integrity verification. Host-level disaster recovery is still untested; see verified section above.
2. **Production-equivalent full-engine canary outstanding:** Targeted actual SIF functions, actual Action Center/Review Queue generators, a 1,200-row real Canary Sheets write, and real Canary sheet edit races passed. The complete `main()` with every external client isolated **has not** been executed; no production deployment authorization is implied.
3. **Safe rollout approval + rollback rehearsal (eight patches):** Snapshot current source and live DB, ensure executable rollback is tested, then deploy only after explicit authorization.
4. **System service wrappers:** Confirm the `v8.92.1-server-local-adc` wrapper, systemd/cron schedules and 10-minute mail collector interactions before a controlled run.

## Backup retention — sampled dry-run only
- Initial sample was the **100 most recently returned files**; subsequently the entire backup folder was inventoried.
- 83 `mail_sync_fast` files, 17 `css_project_manager` files; sampled total **27.61 GiB**.
- Full Drive inventory: **984 backups / 271.69 GiB**, including 827 mail and 157 project backups. Tiered retention simulation protects 64 and identifies 920 files (about **258.82 GiB**) as *review-only* candidates. Actual deletion requires separate approval.
- **NO DELETE** before retention/RPO/RTO/whole-host recovery policy approval, last-two-by-type protection, and explicit age/size criteria. Never delete current raw databases, source data, or logs.
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
