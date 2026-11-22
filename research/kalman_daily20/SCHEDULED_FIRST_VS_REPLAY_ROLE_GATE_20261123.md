# Daily20 scheduled first-vs-replay role gate — 2026-11-23

Research-only CI hardening. **Milestone progress remains 7/10 (70%); three scientific gates remain. No change to 2026-11-20 sealed events, live execution, models, market data or analysis thresholds.**

## Discovered failure mode

The original schedule has two independent runs each Tue-Sat UTC:
- `40 2 * * 2-6` (**Tue Nov 24, 2026 11:40 KST**): expected first capture following Monday Nov 23 U.S. close.
- `40 4 * * 2-6` (**Tue Nov 24, 2026 13:40 KST**): expected independent *second* same-session replay.

Previously both slots executed the same first-seal procedure. If the 02:40 run failed, queued, never started, or never published Drive evidence, the 04:40 run could create **the first 60 forward events** and misleadingly leave a successful scheduled run although an independent replay had never happened. Even a future missed publisher cache could produce a delayed first seal in the wrong slot.

## New fail-closed behavior

`next_session_two_pass_contract.decide` now accepts an exact `--schedule-slot` value from `github.event.schedule`, restricted to the two published cron expressions or empty (for manual dispatch/main pushes).

- **02:40 first slot, genuinely newer XNYS session:** must be `FIRST_GENUINE_SEAL_EXPECTED`, with no existing 20+40 cohort and valid post-close +45min/next-open admission window. Unexpected incomplete or prior future-dated evidence is a hard failure.
- **04:40 replay slot for Nov 23 and future XNYS sessions:** must have a **fully signed original 20+40 event cohort, original frozen 26/420/40/60 snapshot, and previous pinned Drive archive session exactly equal to this trading date**, produced by a *different GitHub Actions run*. If any element is missing, preflight raises `TWO_PASS_SCHEDULED_REPLAY_WITHOUT_VERIFIED_FIRST_SEAL` or `TWO_PASS_REPLAY_MUST_USE_DISTINCT_ACTIONS_RUN` **before either forward writer**. It will **never** compensate by inventing a delayed first seal.
- **Market holiday/non-new date:** the 02:40 slot is permitted to verify an already closed session with 0 new events; e.g. Thu Nov 26 Thanksgiving, run Fri Nov 27 UTC 02:40 sees Wed Nov 25 as latest complete XNYS day. No phantom new trading day. The 04:40 slot still requires actual prior original snapshot and a prior independent run.
- **Manual dispatch / protected-main push:** no first/second scheduled role is inferred. The original time-aware prospective admission and immutable journal rules still apply; such a run may seal a valid unsealed new day but cannot be described as a successful two-slot scheduled pair.
- The **postflight** rejects a changed cron expression between pre/post reports, prohibits the 04:40 slot from adding signals, verifies exact prior journal byte prefixes and all older snapshot SHA256s, and leaves source/factor scientific certification at HOLD.

New CI regression cases cover the failed 02:40 / attempted 04:40 backfill, missing original input snapshot, stale prior session metadata, first run from same Actions ID, a verified second run, invalid cron strings, Thanksgiving no-new-session behavior and pre/post role swap. The existing 426 tests and independent PR scope/write guards remain mandatory.

## What success does not prove

- A green manual/push run over 2026-11-20 proves only that the **existing** 60-event cohort was not rewritten. It does not certify Nov 23 first signal or generate the missing 2026-11-20 original 21-feature model input.
- GitHub scheduled events are best effort and may be delayed or absent. A failed/missed first run is **not automatically retried as a scientifically valid replay**.
- Independent official closes 0/26, corporate factors 0/25 and four-XNYS-session prospective settlements continue to be HOLD.
- **Never re-seal or backfill** first-pass research events after the next market open; never promote live trading based on a green contract-only run.
