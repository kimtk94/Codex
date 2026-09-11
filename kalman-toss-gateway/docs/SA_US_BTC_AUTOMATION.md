# Seeking Alpha × US × BTC server automation

This integration has two independent stages:

```text
authorized SA source
  -> engine.sa_collector
  -> SeekingAlpha/seeking_alpha_daily.csv
  -> engine.sa_us_btc_features
  -> Market_Features/sa_us_btc/*
```

The collector is deliberately not a website scraper. Use only an authorized/licensed API/data feed or a CSV/export you are permitted to process.

## Components

```text
engine/sa_collector.py
engine/sa_us_btc_features.py
scripts/run_sa_collector.sh
scripts/run_sa_us_btc_features.sh
scripts/run_sa_us_btc_refresh.sh
```

`run_sa_us_btc_refresh.sh` is the normal automation entry point: it runs the collector first, then rebuilds the US/BTC features.

The integration does not enable live trading and does not modify the KR/US/CRYPTO pipeline entry points.

## Collector modes

### 1. disabled

Default.

```env
KALMAN_SA_COLLECTOR_MODE=disabled
KALMAN_SA_REQUIRED=false
```

The feature worker still runs in market-only mode.

### 2. drop_csv

Use this when an authorized export/file is placed in the incoming directory.

```env
KALMAN_SA_COLLECTOR_MODE=drop_csv
KALMAN_SA_DROP_CSV=/mnt/gdrive/SeekingAlpha/incoming/seeking_alpha_latest.csv
```

The collector validates and normalizes the file, appends it to canonical history, deduplicates by `date,ticker`, archives the source file, and atomically writes:

```text
/mnt/gdrive/SeekingAlpha/seeking_alpha_daily.csv
```

### 3. licensed_http

Use this only with an API/data-feed endpoint you are authorized to automate.

```env
KALMAN_SA_COLLECTOR_MODE=licensed_http
KALMAN_SA_FEED_URL='https://licensed-provider.example/...'
KALMAN_SA_FEED_TOKEN='...'
KALMAN_SA_FEED_AUTH_HEADER=Authorization
KALMAN_SA_FEED_AUTH_SCHEME=Bearer
KALMAN_SA_FEED_FORMAT=auto
KALMAN_SA_FEED_JSON_PATH=
```

The HTTP collector supports retry/backoff, redirects, ETag, Last-Modified, JSON/CSV payloads, and source archives.

Keep the real URL/token only in `/opt/kalman/.env`; never commit them.

If the licensed schema differs, map source fields with:

```env
KALMAN_SA_FIELD_MAP_JSON='{"symbol":"ticker","asOfDate":"date","quantScore":"quant_rating"}'
```

For JSON payloads nested under a known path:

```env
KALMAN_SA_FEED_JSON_PATH=data.rows
```

## Canonical SA schema

Minimum:

```text
date
ticker
```

Canonical fields:

```text
date
ticker
asset_type
quant_rating
value
growth
profitability
momentum
eps_revision
expenses
dividends
risk
liquidity
sa_analyst_rating
wall_street_rating
news_sentiment
```

Stock-oriented fields and ETF-oriented fields can coexist in the same history; irrelevant fields can be blank.

## Feature semantics

The feature worker:

- keeps BTC calendar-day observations separate from US trading-day observations;
- annualizes BTC volatility with 365 and US-listed assets with 252;
- excludes missing tickers from breadth denominators;
- separates SA stock factors from SA ETF factors;
- keeps X features separate from forward y targets;
- writes atomically;
- uses an independent flock lock to prevent overlapping runs.

## Environment

Core settings:

```env
KALMAN_SA_INPUT_CSV=/mnt/gdrive/SeekingAlpha/seeking_alpha_daily.csv
KALMAN_SA_OUTPUT_DIR=/mnt/gdrive/Market_Features/sa_us_btc
KALMAN_SA_START_DATE=2022-01-01
KALMAN_SA_END_DATE=
KALMAN_SA_ASOF_LAG_BDAYS=0
KALMAN_SA_REQUIRED=false

KALMAN_SA_COLLECTOR_MODE=disabled
KALMAN_SA_DROP_CSV=/mnt/gdrive/SeekingAlpha/incoming/seeking_alpha_latest.csv
KALMAN_SA_ARCHIVE_DIR=/mnt/gdrive/SeekingAlpha/archive
KALMAN_SA_COLLECTOR_STATE=/opt/kalman/state/sa_collector.json
```

Use `KALMAN_SA_ASOF_LAG_BDAYS=0` only when the snapshot is available before the market session being modeled. If it is only available after the close, use `1`.

Keep `KALMAN_SA_REQUIRED=false` while SA is optional. Once production must fail without SA data, switch it to `true`.

## Server install/update

```bash
cd ~/Codex
git pull origin main
cd kalman-toss-gateway
sudo bash scripts/install_server.sh
```

The installer recreates the virtual environment dependencies, copies the engine/scripts/config into `/opt/kalman/app`, and makes shell runners executable.

## Manual validation

Collector only:

```bash
sudo /opt/kalman/app/scripts/run_sa_collector.sh
```

Feature worker only:

```bash
sudo /opt/kalman/app/scripts/run_sa_us_btc_features.sh
```

Full refresh:

```bash
sudo /opt/kalman/app/scripts/run_sa_us_btc_refresh.sh
```

Inspect:

```bash
cat /opt/kalman/state/sa_collector.json
cat /mnt/gdrive/Market_Features/sa_us_btc/us_btc_sa_run_status.json
```

The collector runner checks the Google Drive mount before writing to any configured `/mnt/gdrive` SA path, so a failed mount does not silently create local replacement files.

## Output files

```text
/mnt/gdrive/SeekingAlpha/
├── seeking_alpha_daily.csv
├── incoming/
└── archive/

/mnt/gdrive/Market_Features/sa_us_btc/
├── us_btc_sa_features_X_daily.csv
├── us_btc_targets_y_daily.csv
├── us_btc_sa_dataset_combined_daily.csv
├── us_btc_sa_feature_schema.csv
├── us_btc_sa_features_latest.json
└── us_btc_sa_run_status.json
```

## Cron

The repo contains a disabled template:

```cron
# 45 7 * * * root /opt/kalman/app/scripts/run_sa_us_btc_refresh.sh >> /opt/kalman/logs/sa-us-btc.log 2>&1
```

Do not enable it until:

1. a full manual refresh succeeds;
2. the authorized SA input mode is configured;
3. the source snapshot delivery time is known;
4. `KALMAN_SA_ASOF_LAG_BDAYS` matches that delivery time;
5. the output files and run-state JSON have been checked.

07:45 KST is a placeholder only, not a recommended production time.

## Monitoring

```bash
tail -f /opt/kalman/logs/sa-us-btc.log
cat /opt/kalman/state/sa_collector.json
cat /mnt/gdrive/Market_Features/sa_us_btc/us_btc_sa_run_status.json
```

This automation does not alter `TRADING_ENABLED`, `LIVE_TRADING_CONFIRM`, `AUTO_TRADE_ENABLED`, or any live-order path.
