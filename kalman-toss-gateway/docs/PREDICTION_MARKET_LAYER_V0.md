# Kalman Prediction Market Layer v0

## Scope

Read-only research/challenger layer for prediction-market expectations. It never submits orders, never authenticates a wallet, never changes R5.1 live scoring, and never attempts to bypass geographic/legal access restrictions.

The intended research chain is:

prediction-market expectation shift -> rate confirmation (US2Y / policy repricing) -> equity confirmation -> challenger evaluation.

## Provider contract

Polymarket's official market-list response exposes the fields needed for v0: outcomes/outcomePrices, liquidityNum, volume24hr, spread, oneHourPriceChange, oneDayPriceChange, lastTradePrice, bestBid, bestAsk, clobTokenIds and market timestamps.

The official price-history API is suitable for later point-in-time backfill by outcome token. Historical backfill is deliberately not activated until a lawful reachable data path exists.

## Current runtime finding (2026-10-07 KST)

From taehoonserver in Korea, the following public endpoints returned HTTP 451:

- gamma-api.polymarket.com/markets
- data-api.polymarket.com/v2/prices-history
- clob.polymarket.com/time

v0 treats HTTP 451 as BLOCKED_LEGAL_ACCESS, emits a status artifact, stores no synthetic market observations, and exits without retry/bypass logic.

## Features

Per market:

- poly_prob
- poly_delta_10m
- poly_delta_1h
- poly_velocity_1h
- liquidity_usd
- volume_24h_usd
- spread / best_bid / best_ask
- hours_to_event
- theme
- semantic_channel
- risk_prior_sign (research prior only)
- quality blockers

SQLite snapshots preserve point-in-time probability history for lead/lag work.

## Shadow experiment design

Keep the production control frozen:

- CONTROL: R5.1 + FIXED_4
- TEST A: CONTROL + prediction probability level
- TEST B: TEST A + 10m/1h probability momentum
- TEST C: TEST B + US2Y confirmation

Do not promote any feature until there is enough out-of-sample history and evaluation across net return, Sharpe, Sortino, MDD, profit factor, win rate, average trade, turnover and tail loss.

## Commands

Local parser/self-test:

    python -m engine.prediction_market_layer_v0 selftest

Fixture collection:

    python -m engine.prediction_market_layer_v0 collect --fixture tests/fixtures/prediction_market_sample.json --output /tmp/pm.json --db /tmp/pm.sqlite3

Live collection:

    python -m engine.prediction_market_layer_v0 collect

On the current Korea-hosted server, live collection is expected to return BLOCKED_LEGAL_ACCESS.

## Safety invariants

Every emitted market and top-level payload is challenger-only/read-only. There is no order endpoint, wallet key, position sizing, Kelly sizing, execution hook, or R5.1 live feature mutation in this module.

## Offline archive backfill

For reproducible historical research, v0 can ingest the independent CC BY 4.0
archive published by Dinesh Gopalakrishnan rather than attempting to bypass the
live HTTP 451 restriction.

Frozen research snapshot:

- GitHub release: data-2026-09-13
- asset: polymarket-orderbook-2026-09-13.tar.zst
- SHA256: 13c76e8868589a46a60cd1b6eda80c2094fc36b32f51fc6435fa4ba9c6fb8086
- observed coverage: 2026-07-10 through 2026-09-13

Fetch and verify:

    scripts/fetch_prediction_market_archive_v0.sh

Build the 10-minute macro canonical table:

    scripts/run_prediction_market_research_v0.sh archive

Archive safety/data-quality rules are explicit:

- quotes/ is top-of-book observation data, not executed prints
- crossed books are removed
- the 2026-07-17 to 2026-07-22 collector outage is never bridged for deltas
- 10m/1h probability changes require the exact prior timestamp within the same segment
- volume24hr is retained but tagged as unreliable/missing where the source dataset has the known upstream failure
- only macro/finance/geopolitics/politics rows that map to a configured Kalman theme survive

## Lead-lag audit

The offline lead-lag runner accepts any Kalman asset file that contains a
recognizable timestamp column and close/price column.

Example:

    scripts/run_prediction_market_research_v0.sh leadlag \
      --asset QQQ=/path/QQQ_1h_2017plus.parquet \
      --asset QLD=/path/QLD_1h_2017plus.parquet

The event layer only uses semantically mapped markets. A one-hour probability
move is converted into a signed risk shift using the configured research prior,
then aligned to the first asset bar at or after the event. It reports 1-bar,
4-bar and 7-bar forward returns without changing production R5.1.

An optional US2Y file can be supplied with --us2y. Rate confirmation is only
scored for FED_EASING and FED_TIGHTENING channels; other event classes are left
unscored rather than forcing a generic bond-direction assumption.

The 1-hour QQQ/QLD history currently available in Kalman covers 2020-07-27
through 2026-08-28. SOXX is not currently present in the history_1h folder, so it
is an explicit data gap rather than a synthesized series.
