# Polymarket US Prospective OOS Collector v0

Date: 2026-10-08 KST

## Provenance correction

The frozen discovery archive contains CPI contracts such as:

`cpic-uscpi-august-yoy-2026-09-11-gt3pt3pct`

The official Polymarket US public gateway successfully resolves that exact slug:

`GET https://gateway.polymarket.us/v1/market/slug/{slug}`

It returns the same question, macro category, description, start/end dates, and
resolved Yes/No market. Therefore the CPI discovery source is Polymarket US,
not Polymarket Global.

This matters because Global Polygon datasets such as Dune's Polymarket tables
are not a measurement-compatible substitute for this frozen OOS hypothesis.

## Official public source

The active collector uses only the official Polymarket US public gateway:

- search: `GET /v1/search`
- BBO: `GET /v1/markets/{slug}/bbo`

No authentication, wallet, order API, geobypass, or private participant data is
used.

The Polymarket US SDK documents BBO as the lightweight top-of-book endpoint and
returns best bid, best ask, and last trade information.

## Measurement contract

The Dinesh discovery archive used two-sided top-of-book midpoint as probability.

On the first live Polymarket US collection, 44 active inflation markets were
found. For every one of the 44 markets:

`(bestBid + bestAsk) / 2 == currentPx`

Observed maximum and median absolute differences were both exactly 0.0.

Therefore the prospective collector stores:

`probability = (bestBid + bestAsk) / 2`

and rejects one-sided books for canonical probability observations.

## Collection and gap policy

- search terms: CPI, inflation, PCE
- category: macro
- semantic themes: INFLATION
- channels: INFLATION_UPSIDE / INFLATION_DOWNSIDE
- poll cadence: every 2 minutes
- canonical bucket: 10 minutes, last observation in bucket
- if a slug has a collection gap >30 minutes, a new segment begins
- 10m/1h deltas are only computed within the same segment

This prevents a collector outage from being interpreted as a normal one-hour
probability move.

## Paths

Raw SQLite:

`/home/taehoon/kalman-data/prediction-market/us-live-v0/raw_snapshots.sqlite3`

Canonical:

`/home/taehoon/kalman-data/prediction-market/us-live-v0/prediction_us_live_v0.parquet`

Status:

`/home/taehoon/kalman-data/prediction-market/us-live-v0/status.json`

Frozen OOS result:

`/home/taehoon/kalman-data/prediction-market/us-live-v0/oos/oos_summary.json`

## First live run

First collection timestamp:

`2026-10-07T15:25:38Z`

Result:

- discovered active eligible markets: 44
- stored BBO snapshots: 44
- request failures: 0
- max midpoint-vs-currentPx difference: 0.0
- median midpoint-vs-currentPx difference: 0.0
- canonical rows: 44
- canonical markets: 44
- first bucket: `2026-10-07T15:20:00Z`
- OOS status: `WAITING_FOR_OOS_EVENTS`

The absence of a one-hour delta on the first bucket is expected.

## Frozen hypothesis safety

The collector feeds the already frozen:

`PMOOS-INFLATION-UP-QQQ-7B-V1`

It does not change:

- the 15pp shock threshold
- INFLATION_UPSIDE channel
- QQQ
- 7-hour-bar horizon
- <=90 minute entry-lag rule
- confirmatory gate thresholds

It cannot auto-promote a result, mutate R5.x, or submit trades.

## OOS event ledger

Every collector cycle now updates a persistent event ledger.

SQLite:

`/home/taehoon/kalman-data/prediction-market/us-live-v0/oos_event_ledger.sqlite3`

Parquet mirror:

`/home/taehoon/kalman-data/prediction-market/us-live-v0/oos_event_ledger.parquet`

A stable event ID is derived from:

`hypothesis_id + event_hour + dominant_channel`

so repeated collector cycles update one event instead of duplicating it.

Per-event states are:

- `WAITING_ASSET_ENTRY`
- `EXCLUDED_ENTRY_LAG`
- `WAITING_HORIZON`
- `OUTCOME_READY`

When the QQQ 7-bar outcome becomes available, the ledger records both raw forward return and signed return. Signed return follows the same convention as the frozen discovery analysis: `sign(event_score) * forward_return`.

The first live ledger run on 2026-10-08 produced zero events, which is expected because the prospective collector had not yet accumulated a full one-hour probability delta.
