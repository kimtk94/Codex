# Live Policy Replay V1

## Purpose

Research-only replay of the **current Kalman live exit stack** against the frozen historical `FIXED_4` ledger.

This code is intentionally separate from production scheduling. It does **not** edit cron, Vercel, Neon, Toss credentials, live environment values, or current automation.

The objective is to answer:

> If the current live position manager had observed historical minute data on the same watcher cadence, would its risk exits have improved the frozen FIXED_4 outcome?

## Core design

The replay uses the same pure exit-policy contract as production:

- stop-loss priority
- take-profit priority
- profit-to-loss pending exit
- model-rotation priority slot
- max-hold priority slot

The profit-to-loss state transition is also shared with `ManagedPositionStore`.

This removes the most important source of research drift: duplicated policy logic.

## Current live profit-flip state machine

Default live parameters are loaded from the server environment at run time and frozen into `policy_snapshot.json`.

Current contract:

1. Track peak return after entry.
2. Arm when peak return reaches `AUTO_TRADE_PROFIT_FLIP_ARM_PCT`.
3. Count consecutive observations at or below `AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT`.
4. Set `PROFIT_TO_LOSS_FLIP` pending after the configured confirmation count.
5. While pending, historical add-on blocking is audited.
6. At an executable regular-session watcher tick, revalidate the latest available price.
7. If return recovered above `AUTO_TRADE_PROFIT_FLIP_RECOVERY_PCT`, clear pending.
8. Otherwise execute the risk-reducing exit in the replay.

## Cadence reproduced

The research scheduler mirrors the committed KST watcher cadence without invoking cron.

### Position watcher

- every 30 minutes from 09:00 through 21:30 KST
- one additional 22:00 KST observation
- weekdays only

### Execution watcher

- every five minutes from 22:25 KST
- continues through 05:55 KST next day
- weekdays / next-morning continuation matching the deployed cron pattern

The executable market window is evaluated in `America/New_York`, so DST and standard-time shifts do not require hard-coded KST market-open assumptions.

## No-lookahead price semantics

Historical one-minute bars are indexed with binary search.

At watcher time `t`:

- decision/fill proxy: minute **open at or immediately after** `t`, with a strict three-minute tolerance
- entry/fixed-4 reconstruction: last completed minute close strictly before the effective hourly-bar close

The replay never uses the close of a minute that had not completed at the decision timestamp.

## Data source and caching

Default data source:

- Alpaca historical 1-minute bars
- default feed: `iex`

Cache:

`/mnt/gdrive/US_ETF/directional_research/live_policy_replay_1m_alpaca_v1`

The cache key contains symbol plus exact UTC fetch range. In-process use is bounded by an LRU cache to avoid retaining every historical window in memory.

Useful modes:

- normal: cache hit first, then fetch missing windows
- `--refresh-cache`: force refetch
- `--cache-only`: never make a network request; missing files fail closed

## Feed-bias control

The frozen historical `net_return` remains authoritative.

For a replay-triggered exit:

`candidate_net = baseline_net + weight * (vendor_candidate_raw - vendor_fixed4_raw)`

This is the same paired same-feed delta principle used by the existing open-revalidation study.

The vendor feed is therefore used to estimate only the **counterfactual timing delta**, not to replace the original strategy return.

## Coverage policy

Missing overnight data is **not forward-filled**.

The replay records separately:

- total watcher coverage
- daytime position-watch coverage
- execution-watch coverage
- regular-session executable coverage

A candidate cannot become a research survivor unless data coverage passes strict gates.

This is deliberate. A result based on incomplete overnight observations should fail closed rather than silently assuming that no state transition occurred.

## Model rotation

The current replay requires `AUTO_TRADE_MODEL_ROTATION_ENABLED=false`.

If rotation is enabled, the run stops because an exact historical replay requires a point-in-time eligible-signal stream. It will not silently pretend rotation was absent.

## Add-ons

V1 does not synthesize historical add-on purchases because the frozen FIXED_4 ledger does not contain the new live add-on decision stream.

The replay does audit how often `exit_pending_reason` would have blocked a same-symbol add-on.

A future version can ingest a point-in-time add-on event ledger without changing the state engine.

## Outputs

Default output:

`/mnt/gdrive/US_ETF/model_lab_v1/results/live_policy_replay_v1`

Files:

- `status.json`
- `policy_snapshot.json`
- `live_policy_replay_trade_audit.parquet`
- `live_policy_replay_event_audit.parquet`
- `live_policy_replay_decision.json`
- `live_policy_replay_fold_summary.csv`
- `live_policy_replay_reason_summary.csv`
- `live_policy_replay_attribution.csv`

The attribution table decomposes the paired P&L delta by exit reason, including
trade count, aggregate baseline/candidate net return, total delta, mean delta per
trade, and positive-delta rate.

The trade audit stores one row per baseline trade.

The event audit defaults to `changes` mode and stores state transitions, exit-due events, and executable regular-session checks without writing every missing tick.

Use `--event-audit full` only for detailed forensic review.

## Statistical gate

The replay reuses the existing paired daily log-return bootstrap and fold comparison methodology.

Research-survivor requirements include:

- paired 95% CI lower bound > 0
- one-sided bootstrap p <= 0.10
- positive paired folds >= 60%
- MDD deterioration no worse than 2 percentage points
- baseline/replay-ready coverage >= 90%
- median watcher coverage >= 80%
- median regular-session execution coverage >= 95%

A survivor receives only:

`PROSPECTIVE_SHADOW_ONLY`

Never automatic production promotion.

## Pilot

After the branch is checked out on the server:

```bash
cd ~/Codex

sudo KALMAN_ENV_FILE=/opt/kalman/.env \
  bash kalman-toss-gateway/scripts/run_live_policy_replay.sh \
  --max-trades 20 \
  --backfill-only
```

This verifies:

- live environment policy snapshot
- Alpaca credentials
- exact KST watcher generation
- DST-safe execution window
- cache write/read
- entry/fixed-4 reconstruction
- observation coverage

## Full pre-2026 run

```bash
sudo KALMAN_ENV_FILE=/opt/kalman/.env \
  bash kalman-toss-gateway/scripts/run_live_policy_replay.sh \
  --start 2023-01-01 \
  --end 2025-12-31 \
  --feed iex
```

For a final research decision, rerun the exact frozen policy with SIP if historical SIP access is available.

## Safety invariant

This change does not alter the currently running scheduler.

No code in this research runner submits an order, calls `engine.auto_trade`, writes production strategy signals, or changes live environment values.


## Session-aware market data

The live Toss `/api/v1/prices` endpoint can refresh `lastPrice` during the
US overnight session. Historical replay therefore composes session-specific
Alpaca feeds instead of carrying a regular-session close through the night:

- 20:00-04:00 America/New_York: `boats` by default
- 04:00-20:00 America/New_York: the configured primary feed (`iex` by default)

The replay never consumes a minute bar that starts after the watcher timestamp.
At an exact watcher minute it may use that minute's open; otherwise it uses the
latest completed minute close from the required session feed. Missing overnight
data is not substituted with an IEX close.

The pilot reports `median_overnight_watch_coverage` separately and requires
it to be at least 80% before the replay is considered validation-ready.
