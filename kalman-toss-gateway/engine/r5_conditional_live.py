"""R5.1 conditional LIVE executor.

Allocation contract:
- low confidence: Rank1 KRW 10,000 + KRW 10,000 cash
- close Rank1/Rank2 score gap: Rank1 KRW 10,000 + Rank2 KRW 10,000
- otherwise: Rank1 KRW 20,000

This runner only opens a new managed position per symbol. Existing positions are
left to position_manager; it does not pyramid/add-on under the conditional
profile.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from decimal import Decimal, ROUND_DOWN
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

from app.config import Settings
from app.executor import TradeLedger, execute_order
from app.managed_positions import ManagedPositionStore
from app.market_guard import unwrap, us_fractional_order_window
from app.toss_client import TossClient
from engine.auto_trade import (
    TARGET_EXIT_BUCKETS,
    _client_order_id,
    _entry_exit_window_check,
    _exit_priority_positions,
    _exit_priority_summary,
    _has_open_buy_order,
    _holding_items,
    _nonzero_holdings,
    _open_order_items,
    _symbol_position_quantity,
    load_signal,
)
from engine.r5_conditional_policy import (
    decide,
    rank2_from_payload,
    score_from_payload,
)


POLICY = "R5_LIVE_CONDITIONAL"
CONFIRM = "CONFIRM_R5_LIVE_CONDITIONAL_20000"


def _score(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_from_payload(payload):
    return score_from_payload(payload if isinstance(payload, dict) else {})


def _snapshot_rank_context(snapshot: dict, signal: dict) -> tuple[float | None, str | None, float | None]:
    if not isinstance(snapshot, dict):
        return None, None, None

    rank1_symbol = str(signal.get("symbol") or "").upper()
    if not rank1_symbol:
        return None, None, None

    rows: list[tuple[int | None, str, float]] = []
    snapshot_as_of = None

    # API-shaped snapshot: payload.top3 + data_as_of.
    payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else None
    top = payload.get("top3") if isinstance(payload, dict) else None
    if isinstance(top, list) and top:
        snapshot_as_of = snapshot.get("data_as_of") or payload.get("data_as_of")
        for row in top:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").upper()
            score = _score(row.get("model_score"))
            try:
                rank = int(row.get("rank"))
            except (TypeError, ValueError):
                rank = None
            if symbol and score is not None:
                rows.append((rank, symbol, score))
        rows.sort(key=lambda x: (x[0] is None, x[0] if x[0] is not None else 9999))

    # Server web-snapshot shape:
    # today_selector.selected_symbol + model_universe[*].model_score.
    if not rows:
        selector = snapshot.get("today_selector")
        universe = snapshot.get("model_universe")
        if not isinstance(selector, dict) or not isinstance(universe, dict):
            return None, None, None

        selected = str(selector.get("selected_symbol") or "").upper()
        selected_score = _score(selector.get("model_score"))
        snapshot_as_of = snapshot.get("model_as_of_utc") or selector.get("as_of_utc")

        scored: list[tuple[str, float]] = []
        for symbol, row in universe.items():
            if not isinstance(row, dict):
                continue
            score = _score(row.get("model_score"))
            symbol = str(symbol or "").upper()
            if symbol and score is not None:
                scored.append((symbol, score))
        scored.sort(key=lambda x: (-x[1], x[0]))

        if not scored or selected != scored[0][0] or selected != rank1_symbol:
            return None, None, None
        if selected_score is not None and abs(selected_score - scored[0][1]) > 1e-15:
            return None, None, None

        rows = [(idx, symbol, score) for idx, (symbol, score) in enumerate(scored, start=1)]

    if not rows or rows[0][1] != rank1_symbol:
        return None, None, None

    signal_as_of = signal.get("as_of")
    if signal_as_of is not None and snapshot_as_of:
        try:
            from datetime import datetime, timezone
            def _utc(value):
                if isinstance(value, datetime):
                    dt = value
                else:
                    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            if _utc(signal_as_of) != _utc(snapshot_as_of):
                return None, None, None
        except Exception:
            return None, None, None

    rank2 = next((row for row in rows[1:] if row[1] != rank1_symbol), None)
    return rows[0][2], (rank2[1] if rank2 else None), (rank2[2] if rank2 else None)

def _rank_context_from_web_snapshot(signal: dict) -> tuple[float | None, str | None, float | None]:
    configured = os.environ.get("KALMAN_WEB_SNAPSHOT_PATH", "").strip()
    data_root = Path(os.environ.get("KALMAN_DATA_ROOT", "/mnt/gdrive/US_ETF")).expanduser()
    drive_root = data_root.parent if data_root.name == "US_ETF" else Path("/mnt/gdrive")
    candidates = [
        Path(configured).expanduser() if configured else None,
        Path("/content/drive/MyDrive/Upbit_BTC/docs/investment_hub_web_snapshot_latest.json"),
        drive_root / "Upbit_BTC/docs/investment_hub_web_snapshot_latest.json",
        Path("/mnt/gdrive/Upbit_BTC/docs/investment_hub_web_snapshot_latest.json"),
    ]
    seen = set()
    for path in candidates:
        if path is None:
            continue
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            if not path.is_file():
                continue
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        ctx = _snapshot_rank_context(snapshot, signal)
        if ctx[0] is not None:
            return ctx
    return None, None, None


def _rank_context_from_same_run(signal: dict) -> tuple[float | None, str | None, float | None]:
    payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
    r1 = _score_from_payload(payload)
    r2_symbol, r2_score = rank2_from_payload(payload)
    if r2_symbol and r2_score is not None:
        return r1, r2_symbol, r2_score

    db_url = os.environ.get("DATABASE_URL_WRITER")
    if not db_url:
        return r1, None, None

    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT symbol, payload
            FROM strategy_signal
            WHERE market='US'
              AND run_id=%s
              AND strategy_version=%s
              AND as_of=%s
            """,
            (signal["run_id"], signal["strategy_version"], signal["as_of"]),
        )
        scored = []
        for symbol, row_payload in cur.fetchall():
            score = _score_from_payload(row_payload)
            if score is not None:
                scored.append((str(symbol).upper(), score))

    if scored:
        scored.sort(key=lambda x: x[1], reverse=True)
        top1_symbol = str(signal["symbol"]).upper()
        if r1 is None:
            for symbol, score in scored:
                if symbol == top1_symbol:
                    r1 = score
                    break
        others = [(s, v) for s, v in scored if s != top1_symbol]
        if r1 is not None and others:
            return r1, others[0][0], others[0][1]

    snapshot_r1, snapshot_r2_symbol, snapshot_r2_score = _rank_context_from_web_snapshot(signal)
    if snapshot_r1 is not None:
        return snapshot_r1, snapshot_r2_symbol, snapshot_r2_score
    return r1, None, None


def _order_usd(target_krw: int, usd_krw: Decimal, cash_available: Decimal) -> Decimal | None:
    if usd_krw <= 0:
        return None
    raw = (Decimal(target_krw) / usd_krw).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    amount = min(raw, cash_available).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    minimum = Decimal(os.environ.get("AUTO_TRADE_MIN_ORDER_USD", "1"))
    return amount if amount >= minimum else None


async def main_async() -> int:
    load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)

    if os.environ.get("AUTO_TRADE_ENABLED", "false").lower() != "true":
        print("AUTO_TRADE_DISABLED")
        return 0
    if os.environ.get("AUTO_TRADE_EXECUTION_MODE", "").upper() != "LIVE":
        print("R5_CONDITIONAL_REQUIRES_LIVE")
        return 2
    if os.environ.get("AUTO_TRADE_SIGNAL_POLICY", "").upper() != POLICY:
        print("R5_CONDITIONAL_POLICY_NOT_SELECTED")
        return 2
    if os.environ.get("AUTO_TRADE_CONDITIONAL_CONFIRM", "") != CONFIRM:
        print("R5_CONDITIONAL_CONFIRMATION_MISSING")
        return 2

    strategy = os.environ.get("AUTO_TRADE_STRATEGY_VERSION", "").strip()
    if strategy != "R5.1_BASE_HGB":
        print("R5_CONDITIONAL_STRATEGY_MISMATCH")
        return 2

    gap_threshold = float(os.environ["AUTO_TRADE_CONDITIONAL_GAP_THRESHOLD"])
    confidence_threshold = float(os.environ["AUTO_TRADE_CONDITIONAL_CONFIDENCE_THRESHOLD"])
    total_krw = int(os.environ.get("AUTO_TRADE_CONDITIONAL_TOTAL_KRW", "20000"))
    if total_krw != 20000:
        raise RuntimeError("conditional LIVE total must be KRW 20000")

    settings = Settings()
    if not settings.live_gate_open:
        print("LIVE_GATE_CLOSED")
        return 2

    store = ManagedPositionStore(settings.state_db_path)
    active = store.active()
    exit_priority = _exit_priority_positions(active)
    if exit_priority:
        print(json.dumps({
            "executionAttempted": False,
            "reason": "ENTRY_BLOCKED_PENDING_EXIT_PRIORITY",
            "exitPriorityPositions": _exit_priority_summary(exit_priority),
        }, ensure_ascii=False, default=str))
        return 0

    # Use the frozen R5.1 Top1 signal eligibility contract; only allocation is changed.
    signal = load_signal("LIVE", strategy, "R5_LIVE_TOP1")
    if not signal:
        print("NO_ELIGIBLE_SIGNAL")
        return 0

    payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
    if str(signal.get("signal") or "").upper() != "SHADOW":
        print("LIVE_SIGNAL_GATE_FAILED")
        return 2
    if str(payload.get("allow_trade_shadow") or "").lower() != "true":
        print("LIVE_SIGNAL_GATE_FAILED")
        return 2

    rank1_score, rank2_symbol, rank2_score = _rank_context_from_same_run(signal)
    if rank1_score is None:
        print("CONDITIONAL_SCORE_MISSING_RANK1")
        return 0
    if rank1_score > confidence_threshold and (not rank2_symbol or rank2_score is None):
        print("CONDITIONAL_SCORE_MISSING_RANK2")
        return 0
    decision = decide(
        rank1_symbol=str(signal["symbol"]),
        rank1_score=rank1_score,
        rank2_symbol=rank2_symbol,
        rank2_score=rank2_score,
        gap_threshold=gap_threshold,
        confidence_threshold=confidence_threshold,
        total_krw=total_krw,
    )

    client = TossClient(settings)
    window_open, window_info = await us_fractional_order_window(client)
    if not window_open:
        print("US_FRACTIONAL_ORDER_WINDOW_CLOSED")
        return 0
    window_ok, window_detail = _entry_exit_window_check(
        window_info,
        anchor_signal_as_of=signal["as_of"],
        strategy_version=signal["strategy_version"],
        target_exit_buckets=TARGET_EXIT_BUCKETS,
    )
    if not window_ok:
        print(json.dumps({
            "executionAttempted": False,
            "reason": "ENTRY_BLOCKED_FRIDAY_FLAT",
            "fridayFlatGate": window_detail,
        }, ensure_ascii=False, default=str))
        return 0

    holdings = _holding_items(await client.holdings())
    open_orders = _open_order_items(await client.orders("OPEN"))
    buying_power = unwrap(await client.buying_power("USD")) or {}
    cash_usd = Decimal(str(buying_power.get("cashBuyingPower") or "0"))
    fx_payload = unwrap(await client.exchange_rate("USD", "KRW")) or {}
    usd_krw = Decimal(str(fx_payload.get("rate") or "0"))
    reserve = Decimal(os.environ.get("AUTO_TRADE_CASH_RESERVE_USD", "0"))
    remaining_cash = max(Decimal("0"), cash_usd - reserve)

    max_active = int(os.environ.get("AUTO_TRADE_MAX_ACTIVE_POSITIONS", "3"))
    results = []
    active_symbols = {str(p.get("symbol") or "").upper() for p in active}
    planned_new = [s for s, _ in decision.legs_krw if s.upper() not in active_symbols]
    if len(active) + len(planned_new) > max_active:
        print(json.dumps({
            "executionAttempted": False,
            "reason": "MAX_ACTIVE_POSITIONS_REACHED",
            "active": len(active),
            "plannedNew": len(planned_new),
            "maxActive": max_active,
            "decision": decision.__dict__,
        }, ensure_ascii=False, default=str))
        return 0

    for leg_index, (symbol, target_krw) in enumerate(decision.legs_krw, start=1):
        symbol = symbol.upper()

        # Conditional profile deliberately disables pyramiding. A leg already
        # active is idempotently skipped; the next missing leg can still fill.
        if symbol in active_symbols:
            results.append({"symbol": symbol, "status": "SKIP_ALREADY_ACTIVE"})
            continue
        if _symbol_position_quantity(holdings, symbol) > 0:
            results.append({"symbol": symbol, "status": "SKIP_UNMANAGED_BROKER_POSITION"})
            continue
        if _has_open_buy_order(open_orders, symbol):
            results.append({"symbol": symbol, "status": "SKIP_OPEN_BUY_ORDER"})
            continue

        amount_usd = _order_usd(target_krw, usd_krw, remaining_cash)
        if amount_usd is None:
            results.append({"symbol": symbol, "status": "SKIP_INSUFFICIENT_CASH"})
            continue

        client_order_id = _client_order_id(signal["run_id"], symbol)
        reserved, position = store.reserve_entry(
            run_id=signal["run_id"],
            symbol=symbol,
            strategy_version=signal["strategy_version"],
            signal_as_of=signal["as_of"].isoformat(),
            client_order_id=client_order_id,
            target_exit_buckets=TARGET_EXIT_BUCKETS,
        )
        if not reserved or not position:
            results.append({"symbol": symbol, "status": "SKIP_RESERVATION_FAILED"})
            continue

        request = SimpleNamespace(
            client_order_id=client_order_id,
            symbol=symbol,
            side="BUY",
            order_type="MARKET",
            time_in_force="DAY",
            quantity=None,
            order_amount=str(amount_usd),
            price=None,
        )

        try:
            result = await execute_order(settings, request)
        except Exception as exc:
            guard = TradeLedger(settings.state_db_path).get(client_order_id)
            if guard and guard.get("status") == "AMBIGUOUS":
                store.mark_ambiguous_entry(
                    position["position_id"],
                    f"conditional submission ambiguous: {guard.get('error') or exc}",
                )
            else:
                store.mark_entry_aborted(
                    position["position_id"], f"{type(exc).__name__}: {exc}"
                )
            raise

        if not result.get("allowed"):
            store.mark_entry_aborted(
                position["position_id"], f"conditional entry blocked: {result.get('reason')}"
            )
            results.append({"symbol": symbol, "status": "BLOCKED", "result": result})
            continue

        TradeLedger(settings.state_db_path).patch_telemetry(
            client_order_id,
            {
                "signal_context": {
                    "execution_mode": "LIVE",
                    "signal_policy": POLICY,
                    "strategy_version": signal["strategy_version"],
                    "run_id": signal["run_id"],
                    "signal_as_of": signal["as_of"].isoformat(),
                    "conditional_regime": decision.regime,
                    "rank1_symbol": decision.rank1_symbol,
                    "rank1_score": decision.rank1_score,
                    "rank2_symbol": decision.rank2_symbol,
                    "rank2_score": decision.rank2_score,
                    "relative_gap": decision.relative_gap,
                    "gap_threshold": gap_threshold,
                    "confidence_threshold": confidence_threshold,
                    "target_leg_krw": target_krw,
                    "conditional_total_krw": total_krw,
                    "conditional_cash_krw": decision.cash_krw,
                    "leg_index": leg_index,
                }
            },
        )

        order_id = result.get("orderId")
        if not order_id:
            store.mark_ambiguous_entry(
                position["position_id"], "conditional submission returned no orderId"
            )
            results.append({"symbol": symbol, "status": "AMBIGUOUS_NO_ORDER_ID"})
            continue

        store.mark_entry_submitted(position["position_id"], order_id)
        remaining_cash -= amount_usd
        active_symbols.add(symbol)
        results.append({
            "symbol": symbol,
            "status": "SUBMITTED",
            "targetKrw": target_krw,
            "orderAmountUsd": str(amount_usd),
            "orderId": order_id,
            "positionId": position["position_id"],
        })

    print(json.dumps({
        "status": "R5_CONDITIONAL_LIVE",
        "decision": decision.__dict__,
        "gapThreshold": gap_threshold,
        "confidenceThreshold": confidence_threshold,
        "results": results,
        "fridayFlatGate": window_detail,
    }, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
