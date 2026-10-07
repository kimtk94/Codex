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
