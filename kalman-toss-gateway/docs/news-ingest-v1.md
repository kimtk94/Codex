# Kalman News/Event Ingestion V1

## Scope

This is an additive sidecar for `US / KR / CRYPTO / GLOBAL`. It does **not** change
R5.1 features, ranks, trade gates, or live execution.

### Source layers

- US corporate: SEC EDGAR submissions API.
- US/global macro: Federal Reserve, BLS CPI, Employment Situation, JOLTS, BEA RSS.
- KR corporate: OpenDART disclosure API.
- KR macro: Bank of Korea monetary-policy and economic-statistics RSS.
- Broad US/KR/CRYPTO/GLOBAL news: GDELT DOC API.
- Historical crypto/SA proxy: existing GDELT CSV can be imported manually.

## Reliability model

`/var/lib/kalman/news/news_spool.sqlite3` is the ingestion truth.

Collection never depends on Google Drive being mounted. Neon and Drive are downstream
sync targets. Failed sync leaves rows pending in SQLite for the next retry.

Drive archive is append-only:

```
/mnt/gdrive/Market_News/v1/raw/YYYY/MM/DD/news_<UTC>_<hash>.jsonl.gz
```

## Point-in-time semantics

- `EXACT_SOURCE_TS`: SEC acceptance timestamp.
- `PUBLISHER_TS`: official RSS publisher timestamp.
- `FIRST_SEEN_TS`: no safe publisher timestamp, e.g. current OpenDART polling.
- `GDELT_OBSERVED_PROXY`: GDELT observed timestamp; never treated as exact publisher time.
- `DATE_ONLY`: research-only date resolution.

Do not forward-fill news features. Later sidecar features must use time decay.

## Server install

After the branch is deployed to `/opt/kalman/app`:

```bash
sudo nano /opt/kalman/.env
sudo /opt/kalman/app/scripts/run_news_ingest_v1.sh selftest
sudo /opt/kalman/app/scripts/install_news_ingest_v1.sh
```

Useful checks:

```bash
systemctl list-timers --all 'kalman-news-*'
journalctl -u kalman-news-collect.service -n 100 --no-pager
journalctl -u kalman-news-sync.service -n 100 --no-pager
cat /opt/kalman/state/news/coverage_status.json
```

## Required / optional environment

SEC collection requires a descriptive User-Agent with a contact:

```env
KALMAN_NEWS_SEC_USER_AGENT="KalmanResearch/1.0 contact@example.com"
```

OpenDART requires:

```env
DART_API_KEY=
```

RSS and GDELT do not require API keys.

Keep `KALMAN_NEWS_NEON_SYNC_ENABLED=false` until the additive Neon schema has been
promoted to production. Collection and Drive archive can run before that.

## Historical import

The existing Drive GDELT/SeekingAlpha historical CSV can be loaded into the durable
spool without pretending its timestamps are exact:

```bash
sudo /opt/kalman/app/scripts/run_news_ingest_v1.sh import-gdelt-csv \
  --input-csv /mnt/gdrive/SeekingAlpha/historical_import/gdelt_seekingalpha_backfill.csv
```

It is tagged `GDELT_OBSERVED_PROXY`.

## Database contract

Schema file:

```
research/quant_stack/news_ingest_v1.sql
```

Tables:

- `news_article`
- `news_entity`
- `news_event`
- `news_source_state`
- `news_coverage_hourly`
- `news_feature_snapshot`

Views:

- `v_news_latest_coverage`
- `v_news_feature_latest`

`news_feature_snapshot` is reserved for a future R5.x challenger sidecar. V1 collection
does not write news into the frozen R5.1 model score.
