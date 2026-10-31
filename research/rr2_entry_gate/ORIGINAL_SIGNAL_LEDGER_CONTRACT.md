# COIN V_unweighted original-signal ledger contract

## Current state — HOLD
- Existing historical aggregate ZIP `Kalman_US_Five_RR2_Feasibility_20261101.zip` establishes **COIN 2025:80, 2026:46 V_unweighted original signals**, all rejected by the 1.25×ATR / 3×ATR baseline.
- It does **not contain signal IDs, entry dates, individual predictions, or their provenance**. Never synthesize these from a plausible 80/46 subset.
- The COIN 2024–2026 all-session SIP pilot has 711 complete sessions but **does not match** the V_unweighted signal cohort and cannot establish model-signal profitability.
- Historical 2025/2026 samples have been inspected. They are **not untouched OOS**.

## Required original export: `coin_v_unweighted_PIT_signals.csv`
Mandatory CSV header:

```csv
signal_id,signal_date,entry_date,symbol,model,available_after,source_run_id
```

No sample fake signals. Export only original **positive signal decisions** from the immutable model run, not signals inferred from future returns. `signal_date` is the completed NYSE session in New York local calendar date for which model features are available **after RTH close**. `entry_date` must equal the immediately following NYSE trading session (no skipping sessions); assumed fill is the opening price of the 09:45 NYSE bar. `available_after=RTH_CLOSE`, `symbol=COIN`, `model=V_unweighted`. `source_run_id` must refer to the original model execution and be consistent within each 2025 or 2026 training vintage (it may differ between years).

### Model / source provenance requirements
- Preserve original algorithm, feature lag definitions, 2024 training used for 2025 and 2024+2025 training for 2026 YTD, any purging/calibration, fit window, frozen model artifact identity, and positive-signal decision rule.
- Export all candidates **before RR rejection**, including the 126 original signals. No future price outcomes used to filter the export.
- Include separate nonpublic provenance of `source_run_id`, frozen model artifacts, and raw feature snapshot provenance; a self-reported CSV value does not independently authenticate a real historical signal.
- Persist the export privately in Drive and allow the `TaehoonServer` GitHub Actions service account **Viewer** access. The prior archive read failed because the service account could not access its Drive file.
- Do not commit the private ledger, licensed SIP 15m bars, API credentials, per-signal dates, or unaggregated trade fills to the public repository.

## Hard validation implemented
1. Mandatory fields, nonempty IDs, nonduplicated entries, one signal per entry date.
2. NYSE calendar `signal_date` immediately before `entry_date`, price source availability and 20 completed-day lookback.
3. 2025 exactly 80, 2026 exactly 46 signals; one documented model source run per evaluation year.
4. Baseline ATR1.25/TP3.0 geometry must still admit zero signals (if drift, HOLD).
5. Only after these gates does the private job replay four structural entry arms over 1, 2, 4 NYSE sessions, accounting for overlap, horizon censoring and 15m stop-first/gap paths.
6. Aggregate-only output with per-year signal count, admission, rejections, realized R, gap stops and cash-chain drawdown. Always `live=HOLD` and `not_fresh_oos=true`.

## CI
- Offline synthetic tests automatically run on PR changes to `coin_signal_replay.py`.
- Private workflow: `.github/workflows/kalman-coin-pit-replay.yml` requires `original_signal_ledger_drive_id`. It is **not executed** without an accessible authentic original ledger.
- Run through CI, not on the LIVE server. No broker/order system changes.

## Known limitations before future promotion
- Self-reported ledger provenance cannot prove its historical integrity; independently reconcile against original pipeline run logs/commit/checksums.
- Baseline ATR calculation may differ in smoothing details from original pipeline; cross-check distributions and first-failure flags using original source.
- The existing simulator uses OHLC-based pessimistic stop-first ordering and approximate flat 30bps friction; spread, latency, real quotes, and intrabar marked-to-market MDD remain unverified.
- No model-promotion decision without fresh, independent OOS evidence and realistic fill stress testing.
