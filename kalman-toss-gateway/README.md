# Kalman Server + Toss Gateway

Server runtime for the Investment Hub Unified lineage plus a guarded Toss Securities execution gateway.

## Architecture

Pipeline:

`cron -> engine/unified_runner.py -> Neon PostgreSQL -> Vercel viewers`

Automated trading is a separate stateful path:

`strategy_signal -> position_manager(reconcile/exit) -> auto_trade(entry) -> Toss Open API`

The model pipeline and broker execution remain separated. Current Unified US output is still written to Neon as SHADOW; the execution layer never rewrites the frozen model artifact or silently promotes the database signal.

## Install / update

```bash
git clone https://github.com/kimtk94/Codex.git
cd Codex/kalman-toss-gateway
sudo bash scripts/install_server.sh
sudo nano /opt/kalman/.env
```

For an existing server:

```bash
cd ~/Codex
git pull origin main
cd kalman-toss-gateway
sudo bash scripts/install_server.sh
```

Google Drive is mounted at `/mnt/gdrive` by `kalman-gdrive.service`; `/content/drive/MyDrive` is the compatibility symlink used by the former Colab lineage.

## Pipeline smoke test

Keep trading OFF while validating the research/data pipeline:

```bash
sudo /opt/kalman/app/scripts/preflight.sh
sudo /opt/kalman/app/scripts/smoke_test.sh --pipelines
```

The frozen sklearn models require `scikit-learn==1.6.1`; this is pinned in `requirements.txt`.

## Toss gateway smoke test

```bash
sudo systemctl restart kalman-toss-gateway
curl http://127.0.0.1:8787/health
```

Expected deployment state:

```json
{"tradingEnabled":false,"liveGateOpen":false}
```

Real credentials and account identifiers belong only in `/opt/kalman/.env`, never in Git.

## Automated trade lifecycle

`run_auto_trade.sh` takes one exclusive lock and always runs the position manager before the entry worker:

```text
ENTRY_RESERVED
  -> ENTRY_SUBMITTED
  -> OPEN
  -> hold for 4 distinct US canonical signal buckets
  -> EXIT_RESERVED
  -> EXIT_SUBMITTED
  -> CLOSED
```

The bot does not treat an accepted order as a filled position. It queries Toss order detail and records `execution.filledQuantity` before moving to `OPEN`. A terminal partial exit reduces `remaining_quantity`; the residual is retried only on a later scheduled cycle.

Unexpected broker/local quantity mismatches, ambiguous POST outcomes, and unresolved order states go to a manual-reconcile state and block new entries instead of guessing or duplicating an order.

By default the bot manages one position at a time. `AUTO_TRADE_REQUIRE_ACCOUNT_FLAT=true` also requires the brokerage account to have no holdings and no open orders before the first automated entry. This is intended for the clean handoff after any legacy holdings are manually liquidated.

Read-only status:

```bash
sudo /opt/kalman/app/scripts/trading_status.sh
```

## DRY_RUN first

Repository defaults never submit an order:

```env
AUTO_TRADE_ENABLED=false
AUTO_TRADE_EXECUTION_MODE=DRY_RUN
TRADING_ENABLED=false
LIVE_TRADING_CONFIRM=
```

To exercise the read-only broker/account path while keeping live orders impossible:

```env
AUTO_TRADE_ENABLED=true
AUTO_TRADE_EXECUTION_MODE=DRY_RUN
TRADING_ENABLED=false
LIVE_TRADING_CONFIRM=
```

DRY_RUN reports the latest eligible signal, broker holdings/open orders, USD `cashBuyingPower`, market window, proposed size, and managed-position state.

## Signal policies

`APPROVED_ONLY` is the default and requires all of:

```text
signal=BUY
entry_allowed=true
risk_gate=PASS
position_state=FLAT
payload.live_execution=true
```

`SHADOW_CANARY` is an explicit external canary path. It does not alter the frozen DB signal and additionally requires:

```text
signal=SHADOW
payload.allow_trade_shadow=true
payload.shadow_entry_this_signal=true
AUTO_TRADE_SHADOW_CONFIRM=CONFIRM_SHADOW_CANARY
```

Current research governance still controls whether a signal is actually eligible; the execution layer does not manufacture one.

## Entry sizing

The safe default remains a fixed USD canary:

```env
AUTO_TRADE_SIZING_MODE=FIXED_USD
AUTO_TRADE_ORDER_USD=2
AUTO_TRADE_MAX_ORDER_USD=2
```

Cash-proportional sizing is available but still clamped by `AUTO_TRADE_MAX_ORDER_USD` and the KRW entry risk limits:

```env
AUTO_TRADE_SIZING_MODE=CASH_FRACTION
AUTO_TRADE_CASH_FRACTION=0.10
AUTO_TRADE_CASH_RESERVE_USD=0
AUTO_TRADE_MIN_ORDER_USD=1
AUTO_TRADE_MAX_ORDER_USD=2
```

The execution layer no longer maintains a symbol allowlist. Existing global live gates, broker/account checks, per-order limits, and daily limits remain in force.

## Live safety gates

A new automated BUY needs, at minimum:

1. exact `AUTO_TRADE_STRATEGY_VERSION` lock;
2. an eligible signal under the selected signal policy;
3. fresh READY Neon snapshot;
4. account/bot-position reconciliation;
5. Toss US fractional-order session window;
6. positive broker USD buying power;
7. per-order and daily BUY caps;
8. persistent local `clientOrderId` idempotency;
9. `TRADING_ENABLED=true` and `LIVE_TRADING_CONFIRM=CONFIRM_LIVE_TRADING`.

Managed SELL exits are treated as risk-reducing: they still require both global live gates and Toss sellable quantity/session checks, while entry notional caps do not block an already-managed exit.

The local order/position state is stored in `/opt/kalman/state/trading.sqlite3`. Gateway and workers share one Toss OAuth token cache under `/opt/kalman/state/toss_oauth_token.json`.

## Important

Do not place real API keys, full account numbers, static IPs, OAuth tokens, or service-account JSON in Git. Keep them only in `/opt/kalman/.env` or `/opt/kalman/secrets/`.

## Unified source integrity

`engine/_unified_payload_*.b64` is the LZMA+base64 representation of the validated `Investment_Hub_Unified_Colab_v1` server port. `engine/unified_runner.py` verifies the decoded SHA-256 before executing it, so a partial or edited payload fails closed. The Drive notebook remains the research/source lineage; the server payload is the runtime copy with Colab APIs shimmed through `engine.colab_compat`.
