# Kalman Macro Event V1 (research only)

Purpose: add point-in-time U.S. macro release information and rate context to the existing Historical V3 daily matrices without changing production execution.

## Free canonical data path

The canonical V1 backfill uses only the user's free FRED API key:

- FRED/ALFRED `series/observations?output_type=4` for initial-release-only macro observations
- FRED daily rates/FX for DGS2, DGS10, effective Fed Funds, target range, SOFR and USD/KRW
- no paid Trading Economics dependency

The free path intentionally distinguishes an initial-release change proxy from a survey-consensus surprise.

## Normalized event contract

Required columns:

- `event_id`: unique stable ID
- `event_type`: canonical type from `config/macro-event-v1-spec.json`
- `release_time`: model release timestamp, timezone-aware or UTC-parseable
- `available_time`: first timestamp the release may enter the model
- `actual`: ALFRED initial-release value

Optional columns:

- `consensus`: pre-release survey consensus, when separately available
- `previous`, `revised_previous`
- `us2y_daily_bp`: same-day FRED DGS2 move versus previous available DGS2 observation
- `us2y_1m_bp`, `us2y_5m_bp`, `us2y_30m_bp`, `us2y_60m_bp`: optional licensed intraday reactions
- `fed_reprice_*`: optional licensed policy-path repricing
- `nq_5m_ret`, `soxx_5m_ret`, `dxy_5m_ret`, `gold_5m_ret`, `btc_5m_ret`: optional intraday reactions

Do not replace ALFRED initial releases with today's revised historical series. `available_time` is the anti-lookahead boundary.

## Free FRED/ALFRED backfill

```bash
export FRED_API_KEY='...'

python -m research.macro_event.collect_fred_alfred \
  --start 2017-01-01 \
  --end 2026-09-16 \
  --events-output /mnt/gdrive/Market_Macro/v1/raw/us_macro_events_normalized.parquet \
  --rates-output /mnt/gdrive/Market_Macro/v1/rates/fred_rates_context.parquet
```

The API key is read from the environment only and is never written to Drive or Git.

Initial free event set:

- CPI / Core CPI
- PCE / Core PCE
- PPI final demand
- nonfarm payroll level
- unemployment rate
- average hourly earnings
- JOLTS openings
- initial claims
- advance retail sales

FOMC decision surprise/dot-plot surprise remain separate future enrichments because FRED does not provide the pre-meeting market expectation needed to define a true policy surprise.

## Signal semantics

When a real pre-release consensus is available:

```
surprise_raw = actual - consensus
surprise_z = surprise_raw / prior-only expanding SD
hawkish_surprise_z = hawkish_sign * surprise_z
```

With the free FRED/ALFRED path, consensus is absent and the model uses:

```
release_change_raw = initial_release_t versus initial_release_(t-1)
release_shock_z = release_change_raw / prior-only expanding SD
hawkish_release_shock_z = hawkish_sign * release_shock_z
```

`macro_signal_z` chooses `hawkish_surprise_z` when a true consensus surprise exists; otherwise it falls back to `hawkish_release_shock_z`.

The free fallback is explicitly labeled `INITIAL_RELEASE_CHANGE_PROXY`. It must not be described as a consensus surprise.

## Daily 2Y confirmation

The free path uses FRED DGS2 daily data. The event-level field is `us2y_daily_bp`, not `us2y_30m_bp`.

This represents the change in the daily DGS2 observation on the release date versus the previous available DGS2 observation. It is useful as a daily rates-confirmation proxy but must not be interpreted as a +5m or +30m event-window reaction.

## Pipeline

```text
FRED/ALFRED initial releases + free daily rates
  -> collect_fred_alfred.py
  -> build_macro_event_features.py
  -> macro_events_v1.parquet
  -> merge_macro_v4.py
  -> historical_matrices_v4_macro/
  -> existing Historical V3 return/regime engine with V4 spec
  -> compare_v3_v4.py
```

Daily decision cutoffs:

- US: 16:00 America/New_York
- KR: 15:30 Asia/Seoul
- BTC: 23:59 UTC

An event is usable only when `available_time <= decision_cutoff`.

## Dense state semantics

- no active event shock in the configured window -> macro shock state `0.0`
- a reaction source that exists -> latest non-null reaction decays toward `0.0`
- a reaction source unavailable for the entire dataset -> `NaN`

This lets monthly macro releases pass the daily model coverage gate without converting genuinely missing reaction feeds into fake zeros.

## Fair V3 vs V4 comparison

The primary V4 spec keeps `maximum_features=24`, identical to Historical V3. Therefore the first comparison tests whether macro information improves feature selection under the same model capacity.

The V4 runner records how often `macro__*` features are selected across walk-forward folds.

All modules are research-only. Toss execution and Neon production writes remain disabled.
