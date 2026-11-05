# Prediction Market Vike Measurement Bridge v0

Date: 2026-10-07 KST

## Why this bridge exists

The frozen discovery archive ends at `2026-09-13T11:50:00Z`. Vike's public
manifest shows Polymarket archive coverage through `2026-10-06`, so it can
potentially provide a true OOS continuation.

The original implementation attempted to use Vike
`/v1/polymarket/markets` for slug-to-token metadata. On 2026-10-07 that
endpoint returned HTTP 500 even though the public archive manifest remained
available. Authentication was therefore not treated as failed, and bridge
thresholds were not relaxed.

The active implementation no longer depends on the Vike market-directory API.

## Archive-only identity design

Vike L1 parquet contains:

`token_id, condition_id, ts, local_ts, bid, ask, bid_size, ask_size`

The original Dinesh archive contains the CPI slug probability series. The bridge
uses temporal overlap to identify the corresponding Vike condition/token
without relying on market metadata.

To avoid circular validation, the overlap is split before authenticated archive
data is inspected:

### Identity train

- `2026-09-08T00:00:00Z` through `2026-09-09T23:50:00Z`
- used only to map each frozen CPI slug to a Vike condition/token
- matching statistic: 10-minute midpoint MAE + correlation
- one best token is chosen per condition before conditions are ranked

### Holdout validation

- `2026-09-10T00:00:00Z` through `2026-09-11T09:00:00Z`
- not used for identity selection
- contains 2,240 frozen reference points across 12 CPI slugs
- contains exactly 5 reference 15pp+ one-hour shocks
- used for the actual measurement bridge gate

Only four Vike daily L1 partitions are now required: 2026-09-08 through
2026-09-11. Based on the public manifest this is about 0.724 GB rather than the
previous 1.128 GB six-day plan.

## Frozen bridge spec

Config:

`config/prediction-market-vike-bridge-v0.json`

Current SHA256:

`16f718c7f0e2ea9721d0c8ab072dab74bf7583d01143c84cdfef01dae194f82a`

This SHA was created after the Vike market-directory HTTP 500 and before any
authenticated Vike archive partition was inspected.

### Identity gate

For every frozen CPI slug:

- training matched points >= 150
- training MAE <= 0.03
- training correlation >= 0.95
- MAE margin versus the second-best distinct condition >= 0.005
- selected condition IDs must be unique across slugs

Any identity ambiguity causes `IDENTITY_BRIDGE_FAIL`.

### Holdout bridge gate

All must pass:

- shared markets >= 8
- matched holdout points >= 1,000
- median per-market probability MAE <= 0.03
- pooled probability correlation >= 0.95
- median absolute one-hour delta difference <= 0.02
- 15pp shock pairs >= 5
- shock-direction agreement >= 90%

A failed gate is not retuned.

## Download and aggregation

The active runner downloads only
`asset=other/tenor=other/l1_quotes.parquet` partitions for the four overlap
dates. Each raw partition is immediately reduced with DuckDB to the last
bid/ask midpoint in each 10-minute bucket by condition/token, then the raw
partition is deleted.

This avoids retaining or loading the full L1 archive in Python memory.

## Safety

`BRIDGE_PASS` only permits Vike to become a confirmatory OOS input source. It
does not:

- change `PMOOS-INFLATION-UP-QQQ-7B-V1`
- change the 15pp shock threshold
- change QQQ
- change the 7-bar horizon
- change the <=90 minute entry-lag rule
- modify R5.x
- place trades
- auto-promote a signal

## Current execution

Do not paste the Vike API key into chat or commit it.

Run:

```bash
cd /home/taehoon/Codex-PREDICTION-MARKET-20261007/kalman-toss-gateway

read -s -p "Vike API key: " VIKE_API_KEY
echo
export VIKE_API_KEY

bash scripts/run_prediction_market_vike_overlap_v0.sh

unset VIKE_API_KEY
```

The command now performs:

`authenticated archive download -> DuckDB 10m aggregation -> blind train mapping -> holdout bridge validation`

It does not call `/v1/polymarket/markets`.

Primary result:

`/home/taehoon/kalman-data/prediction-market/vike-bridge-v0/bridge_status.json`
