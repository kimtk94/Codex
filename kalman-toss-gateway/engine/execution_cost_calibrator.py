from __future__ import annotations

import json
import math
import os
import sqlite3
from decimal import Decimal
from pathlib import Path

import numpy as np



MIN_TOTAL_SAMPLES = 30
MIN_SIDE_SAMPLES = 10
DEFAULT_REFERENCE_ROUND_TRIP_BPS = 20.0


def _dec(v):
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _json_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _execution_quality(side: str | None, average_fill, telemetry: dict) -> dict:
    broker = telemetry.get("broker_order") if isinstance(telemetry.get("broker_order"), dict) else {}
    quote = telemetry.get("pretrade_quote") if isinstance(telemetry.get("pretrade_quote"), dict) else {}
    fill_price = _dec(average_fill) or _dec(broker.get("average_filled_price"))
    fill_quantity = _dec(broker.get("filled_quantity"))
    side = str(side or "").upper()
    reference_price = _dec(quote.get("best_ask" if side == "BUY" else "best_bid" if side == "SELL" else ""))
    slippage_bps = None
    if fill_price is not None and reference_price is not None and reference_price > 0:
        if side == "BUY":
            slippage_bps = (fill_price - reference_price) / reference_price * Decimal("10000")
        elif side == "SELL":
            slippage_bps = (reference_price - fill_price) / reference_price * Decimal("10000")
    exact_notional = None
    if fill_price is not None and fill_quantity is not None and fill_quantity > 0:
        exact_notional = fill_price * fill_quantity
    filled_amount = _dec(broker.get("filled_amount"))
    commission = _dec(broker.get("commission")) or Decimal("0")
    tax = _dec(broker.get("tax")) or Decimal("0")
    basis = exact_notional if exact_notional is not None and exact_notional > 0 else filled_amount
    cost_bps = None
    if basis is not None and basis > 0:
        cost_bps = (commission + tax) / basis * Decimal("10000")
    def n(v):
        d=_dec(v)
        return float(d) if d is not None else None
    return {
        "currency": broker.get("currency") or quote.get("currency"),
        "best_bid": n(quote.get("best_bid")),
        "best_ask": n(quote.get("best_ask")),
        "spread_bps": n(quote.get("spread_bps")),
        "reference_price": float(reference_price) if reference_price is not None else None,
        "slippage_bps": float(slippage_bps) if slippage_bps is not None else None,
        "filled_quantity": float(fill_quantity) if fill_quantity is not None else None,
        "average_filled_price": float(fill_price) if fill_price is not None else None,
        "commission": float(commission),
        "tax": float(tax),
        "cost_bps": float(cost_bps) if cost_bps is not None else None,
        "broker_fill_latency_ms": broker.get("broker_fill_latency_ms"),
    }


def _rows(conn: sqlite3.Connection, sql: str) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql).fetchall()]


def _finite(values) -> list[float]:
    out = []
    for value in values:
        try:
            x = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(x):
            out.append(x)
    return out


def _stats(values) -> dict:
    xs = _finite(values)
    if not xs:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "min": None,
            "max": None,
        }
    a = np.asarray(xs, dtype=float)
    return {
        "n": int(len(a)),
        "mean": float(a.mean()),
        "median": float(np.median(a)),
        "p75": float(np.quantile(a, 0.75)),
        "p90": float(np.quantile(a, 0.90)),
        "p95": float(np.quantile(a, 0.95)),
        "min": float(a.min()),
        "max": float(a.max()),
    }


def calibrate(state_db: Path) -> dict:
    if not state_db.is_file():
        return {
            "schema_version": "kalman-execution-cost-calibration-v1",
            "status": "SKIP",
            "reason": "STATE_DB_MISSING",
            "state_db": str(state_db),
        }

    with sqlite3.connect(state_db) as conn:
        positions = _rows(conn, "SELECT * FROM managed_position ORDER BY created_at")
        orders = _rows(conn, "SELECT * FROM order_guard ORDER BY created_at")

    avg_by_client: dict[str, object] = {}
    leg_by_client: dict[str, str] = {}
    for p in positions:
        cid = p.get("entry_client_order_id")
        if cid:
            avg_by_client[str(cid)] = p.get("entry_avg_fill_price")
            leg_by_client[str(cid)] = "ENTRY"
        cid = p.get("exit_client_order_id")
        if cid:
            avg_by_client[str(cid)] = p.get("exit_avg_fill_price")
            leg_by_client[str(cid)] = "EXIT"

    observations = []
    for order in orders:
        cid = str(order.get("client_order_id") or "")
        if not cid:
            continue
        telemetry = _json_dict(order.get("telemetry_json"))
        quality = _execution_quality(order.get("side"), avg_by_client.get(cid), telemetry)
        if quality.get("slippage_bps") is None and quality.get("cost_bps") is None:
            continue
        observations.append({
            "client_order_id": cid,
            "symbol": order.get("symbol"),
            "side": str(order.get("side") or "").upper(),
            "leg": leg_by_client.get(cid),
            "status": order.get("status"),
            "created_at": order.get("created_at"),
            **quality,
        })

    buys = [x for x in observations if x.get("side") == "BUY" and x.get("slippage_bps") is not None]
    sells = [x for x in observations if x.get("side") == "SELL" and x.get("slippage_bps") is not None]
    all_slippage = [x.get("slippage_bps") for x in observations]
    all_direct_cost = [x.get("cost_bps") for x in observations]

    buy_slip = _stats([x.get("slippage_bps") for x in buys])
    sell_slip = _stats([x.get("slippage_bps") for x in sells])
    slip_all = _stats(all_slippage)
    cost_all = _stats(all_direct_cost)
    buy_cost = _stats([x.get("cost_bps") for x in observations if x.get("side") == "BUY"])
    sell_cost = _stats([x.get("cost_bps") for x in observations if x.get("side") == "SELL"])
    spread_all = _stats([x.get("spread_bps") for x in observations])
    fill_latency = _stats([x.get("broker_fill_latency_ms") for x in observations])

    sufficient = (
        slip_all["n"] >= MIN_TOTAL_SAMPLES
        and buy_slip["n"] >= MIN_SIDE_SAMPLES
        and sell_slip["n"] >= MIN_SIDE_SAMPLES
    )

    if sufficient:
        entry_slip = max(0.0, float(buy_slip["p90"] or 0.0))
        exit_slip = max(0.0, float(sell_slip["p90"] or 0.0))
        entry_cost = max(0.0, float(buy_cost["p90"] or 0.0))
        exit_cost = max(0.0, float(sell_cost["p90"] or 0.0))
        empirical_round_trip = entry_slip + exit_slip + entry_cost + exit_cost
        recommended = max(DEFAULT_REFERENCE_ROUND_TRIP_BPS, empirical_round_trip)
        gate = "READY_EMPIRICAL_COST"
    else:
        empirical_round_trip = None
        recommended = DEFAULT_REFERENCE_ROUND_TRIP_BPS
        gate = "BLOCK_INSUFFICIENT_EXECUTION_SAMPLE"

    recent = observations[-20:]
    return {
        "schema_version": "kalman-execution-cost-calibration-v1",
        "status": "COMPLETE",
        "state_db": str(state_db),
        "observations": int(len(observations)),
        "sample_gate": {
            "required_total": MIN_TOTAL_SAMPLES,
            "required_each_side": MIN_SIDE_SAMPLES,
            "sufficient": bool(sufficient),
        },
        "slippage_bps": {
            "all": slip_all,
            "buy": buy_slip,
            "sell": sell_slip,
        },
        "direct_cost_bps": {
            "all": cost_all,
            "buy": buy_cost,
            "sell": sell_cost,
        },
        "spread_bps": spread_all,
        "broker_fill_latency_ms": fill_latency,
        "empirical_p90_round_trip_bps": empirical_round_trip,
        "reference_round_trip_bps": DEFAULT_REFERENCE_ROUND_TRIP_BPS,
        "recommended_backtest_round_trip_bps": float(recommended),
        "promotion_gate": gate,
        "recent_observations": recent,
    }


def main() -> int:
    from app.config import Settings

    settings = Settings(_env_file=os.environ.get("KALMAN_ENV_FILE", ".env"))
    state_db = Path(os.environ.get("TRADING_STATE_DB", str(settings.state_db_path)))
    output = Path(
        os.environ.get(
            "EXECUTION_COST_CALIBRATION_PATH",
            str(state_db.with_name("execution-cost-calibration.json")),
        )
    )
    result = calibrate(state_db)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(temp, output)
    print(json.dumps({
        "status": result.get("status"),
        "observations": result.get("observations", 0),
        "recommended_backtest_round_trip_bps": result.get("recommended_backtest_round_trip_bps"),
        "promotion_gate": result.get("promotion_gate"),
        "output": str(output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
