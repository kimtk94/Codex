# R5.1 LIVE Top1 portfolio policy

## Purpose

Keep the frozen R5.1 prospective shadow ledger unchanged as the research benchmark while allowing the live executor to use fresh R5.1 Top1 signals without the research-only four-bar non-overlap entry gate.

## Research benchmark

The upstream R5.1 prospective files and `shadow_entry_this_signal` semantics are unchanged.

- `shadow_entry_this_signal=true` means the signal was admitted to the R5.1 non-overlap shadow trade ledger.
- The shadow ledger continues to enforce `expected_exit_seq = expected_seq + 4`.
- It remains the clean prospective benchmark.

## LIVE policy: R5_LIVE_TOP1

A LIVE entry candidate requires:

1. market = US
2. strategy_version = R5.1_BASE_HGB
3. signal = SHADOW
4. position_state = FLAT
5. allow_trade_shadow = true
6. signal freshness <= 90 minutes, measured from the completed 60m bar close
7. US fractional-order window open
8. live two-key gate open
9. no open BUY order for the target symbol
10. sufficient broker cash/buying power
11. per-order estimated notional <= KRW 5,000

For a new symbol, the target symbol must not already exist at the broker outside the managed-position state and active managed positions must be below 3.

For an already managed R5_LIVE_TOP1 symbol, the executor may pyramid into the same managed position when all of the following hold:

- the position is OPEN and broker quantity matches the managed aggregate quantity
- the new signal is at least 1 completed 60m canonical bucket after the previous successful entry signal
- the same symbol is still the current eligible Top1
- fewer than 3 successful entries have been aggregated into that symbol
- projected configured target notional does not exceed KRW 15,000
- the add-on remains a separate KRW 5,000 maximum order

The same-symbol add-on does **not** consume another active-position slot. It updates the existing managed position's aggregate quantity and quantity-weighted average entry price. The original first-entry signal timestamp remains the max-hold clock anchor, so pyramiding never extends the 4-bucket holding horizon.

`shadow_entry_this_signal` is NOT a LIVE entry requirement under this policy.

## Execution cadence

The R5.1 model and Top1 decision cadence remains hourly. The execution layer is intentionally more frequent:

- `run_us_cycle.sh` refreshes/commits the US model signal on the existing hourly schedule.
- `run_execution_watch.sh` runs every 5 minutes during the broad US-session KST window.
- The watcher never runs `run_pipeline.sh` or the benchmark ledger.
- It acquires `us-cycle.lock` before `auto-trade.lock`, so it skips while an hourly model refresh is in flight.
- Each watcher tick runs `position_manager -> auto_trade -> trade_mirror`.
- Existing signal freshness, client-order idempotency, same-signal add-on gap checks, broker quantity reconciliation, and market-window gates remain authoritative.

This makes a fresh hourly signal recoverable between model cycles without converting R5.1 into a 5-minute strategy. Stop-loss/take-profit and fill reconciliation are also checked on the 5-minute execution cadence, while max-hold remains defined in canonical hourly buckets.

## Exit policy

For R5_LIVE_TOP1, model-rotation exits are disabled so multiple symbols can coexist.

Each managed position exits on the first applicable rule:

1. stop loss <= -3%
2. take profit >= +20%
3. max hold >= 4 canonical 60m buckets

Position-manager reconciliation validates every add-on fill before updating the aggregate quantity and weighted average price. Any broker/managed quantity mismatch blocks further pyramiding and requires reconciliation.

## Audit / A-B attribution

Every successfully submitted LIVE entry writes `signal_context` into the local order telemetry before the post-trade mirror.

Important fields:

- `signal_policy = R5_LIVE_TOP1`
- `research_non_overlap_entry = true|false`
- `allow_trade_shadow`
- `run_id`
- `signal_as_of`
- `max_active_positions`
- `active_positions_before_entry`
- `entry_type = INITIAL|ADD_ON`
- `entry_count_before`
- `max_entries_per_symbol`
- `max_symbol_notional_krw`
- `projected_symbol_notional_krw`

This allows two cohorts:

- benchmark-compatible LIVE entries: `research_non_overlap_entry=true`
- overlap-added LIVE entries: `research_non_overlap_entry=false`

Historical `trade_execution.signal_policy` is preserved on mirror upserts so switching the runtime policy does not relabel old trades.
