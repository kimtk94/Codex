# Open Revalidation Backfill / Backtest V1

## Purpose

Evaluate whether an R5 position that survives across the US overnight session should be closed at or just after the next regular-session open, instead of waiting for the existing FIXED_4 exit.

This is a **research-only** counterfactual. It does not modify production trading, Toss execution, R5.1 scoring, or the frozen prospective benchmark.

## Why this test exists

Daytime KST monitoring can identify deterioration, but fractional SELL execution is only useful when Toss accepts the order. Therefore the economically relevant question is not whether the position weakened during the Korean daytime, but whether information available at the first executable US regular-session window improves the exit decision.

## Baseline

Default baseline:

`/mnt/gdrive/US_ETF/model_lab_v1/results/exit_policy_v1_0_pre2026/exit_policy_v1_0_1_trade_ledger.parquet`

Only rows with `policy=FIXED_4` are used. Only trades where the ET entry date is earlier than the ET exit date are eligible for open revalidation.

## Historical minute data

Alpaca historical stock bars, default feed `iex`, timeframe `1Min`.

Credentials are loaded from:

- `ALPACA_API_KEY` + `ALPACA_API_SECRET`
- or `APCA_API_KEY_ID` + `APCA_API_SECRET_KEY`

The raw 1-minute windows are cached under:

`/mnt/gdrive/US_ETF/directional_research/open_revalidation_1m_alpaca_v1`

For a final promotion decision, rerun the exact frozen experiment with SIP if the account has SIP historical access.

## Candidate policies

- `OPEN_NEG_0BP_0M`: position return at 09:30 ET <= 0
- `OPEN_NEG_20BP_0M`: position return at 09:30 ET <= -0.2%
- `OPEN_FLIP_0M`: previous close > 0 and 09:30 ET return <= 0
- `OPEN_NEG_5M_CONFIRM`: 09:30 return <= 0 and first 5m momentum <= 0
- `OPEN_FLIP_5M_CONFIRM`: previous close > 0, 09:30 return <= 0, first 5m momentum <= 0
- `OPEN_GAP_5M_CONFIRM`: negative overnight gap, position <= 0 at 09:35, first 5m momentum <= 0
- `OPEN_GIVEBACK_5M`: prior-close return >= +0.5%, giveback by 09:35 >= 0.7%p, first 5m momentum <= 0
- `OPEN_NEG_15M_CONFIRM`: 09:30 return <= 0 and first 15m momentum <= 0

The latency is explicit so 09:35 and 09:45 candidates cannot use future information at 09:30.

## Feed-bias control

The original FIXED_4 `net_return` stays authoritative. IEX is not used to replace the baseline return.

For a triggered trade:

`candidate_net = original_net + weight * (IEX_candidate_raw - IEX_fixed4_raw)`

The original ledger transaction-cost proxy `gross_return - net_return` is preserved. This paired same-feed delta design reduces IEX-vs-consolidated-market bias.

## Validation

Outputs include:

- baseline vs candidate cumulative/log growth
- max drawdown
- mean/median trade return
- win rate
- per-fold paired log-growth delta
- daily paired bootstrap 95% CI
- one-sided bootstrap p-value
- Holm multiple-testing adjustment
- reconstructed IEX FIXED_4 vs original ledger reconciliation
- trigger counts/rates

A candidate is only labelled a `research_survivor` when all configured gates pass. Even then, the automatic recommendation is `PROSPECTIVE_SHADOW_ONLY`, never production promotion.

## Pilot

After the branch is merged and the server is updated:

```bash
cd ~/Codex
git fetch origin main
git checkout main
git pull --ff-only origin main

sudo KALMAN_ENV_FILE=/opt/kalman/.env \
  bash kalman-toss-gateway/scripts/run_open_revalidation_backtest.sh \
  --max-trades 20 \
  --backfill-only
```

The pilot checks credentials, minute-data availability, timestamp semantics, cache writes, and reconstruction coverage without selecting a policy.

## Full IEX research run

```bash
sudo KALMAN_ENV_FILE=/opt/kalman/.env \
  bash kalman-toss-gateway/scripts/run_open_revalidation_backtest.sh \
  --start 2023-01-01 \
  --end 2025-12-31 \
  --feed iex
```

Primary outputs:

`/mnt/gdrive/US_ETF/model_lab_v1/results/open_revalidation_v1/status.json`

`/mnt/gdrive/US_ETF/model_lab_v1/results/open_revalidation_v1/open_revalidation_decision.json`

`/mnt/gdrive/US_ETF/model_lab_v1/results/open_revalidation_v1/open_revalidation_candidate_summary.csv`

`/mnt/gdrive/US_ETF/model_lab_v1/results/open_revalidation_v1/open_revalidation_fold_summary.csv`

`/mnt/gdrive/US_ETF/model_lab_v1/results/open_revalidation_v1/open_revalidation_trade_audit.parquet`

## Promotion sequence

1. IEX historical paired backtest.
2. Freeze any surviving rule and parameters.
3. Repeat with SIP historical data if available.
4. Replay on the true 2026-09-03+ R5.1 prospective trades as they mature.
5. Run prospective shadow at the actual open-revalidation cadence.
6. Consider production only after forward evidence confirms the historical result.
