# Kalman Toss Gateway

Private trading gateway for `kalman-investment-hub-v2` → Toss Securities Open API.

## Safety state

This initial version is intentionally **read-only**.

- `TRADING_ENABLED=false` by default
- No live order submission code is included yet
- `/api/order-probe` only validates LIVE MICRO risk rules; it never sends an order
- Real secrets and the full static IP must stay in the server `.env`, never in Git

## LIVE MICRO limits

- Total capital limit: 30,000 KRW
- Per-symbol cap: QQQ 10,000 / NVDA 10,000 / IONQ 10,000 KRW
- Single-order cap: 5,000 KRW
- Allowed symbols only: QQQ, NVDA, IONQ

## Server setup

1. Register the server's full public static IP in Toss WTS → Settings → Open API → Allowed IP.
2. Copy `.env.example` to `.env` on the server.
3. Fill only the server-side `.env` with:
   - `TOSS_CLIENT_ID`
   - `TOSS_CLIENT_SECRET`
   - `TOSS_ACCOUNT`
   - `HUB_GATEWAY_SECRET`
   - `EXPECTED_EGRESS_IP`
4. Keep `TRADING_ENABLED=false` for the first smoke tests.

## Docker

```bash
docker build -t kalman-toss-gateway .
docker run --rm --env-file .env -p 8787:8787 kalman-toss-gateway
```

## Smoke tests

Health check:

```bash
curl http://127.0.0.1:8787/health
```

Expected: `tradingEnabled: false`.

Authenticated market data:

```bash
curl http://127.0.0.1:8787/api/prices \
  -H "X-Gateway-Secret: $HUB_GATEWAY_SECRET"
```

Holdings:

```bash
curl http://127.0.0.1:8787/api/holdings \
  -H "X-Gateway-Secret: $HUB_GATEWAY_SECRET"
```

Buying power:

```bash
curl http://127.0.0.1:8787/api/buying-power \
  -H "X-Gateway-Secret: $HUB_GATEWAY_SECRET"
```

Risk-only order probe (does not execute):

```bash
curl -X POST http://127.0.0.1:8787/api/order-probe \
  -H "Content-Type: application/json" \
  -H "X-Gateway-Secret: $HUB_GATEWAY_SECRET" \
  -d '{"symbol":"IONQ","amount_krw":3000}'
```

## Activation gate before live orders

Do not add live order execution until all of the following pass:

1. Static outbound IP confirmed from the server.
2. Toss IP allowlist confirmed.
3. OAuth token issuance succeeds.
4. QQQ/NVDA/IONQ price query succeeds.
5. Holdings query succeeds.
6. Buying-power query succeeds.
7. Investment Hub → Gateway authentication succeeds over HTTPS.
8. LIVE MICRO limits are verified with rejection tests.

Only after that should `POST /api/v1/orders` integration be added behind an explicit trading-enable switch and idempotency protection.
