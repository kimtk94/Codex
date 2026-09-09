# Kalman Server + Toss Gateway

Server runtime for the existing Investment Hub Unified Colab lineage plus a guarded Toss Securities execution gateway.

## Architecture

`cron -> engine/unified_runner.py -> Neon PostgreSQL -> Vercel viewers`

Live orders are a separate path:

`signal/intent -> /api/order-preview -> risk gates -> /api/orders/live -> Toss Open API`

The model pipeline itself still has `trade_enabled=False`. This is deliberate: calculation promotion and broker execution stay separate.

The server also persists the current US selector into Neon `strategy_signal` as `SHADOW / entry_allowed=false / risk_gate=SHADOW_ONLY`. The automated trading worker refuses these rows. It only accepts an explicitly promoted `BUY / true / PASS` row.

## What changed from Colab

- `google.colab.userdata` is mapped to normal environment variables.
- `/content/drive/MyDrive` is a compatibility symlink to `KALMAN_DATA_ROOT` (default `/opt/kalman/data`).
- Colab `!pip` setup moved into `requirements.txt`.
- `RUN_MODE` is an environment variable, so cron can call `KR_GLOBAL`, `US`, or `CRYPTO_GLOBAL`.
- Google Sheets uses normal Application Default Credentials (`GOOGLE_APPLICATION_CREDENTIALS`).
- Neon DB contract and the validated KR/US/CRYPTO/GLOBAL calculation code are preserved.

## Install

```bash
git clone https://github.com/kimtk94/Codex.git
cd Codex/kalman-toss-gateway
sudo bash scripts/install_server.sh
sudo nano /opt/kalman/.env
```

Seed the former Drive folders into:

```text
/opt/kalman/data/Finance_KR
/opt/kalman/data/Upbit_BTC
```

Then smoke-test the pipeline with trading OFF:

```bash
/opt/kalman/app/scripts/run_pipeline.sh KR_GLOBAL
/opt/kalman/app/scripts/run_pipeline.sh US
/opt/kalman/app/scripts/run_pipeline.sh CRYPTO_GLOBAL
```

Install `config/kalman.cron` only after those runs pass.

## Gateway smoke test

```bash
sudo systemctl restart kalman-toss-gateway
curl http://127.0.0.1:8787/health
```

The expected initial state is:

```json
{"tradingEnabled":false,"liveGateOpen":false}
```

Discover `accountSeq`:

```bash
curl http://127.0.0.1:8787/api/accounts -H "X-Gateway-Secret: $HUB_GATEWAY_SECRET"
```

Buying power now requires an explicit currency and the gateway sends it correctly:

```bash
curl 'http://127.0.0.1:8787/api/buying-power?currency=USD' -H "X-Gateway-Secret: $HUB_GATEWAY_SECRET"
```

## Live-order safety gates

A live order is submitted only when **all** of these pass:

1. `TRADING_ENABLED=true`
2. `LIVE_TRADING_CONFIRM=CONFIRM_LIVE_TRADING`
3. symbol is in `ALLOW_SYMBOLS`
4. per-order cap passes
5. per-symbol cap passes
6. persistent KST daily budget passes
7. Toss buying power / sellable quantity passes
8. `clientOrderId` has never been reserved locally
9. for cron execution, Neon `strategy_signal` is `BUY + entry_allowed=true + risk_gate=PASS` and the matching snapshot is still fresh

The local order guard is stored in `/opt/kalman/state/trading.sqlite3`.

Preview first:

```bash
curl -X POST http://127.0.0.1:8787/api/order-preview \
  -H 'Content-Type: application/json' \
  -H "X-Gateway-Secret: $HUB_GATEWAY_SECRET" \
  -d '{"client_order_id":"kalman-test-001","symbol":"IONQ","side":"BUY","order_type":"MARKET","order_amount":"2"}'
```

Only after end-to-end parity and a deliberate live promotion, set:

```env
TRADING_ENABLED=true
LIVE_TRADING_CONFIRM=CONFIRM_LIVE_TRADING
```

Then `/api/orders/live` uses the same request body as preview and can submit a real order.

## Important

Do not put real API keys, account identifiers, static IPs, or service-account JSON in Git. All real secrets belong only in `/opt/kalman/.env` or `/opt/kalman/secrets/`.

## Automated execution worker

`config/kalman.cron` includes an hourly `run_auto_trade.sh` poll, but it is inert until all live gates are deliberately opened. Current Unified US runs write only SHADOW signals, so no live order can be generated from the present model state.

```env
AUTO_TRADE_ENABLED=false
AUTO_TRADE_ORDER_USD=2
AUTO_TRADE_MAX_SIGNAL_AGE_MINUTES=90
```

A future live promotion must be explicit in the strategy layer. The executor itself does not reinterpret model scores or convert a Shadow selector into a BUY.

## Unified source integrity

`engine/_unified_payload_*.b64` is the LZMA+base64 representation of the validated
`Investment_Hub_Unified_Colab_v1` server port. `engine/unified_runner.py` verifies
the decoded SHA-256 before executing it, so a partial or edited payload fails closed.
The Drive notebook remains the research/source lineage; the server payload is the
production runtime copy with Colab APIs shimmed through `engine.colab_compat`.
