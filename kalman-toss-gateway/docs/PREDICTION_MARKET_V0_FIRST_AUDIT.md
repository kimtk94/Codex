# Kalman Prediction Market Layer v0 — First Offline Audit

Date: 2026-10-07 KST

## Decision

**Do not promote prediction-market features into R5.x yet.**

The first point-in-time lead/lag audit found no subgroup that survives the current
promotion gate after cluster-aware inference and multiple-testing correction.

The layer remains:

- read-only
- challenger/research only
- disconnected from wallet/order submission
- disconnected from live R5.1 scoring and execution

## Data sources

### Prediction-market archive

Frozen release:

- repository: `DineshKumar8399/polymarket-orderbook-dataset`
- release: `data-2026-09-13`
- asset: `polymarket-orderbook-2026-09-13.tar.zst`
- SHA256: `13c76e8868589a46a60cd1b6eda80c2094fc36b32f51fc6435fa4ba9c6fb8086`
- license: CC BY 4.0

The archive itself documents three constraints that are enforced in the v0 importer:

1. no quote rows from 2026-07-17 17:26:09 to 2026-07-22 10:32:48;
2. `volume24hr` is mostly unusable and disappears after the outage;
3. broad-sweep prices are book quotes/midpoints, not executed trades.

The importer therefore computes deltas only inside the same `slug + segment`,
marks prices as `MIDPOINT_NOT_TRADE`, removes crossed books, and does not use
missing volume as a synthetic value.

### Asset history

The audit used existing Kalman IEX 1-hour history for:

- QQQ: 13,112 bars, 2020-07-27 through 2026-08-28
- QLD: 10,233 bars, 2020-07-27 through 2026-08-28

SOXX was not present in the current Drive `history_1h` folder and is therefore
not fabricated or substituted.

US 2Y confirmation uses FRED `DGS2`. Daily DGS2 observations are timestamped as
available at 16:00 America/New_York rather than 00:00 UTC, preventing same-day
close information from leaking into earlier events.

## Canonical prediction-market dataset

The archive importer produced:

- quote files scanned: 62
- raw in-scope quote rows: 2,182,655
- 10-minute canonical rows: 369,902
- distinct markets: 123

Distinct markets by theme:

| Theme | Markets |
|---|---:|
| RECESSION_GROWTH | 38 |
| INFLATION | 35 |
| GEOPOLITICS | 27 |
| FED_POLICY | 22 |
| FISCAL_POLICY | 1 |

The research signal is based on exact 1-hour probability changes within the same
market and archive segment.

## Experiment contract

Primary near-session audit:

- probability shock thresholds: 5pp, 10pp, 15pp
- asset entry: first QQQ/QLD hourly bar at or after the event
- maximum event-to-entry lag: 90 minutes
- horizons: 1, 4, 7 asset bars
- signed return: `sign(event_score) * forward_return`
- inference: date-cluster bootstrap plus date-cluster sign-flip test
- multiple testing: Benjamini-Hochberg FDR across the generated matrix

Promotion gate:

- n >= 20
- unique event dates >= 8
- directional hit rate >= 55%
- positive-date rate >= 60%
- mean signed return > 0
- cluster bootstrap 95% lower bound > 0
- FDR q <= 0.10

## Baseline result: mixed event score

At the 5pp shock threshold, the mixed macro score is not a usable standalone
feature.

### QQQ near-session

- 155 observations at 1 bar: hit rate 52.3%
- 155 observations at 4 bars: hit rate 47.7%
- 155 observations at 7 bars: hit rate 47.1%

### QLD near-session

- 130 observations at 1 bar: hit rate 51.5%
- 130 observations at 4 bars: hit rate 45.4%
- 129 observations at 7 bars: hit rate 45.7%

This rejects the simple hypothesis that all qualifying prediction-market shocks
can be averaged into one directional equity feature.

## Strongest nominal finding

The strongest pre-FDR result was:

**15pp+ INFLATION_UPSIDE shock -> QQQ 7-bar signed return**

- n = 27
- unique dates = 8
- mean signed return = +0.4093%
- median signed return = +0.5983%
- directional hit rate = 62.96%
- positive-date rate = 87.5%
- event-score/return correlation = 0.341
- date-cluster bootstrap 95% CI = +0.1564% to +0.7294%
- cluster sign-flip p = 0.0350
- Benjamini-Hochberg FDR q = 1.0

This is a **watchlist hypothesis**, not validated alpha. It does not survive the
multiple-testing correction.

A broader 15pp QQQ 7-bar result was also nominally positive:

- n = 46
- unique dates = 15
- mean signed return = +0.2455%
- hit rate = 56.52%
- bootstrap 95% CI = +0.0221% to +0.5152%
- sign-flip p = 0.0548
- FDR q = 1.0

## Fed / US2Y result

At the 5pp threshold, QQQ `FED_TIGHTENING` showed a potentially interesting
1-bar directional response:

- n = 37
- unique dates = 14
- mean signed return = +0.1024%
- hit rate = 64.86%
- bootstrap 95% CI = -0.0889% to +0.3131%
- sign-flip p = 0.352
- FDR q = 1.0

Adding available US2Y confirmation did not make the result statistically robust.
For confirmed Fed rows on QQQ:

- 1 bar: n=24, hit=75.0%, mean signed return +0.0869%, CI crosses zero
- 4 bars: n=24, hit=54.2%, mean signed return +0.1324%, CI crosses zero
- 7 bars: n=24, hit=58.3%, mean signed return -0.0069%

Therefore US2Y confirmation is retained as a research dimension, not as a live
gate.

## Interpretation

The first audit supports three conclusions:

1. **Prediction-market data is useful as an event-state layer, but not as a
   single averaged directional score.**
2. **Theme/channel separation is mandatory.** Inflation and Fed contracts have
   materially different equity response profiles.
3. **The current historical window is too short for promotion.** The strongest
   nominal result uses only eight unique dates and fails FDR correction.

## Next research step

Keep the current layer shadow-only and extend the out-of-sample history before
retesting. The priority hypothesis is:

> Large inflation-upside probability shocks may contain short-horizon QQQ
> downside information.

The hypothesis must be frozen before the next data tranche is evaluated. The
next evaluation should not change its 15pp threshold or 7-bar horizon based on
new results; otherwise the out-of-sample test becomes another tuning exercise.

SOXX should be added only after a real point-in-time 1-hour history file is
available. No proxy substitution should be used.

## Reproduction

Fetch and verify the frozen archive:

```bash
scripts/fetch_prediction_market_archive_v0.sh
```

Build the canonical macro subset:

```bash
scripts/run_prediction_market_research_v0.sh archive
```

Run baseline lead/lag:

```bash
scripts/run_prediction_market_research_v0.sh leadlag \
  --asset QQQ=/path/QQQ_1h_2017plus.parquet \
  --asset QLD=/path/QLD_1h_2017plus.parquet \
  --us2y /path/DGS2.csv
```

Run stratified/FDR audit:

```bash
scripts/run_prediction_market_research_v0.sh stratified \
  --asset QQQ=/path/QQQ_1h_2017plus.parquet \
  --asset QLD=/path/QLD_1h_2017plus.parquet \
  --us2y /path/DGS2.csv \
  --thresholds 0.05,0.10,0.15 \
  --max-entry-lag-minutes 90
```
