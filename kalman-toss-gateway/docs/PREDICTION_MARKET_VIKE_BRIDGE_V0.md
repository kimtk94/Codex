# Prediction Market Vike Measurement Bridge v0

Date: 2026-10-07 KST

## Purpose

The original frozen prediction-market discovery dataset ends at
`2026-09-13T11:50:00Z`. Vike exposes a separate Polymarket L1 archive that
continues beyond that date. This bridge is designed to determine whether Vike
can be used as a measurement-compatible OOS continuation without retuning the
frozen hypothesis.

Vike data is **not** admitted to confirmatory OOS merely because it is newer.
It must first pass the frozen measurement bridge.

## Public source facts observed on 2026-10-07

Public manifest:

`https://data.vike.io/archive/manifest.json`

Observed:

- manifest generated: `2026-10-07T00:45:08Z`
- license: CC BY 4.0
- archive coverage: 2026-07-25 through 2026-10-06
- family layout used here: `asset=other/tenor=other`
- stream used here: `l1_quotes`
- post-discovery dates available: 23 days, 2026-09-14 through 2026-10-06
- post-discovery L1 size: 4.799 GB
- overlap window for bridge: 2026-09-08 through 2026-09-13
- overlap L1 size: 1.128 GB
- overlap reference contains 12 INFLATION_UPSIDE market slugs

The open Vike evaluation sample confirms the actual L1 parquet schema:

`token_id, condition_id, ts, local_ts, bid, ask, bid_size, ask_size`

and confirms that `ts` is epoch milliseconds.

## Frozen bridge specification

Config:

`config/prediction-market-vike-bridge-v0.json`

SHA256:

`046e2af8e3bfbe0aede53ed07e187a841c63cd5bfc4ef33be0a0f267c3f5d768`

Market discovery queries are frozen as:

- `cpi`
- `inflation`
- `consumer-price`

Only markets classified as:

- theme: `INFLATION`
- semantic channel: `INFLATION_UPSIDE`

are eligible for this first bridge.

The overlap is canonicalized to 10-minute last L1 quote per token. For each
shared market, the bridge independently compares token position 0 and token
position 1 with the original discovery probability series and selects the
orientation with lower MAE. This avoids assuming outcome-token ordering.

The bridge passes only if all of these predeclared gates pass:

- shared markets >= 8
- matched 10-minute points >= 1,000
- token-position orientation consistency >= 90%
- median per-market probability MAE <= 0.03
- pooled probability correlation >= 0.95
- median absolute 1-hour-delta difference <= 0.02
- discovery 15pp shock pairs >= 5
- sign agreement on those shock pairs >= 90%

These thresholds are frozen before authenticated Vike data is accessed. They
must not be relaxed after seeing the bridge result.

## Safety

Even `BRIDGE_PASS` only means that Vike is measurement-compatible enough to
be considered as an OOS input source. It does not:

- change `PMOOS-INFLATION-UP-QQQ-7B-V1`
- change the 15pp threshold
- change QQQ
- change the 7-bar horizon
- change the 90-minute entry-lag rule
- alter R5.x
- submit trades
- auto-promote any signal

A failed bridge means Vike is not used for this frozen OOS cycle.

## Current status

Without an authenticated Vike key, the public probe returns:

`WAITING_FOR_VIKE_KEY`

This is expected and fail-closed.

Local regression:

- Vike bridge tests: 6 passed
- Vike bridge + fetch tests: 10 passed

## One-time authenticated bridge run

Do not paste the Vike key into chat or commit it.

From the server:

```bash
cd /home/taehoon/Codex-PREDICTION-MARKET-20261007/kalman-toss-gateway

read -s -p "Vike API key: " VIKE_API_KEY
echo
export VIKE_API_KEY

bash scripts/run_prediction_market_vike_overlap_v0.sh

unset VIKE_API_KEY
```

The fetcher downloads only the six overlap-family L1 partitions, filters them
down to the discovered target CPI/inflation token IDs, discards the temporary
full partitions, combines the filtered rows, and runs the frozen bridge.

Primary result:

`/home/taehoon/kalman-data/prediction-market/vike-bridge-v0/bridge_status.json`

Only after `BRIDGE_PASS` should the post-2026-09-13 Vike partitions be
canonicalized for confirmatory OOS.
