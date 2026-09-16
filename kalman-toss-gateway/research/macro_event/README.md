# Kalman Macro Event V1 (research only)

Purpose: add point-in-time U.S. macro announcement surprise and rate/policy-repricing context to the existing Historical V3 daily matrices without changing production execution.

## Normalized event contract

Required columns:

- `event_id`: unique stable ID
- `event_type`: canonical type from `config/macro-event-v1-spec.json`
- `release_time`: official release timestamp, timezone-aware or UTC-parseable
- `available_time`: first timestamp the value was available to the model
- `actual`: released value in the same unit as consensus
- `consensus`: pre-release survey consensus

Optional columns:

- `previous`, `revised_previous`
- `us2y_1m_bp`, `us2y_5m_bp`, `us2y_30m_bp`, `us2y_60m_bp`
- `fed_reprice_5m_bp`, `fed_reprice_30m_bp`, `fed_reprice_next_bp`, `fed_reprice_3m_bp`, `fed_reprice_year_end_bp`
- `nq_5m_ret`, `soxx_5m_ret`, `dxy_5m_ret`, `gold_5m_ret`, `btc_5m_ret`

Do not substitute a current revised economic series for a historical release value. `available_time` is the anti-lookahead boundary.

## Pipeline

```text
normalized calendar + reaction data
  -> build_macro_event_features.py
  -> macro_events_v1.parquet
  -> merge_macro_v4.py
  -> historical_matrices_v4_macro/
  -> existing Historical V3 return/regime engine with V4 spec
  -> compare_v3_v4.py (identical common OOS window)
```

The daily merge uses market-specific decision cutoffs:

- US: 16:00 America/New_York (DST aware)
- KR: 15:30 Asia/Seoul
- BTC: 23:59 UTC

An event is usable only if `available_time <= decision_cutoff`.

## Surprise standardization

`surprise_raw = actual - consensus`.

`surprise_z` uses only prior events of the same type (`shift(1)` before expanding standard deviation). This prevents the current event from affecting its own normalization denominator.

`hawkish_surprise_z` multiplies by the event-specific direction from the spec. For example, a positive unemployment-rate surprise is mapped dovish (`hawkish_sign = -1`).

## Current data dependency

The code deliberately does not scrape news pages. Historical consensus must come from a point-in-time calendar source/export. Intraday US2Y and Fed repricing are optional columns and can be added when licensed feeds are available.

All modules in this directory are research-only. No Toss orders and no Neon production writes.


## Trading Economics backfill adapter

`collect_tradingeconomics.py` normalizes Trading Economics U.S. calendar records into the contract above.
It reads the API key only from `TRADINGECONOMICS_API_KEY` (or another explicitly selected environment variable)
and never persists the key.

```bash
export TRADINGECONOMICS_API_KEY='...'
python -m research.macro_event.collect_tradingeconomics \
  --start 2017-01-01 \
  --end 2026-09-16 \
  --output /mnt/gdrive/Market_Macro/v1/raw/us_macro_events_normalized.parquet
```

If a normalized macro input already exists, the Colab runner reuses it and does not require an API call.

## Dense state semantics

Macro state features are intentionally dense for the daily model:

- no active macro shock within the configured window -> shock state `0.0`
- a reaction source that exists -> latest non-null reaction decays toward `0.0`
- a reaction source that does not exist anywhere in the dataset -> all `NaN`

This prevents monthly releases such as CPI from failing the model's minimum feature coverage gate while
still preventing missing US2Y/Fed feeds from being represented as fake zeros.

## Fair V3 vs V4 comparison

The primary V4 spec keeps `maximum_features=24`, identical to Historical V3. Therefore the first comparison
tests whether macro information improves feature selection under the same model capacity. Capacity-expanded
variants should be treated as separate ablations.

The V4 runner also records how often `macro__*` features are selected across walk-forward folds.
