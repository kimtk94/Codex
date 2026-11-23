# Daily20 missing-both-scheduled-runs heartbeat — 2026-11-23 KST

**Current implementation milestone 7/10 (70%); three scientific acceptance gates remain.** Scientific and LIVE promotion stay HOLD. No first new Nov 23 U.S. session was sealed at the time this change was authored.

## Failure mode closed

The existing Daily20 research workflow has two *independent GitHub scheduled* entries:
- **02:40 UTC, Tue–Sat**: 11:40 KST, first post-close 20 Bull + 40 Bear forecast seal of a genuinely new XNYS session;
- **04:40 UTC, Tue–Sat**: 13:40 KST, 0 new forecasts and immutable replay of the first original.

PR #996 blocks a 04:40 run from manufacturing a late first seal if 02:40 failed. But the ordinary `workflow_run` ops monitor **cannot trigger at all if neither Daily20 run is created**. A missing first *and* missing second run would therefore produce no regular operational monitor event, and a manual/push run might otherwise be mistaken for real scheduled completion.

## Independent heartbeat workflow

`.github/workflows/kalman-daily20-slot-watchdog.yml` runs **twice** on its own GitHub schedule, at **06:25 UTC (15:25 KST)** and **07:25 UTC (16:25 KST)**, Tue–Sat. The second check provides another opportunity if the first heartbeat itself is skipped. Each run is separate from the actual model pipeline, with `contents: read`, `actions: read`, and **no Drive, broker, account, or mutable repository credentials**.

It calls the GitHub REST API for **the exact Daily20 workflow, main branch, `event=schedule`, and current UTC day**. It does *not* count successful push, manual dispatch or pull-request runs as scheduled first seals. It reads job metadata and the bounded relevant original **daily-research** and **persist-google-drive** logs, discarding log text after extracting only whitelisted evidence. The restricted GitHub log URL redirect code reuses the existing `ops_readiness.safe_job_log`; repository token is never forwarded to blob-storage URLs.

Required for PASS:

1. Exactly one original scheduled **02:40** and exactly one original scheduled **04:40** run, identified by their emitted `github.event.schedule` log evidence. Distinct Actions run IDs, chronologically ordered, and identical code SHA.
2. Both complete **all four** jobs successfully: contracts, restore-drive-cache, daily-research, persist-google-drive. Incomplete, failed, missing, or log-unreadable runs cannot satisfy the heartbeat.
3. The expected latest completed XNYS date matches both runs. On a genuine new session, 02:40 records `FIRST_GENUINE_SEAL_EXPECTED` and **60** new events; 04:40 records `SAME_SESSION_REPLAY_EXPECTED` and **0** new events. On exchange holidays, a prior already recorded XNYS session can be replayed **0/0**, never fake a trading day.
4. The actual **postflight** emits the matching date/role/count, original Drive **media** readback must say `READBACK_VERIFIED`, and each run's original first-seal proof must contain a current valid 26/420/40/60 snapshot.
5. Independent 04:40 proof must point to the original run and the **same original SHA-256 snapshot** as 02:40. On new days, the first proof's original Actions ID must equal the 02:40 run, while the second must prove that ID is earlier than its own.

The watchdog writes a compact **research-only JSON report** and GitHub Actions job summary. On failures it produces **a red workflow run** (native GitHub Actions notifications according to account/repository settings) with explicit classifications such as `BOTH_SCHEDULED_SLOTS_MISSING`, `MISSING_FIRST_SLOT`, `MISSING_SECOND_SLOT`, `SECOND_POSTFLIGHT_MISSING_OR_WRONG_COUNT`, `CODE_SHA_CHANGED_BETWEEN_REPLAYS`, and `INDEPENDENT_REPLAY_DID_NOT_PRESERVE_ORIGINAL_SEAL`. `if: always()` uploads the JSON as a 90-day artifact even if the audit fails. It never silently treats a network timeout, GitHub API error, unsafe log redirect or missing evidence as PASS.

**Limitations:** GitHub schedules are best effort. Because this heartbeat is also hosted by GitHub Actions, a GitHub-wide outage or a skipped pair of heartbeat schedules **cannot** be detected by GitHub alone. Independent off-GitHub monitoring would be a separate task. The heartbeat checks the *presence and integrity of emitted evidence*, not whether Yahoo prices are exchange-certified, whether issuer split/dividend factors are verified, or whether a trading model has positive alpha. It **never alters** market data, the research first-seal journal, Drive archives, model parameters, or real orders.

## Next execution dates (KST)

For US Monday **Nov 23, 2026** session:
- Tue **Nov 24 11:40**: intended original capture;
- Tue **Nov 24 13:40**: intended independent replay;
- Tue **Nov 24 15:25**: first heartbeat, expected both complete;
- Tue **Nov 24 16:25**: second heartbeat.

The earliest 2026-11-20 cohort 4-XNYS-session settlement is after the Fri Nov27 U.S. close. For 2026-11-23 first prospective cohort, maturity is after Mon Nov30 U.S. close (Thanksgiving Nov26 is not an exchange session).

## Reproduction

`cd research/kalman_daily20 && python -m unittest -v test_scheduled_slot_watchdog.py`

Synthetic offline tests prove missing both, missing either, wrong dates, first/second source mismatch, 0/60 count regression, missing remote SHA, GitHub job failure, holiday replay, stale runs, duplicate runs and inaccessible original evidence all fail closed. PR tests do not make actual prospective signals or evaluate historical trading performance.
