# Kalman ETH Grid V3 — static audit (2026-10-18)

Source: `research/upbit_eth/grid_event_v3.py` on `main`. Scope is **read-only, offline research**. Reviewed source only; no market data replay or profitability validation performed.

## Confirmed implementation

- SQLite opened via URI `mode=ro` and `PRAGMA query_only=ON`; output CSV is written separately.
- Annual UTC window is derived from KST Jan 1 boundaries. Simulation evaluates 2024, 2025, 2026, three spacing choices (0.6%, 1%, 1.5%) and levels (20, 50, 100).
- Budget starts 50% fiat, 50% ETH, pre-reserves buy cash inclusive of entry fees and sale inventory separately.
- If a candle touches both a resting buy and a sell, no order executes for that candle; it records ambiguity.
- A timestamp gap >300 s triggers cancellation and reseeding; the first post-gap candle is not used for fill inference.
- Mark-to-market equity includes reserved inventory, and an invariant rejects meaningful negative balances.

## Findings / research risks

| ID | Severity | Observation | Required validation |
|---|---|---|---|
| GV3-01 | HIGH | Touch test uses strict `low < bid` and `high > ask`; equality is excluded. This is a conservative but materially different fill assumption. | Paired `<=` / `>=` sensitivity study and bar-level diagnostics |
| GV3-02 | HIGH | Intrabar candle OHLC cannot establish time-order or queue position. Both-side touched candles are skipped, while one-side touched bars assume full fill at the resting level. | Compare event replay with finer-granularity data, slippage and queue discount scenarios |
| GV3-03 | HIGH | `price()` applies approximate KRW tick bands (including a single 100-KRW band below 1M); the comment itself disclaims exactness. | Date-indexed Upbit KRW market tick schedule before credible PnL |
| GV3-04 | MEDIUM | Each year starts at an independent 50/50 portfolio and seed; year-end proceeds do not carry into next year. | Report annual independent tests separately from continuous multi-year CAGR |
| GV3-05 | MEDIUM | Gap criterion is `>300s`; shorter missing-minute runs do not reset. `gaps` counts reset events, not missing bars. | Report missing-minute distribution, 2/3/4/5-minute gap stress tests |
| GV3-06 | MEDIUM | Only three spacings and level counts are searched; 0.14% setting and a 2020+ regime sample are not covered. | Widen parameters after data integrity check, use train/OOS partitions |
| GV3-07 | MEDIUM | Static order notional per `unit=capital/n`; with fees, buy reservation may exhaust cash before all levels are seeded. | Record seed orders placed vs rejected, idle capital and fee-adjusted inventory |
| GV3-08 | MEDIUM | `equity` is valued at close (not liquidation proceeds); realized liquidation fees, spread and withdrawal/market impact are excluded. | Add exit-cost-adjusted net-equity series and stress fees |
| GV3-09 | MEDIUM | Duplicate orders aggregate by `(side,tick_price)`; tick-rounding can collapse levels. | Count distinct levels, merged order notional and re-seed distribution |
| GV3-10 | LOW | The final `rows[0]` CSV fieldnames code assumes at least one row result. | Empty input fail-safe and schema-level tests |

## Acceptance criteria before any change to LIVE

1. Tests for reservation conservation, fee-inclusive equity, both-side ambiguity, gap resets, and tick collisions.
2. Side-by-side conservative/base/optimistic fill models with explicitly bounded assumptions.
3. Yearly and continuous walk-forward results, net of costs; no future leakage.
4. Store every candidate's trades, exposure and drawdown, not only annual summary.
5. Keep LIVE runtime and credentials unchanged; this document authorizes no deployment.

## Relation to REA

The verified REA 6.5.0 static JavaScript analyzer is applicable to JavaScript front-end/bundle inspection, **not** to this Python file. For Python use AST/unit tests and a separate source evidence ledger. Do not misrepresent a Python AST inspection as an REA finding.
