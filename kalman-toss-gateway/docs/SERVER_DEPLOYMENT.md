# Kalman Linux Server Deployment

This runbook moves the current Unified Colab runtime to `/opt/kalman` and keeps live trading closed during deployment.

## 1. Pull and install

```bash
cd ~/Codex
git pull origin main
cd kalman-toss-gateway
sudo bash scripts/install_server.sh
```

The installer creates:

- `/opt/kalman/.venv`
- `/opt/kalman/.env`
- `/opt/kalman/data`
- `/opt/kalman/logs`
- `/opt/kalman/state`
- `/opt/kalman/secrets`
- `kalman-toss-gateway.service`

`.env` is parsed with `python-dotenv`, not shell `source`. Real secrets remain outside Git.

## 2. Configure secrets

```bash
sudo nano /opt/kalman/.env
```

Minimum pipeline requirement:

```env
DATABASE_URL_WRITER='postgresql://...'
KALMAN_DATA_ROOT=/opt/kalman/data
```

Keep all execution gates closed:

```env
TRADING_ENABLED=false
LIVE_TRADING_CONFIRM=
AUTO_TRADE_ENABLED=false
```

For Toss read-only tests add the real static egress IP and OAuth credentials:

```env
TOSS_CLIENT_ID='...'
TOSS_CLIENT_SECRET='...'
HUB_GATEWAY_SECRET='...'
EXPECTED_EGRESS_IP='x.x.x.x'
TOSS_ACCOUNT=
```

`TOSS_ACCOUNT` is populated after account discovery succeeds.

## 3. Seed legacy data

Copy the former Drive-backed state into:

```text
/opt/kalman/data/Finance_KR
/opt/kalman/data/Upbit_BTC
```

If CRYPTO still reads Google Sheets, place its service-account JSON under `/opt/kalman/secrets/` and set `GOOGLE_APPLICATION_CREDENTIALS` in `.env`.

## 4. Preflight

```bash
sudo /opt/kalman/app/scripts/preflight.sh
```

It checks:

- trading gates are closed
- 15 Unified payload chunks and SHA-256 integrity
- Neon connectivity
- expected public egress IP
- required commands and Python venv
- data directories
- credential completeness warnings

Any `[FAIL]` blocks deployment progression.

## 5. Read-only Gateway test

```bash
sudo systemctl restart kalman-toss-gateway
sudo /opt/kalman/app/scripts/smoke_test.sh
```

This may call account, holdings and buying-power endpoints, but it never calls the live order endpoint.

After `/api/accounts` succeeds, put the returned `accountSeq` into `TOSS_ACCOUNT`, restart the service, and repeat the smoke test.

## 6. Full parity smoke

```bash
sudo /opt/kalman/app/scripts/smoke_test.sh --pipelines
```

It runs, in order:

1. `KR_GLOBAL`
2. `US`
3. `CRYPTO_GLOBAL`

Only if all finish successfully is `/opt/kalman/state/smoke.ok` written.

## 7. Install cron

```bash
sudo /opt/kalman/app/scripts/install_cron.sh
```

The installer requires a successful smoke stamp from the previous 24 hours and installs `/etc/cron.d/kalman`.

Inspect it with:

```bash
cat /etc/cron.d/kalman
```

Monitor with:

```bash
tail -f /opt/kalman/logs/kr.log
tail -f /opt/kalman/logs/us.log
tail -f /opt/kalman/logs/crypto.log
journalctl -u kalman-toss-gateway -f
```

## 8. Live trading stays OFF

Cron installation does not promote the strategy and does not enable trading. Current Shadow signals remain ineligible for execution. Live activation is a separate change and should only happen after parity, Toss account reads, buying-power reads, duplicate-order rejection and a deliberate micro-order test are all verified.
