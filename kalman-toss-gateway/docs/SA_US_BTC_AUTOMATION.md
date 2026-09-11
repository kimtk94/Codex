# Seeking Alpha × US × BTC server feature worker

The reviewed Colab feature builder is integrated as a server worker at:

```text
engine/sa_us_btc_features.py
scripts/run_sa_us_btc_features.sh
```

It is intentionally independent from the live-trading pipeline. Installing this worker does not enable trading, and its cron line is disabled by default.

## Data flow

```text
Yahoo market data ─┐
                   ├─> engine.sa_us_btc_features
SA CSV adapter ────┘          │
                              ├─ X feature matrix
                              ├─ y forward targets
                              ├─ latest JSON
                              ├─ schema
                              └─ run status
```

The worker keeps BTC calendar-day observations separate from US trading-day observations, uses 365-day volatility annualization for BTC and 252 for US-listed assets, excludes missing tickers from breadth denominators, and separates SA stock factors from SA ETF factors.

## Seeking Alpha input

This module is an adapter, not a scraper.

Default path:

```text
$KALMAN_DATA_ROOT/SeekingAlpha/seeking_alpha_daily.csv
```

Minimum columns:

```csv
date,ticker
```

Recommended stock fields:

```text
asset_type,quant_rating,value,growth,profitability,momentum,eps_revision,
sa_analyst_rating,wall_street_rating,news_sentiment
```

Recommended ETF fields:

```text
asset_type,quant_rating,momentum,expenses,dividends,risk,liquidity,
sa_analyst_rating,news_sentiment
```

Use `asset_type=STOCK` or `asset_type=ETF`. If it is absent, IBIT/FBTC are inferred as ETF and other tickers as STOCK.

## Environment

The server-owned `/opt/kalman/.env` is authoritative.

```env
KALMAN_SA_INPUT_CSV=/mnt/gdrive/SeekingAlpha/seeking_alpha_daily.csv
KALMAN_SA_OUTPUT_DIR=/mnt/gdrive/Market_Features/sa_us_btc
KALMAN_SA_START_DATE=2022-01-01
KALMAN_SA_END_DATE=
KALMAN_SA_ASOF_LAG_BDAYS=0
KALMAN_SA_REQUIRED=false
```

Use `KALMAN_SA_ASOF_LAG_BDAYS=0` only when the snapshot is available before the market session being modeled. Set it to `1` when the snapshot is produced after the close and should become usable on the next business day.

Keep `KALMAN_SA_REQUIRED=false` while the SA feed is not connected. The worker will then produce market-only features. Switch it to `true` once the production SA input is mandatory.

## Install/update on the Linux server

```bash
cd ~/Codex
git pull origin main
cd kalman-toss-gateway
sudo bash scripts/install_server.sh
```

The installer copies the new worker into `/opt/kalman/app`, makes all shell runners executable, and installs the pinned yfinance dependency.

## Manual run first

```bash
sudo /opt/kalman/app/scripts/run_sa_us_btc_features.sh
```

Optional overrides:

```bash
sudo /opt/kalman/app/scripts/run_sa_us_btc_features.sh \
  --start-date 2024-01-01 \
  --sa-asof-lag-bdays 1
```

## Outputs

Default output directory:

```text
$KALMAN_DATA_ROOT/Market_Features/sa_us_btc/
```

Files:

```text
us_btc_sa_features_X_daily.csv
us_btc_targets_y_daily.csv
us_btc_sa_dataset_combined_daily.csv
us_btc_sa_feature_schema.csv
us_btc_sa_features_latest.json
us_btc_sa_run_status.json
```

X and y are intentionally separate to reduce accidental target leakage.

Writes use a temporary file plus atomic replace. The shell wrapper also uses a dedicated flock lock, so overlapping cron runs do not write concurrently.

## Cron

A disabled template is included in `config/kalman.cron.d`:

```cron
# 45 7 * * * root /opt/kalman/app/scripts/run_sa_us_btc_features.sh >> /opt/kalman/logs/sa-us-btc.log 2>&1
```

Do not uncomment it until:

1. a manual run succeeds;
2. the output path is verified;
3. the actual SA snapshot availability time is known;
4. `KALMAN_SA_ASOF_LAG_BDAYS` matches that timing.

The 07:45 KST schedule is only a template, not a production timing recommendation.

## Monitoring

```bash
tail -f /opt/kalman/logs/sa-us-btc.log
cat /mnt/gdrive/Market_Features/sa_us_btc/us_btc_sa_run_status.json
```

This worker does not alter `TRADING_ENABLED`, `LIVE_TRADING_CONFIRM`, `AUTO_TRADE_ENABLED`, or any live-order path.
