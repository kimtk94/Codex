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
9. target symbol has no existing broker position
10. target symbol has no open BUY order
11. no active managed lot already exists for the same symbol
12. active managed positions < 3
13. sufficient broker cash/buying power
14. per-order estimated notional <= KRW 5,000

`shadow_entry_this_signal` is NOT a LIVE entry requirement under this policy.

## Exit policy

For R5_LIVE_TOP1, model-rotation exits are disabled so multiple symbols can coexist.

Each managed position exits on the first applicable rule:

1. stop loss <= -3%
2. take profit >= +20%
3. max hold >= 4 canonical 60m buckets

Position-manager reconciliation and broker-quantity safety checks remain unchanged.

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

This allows two cohorts:

- benchmark-compatible LIVE entries: `research_non_overlap_entry=true`
- overlap-added LIVE entries: `research_non_overlap_entry=false`

Historical `trade_execution.signal_policy` is preserved on mirror upserts so switching the runtime policy does not relabel old trades.
