"""Read-only evaluation of all broker holdings against current R5.1 Top2 support.

This module never submits broker orders. It produces an auditable state snapshot
used by the scheduler and dashboard before any new BUY decision.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.config import Settings
from app.managed_positions import ManagedPositionStore
from app.market_guard import unwrap
from app.toss_client import TossClient
from engine.auto_trade import _holding_items, load_signal
from engine.r5_conditional_live import _rank_context_from_same_run
from engine.r5_conditional_policy import decide


STRATEGY = "R5.1_BASE_HGB"
POLICY = "R5_LIVE_TOP1"


def _dec(value: Any) -> Decimal | None:
    try:
        if value is None or value == "":
            return None
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _nested_decimal(row: dict[str, Any], root: str, key: str) -> Decimal | None:
    payload = row.get(root)
    if not isinstance(payload, dict):
        return None
    return _dec(payload.get(key))


def _classification(
    *,
    managed: dict[str, Any] | None,
    support_rank: int | None,
    pnl_rate: Decimal | None,
    stop_loss: Decimal,
    take_profit: Decimal,
) -> tuple[str, list[str]]:
    flags: list[str] = []
    if support_rank is not None:
        flags.append(f"MODEL_TOP{support_rank}")
    else:
        flags.append("OUTSIDE_CURRENT_TOP2")

    if pnl_rate is not None:
        if pnl_rate <= stop_loss:
            flags.append("STOP_LOSS_ZONE")
        elif pnl_rate >= take_profit:
            flags.append("TAKE_PROFIT_ZONE")
        elif pnl_rate < 0:
            flags.append("UNREALIZED_LOSS")
        else:
            flags.append("UNREALIZED_NONNEGATIVE")

    if managed:
        state = str(managed.get("state") or "")
        pending = managed.get("exit_pending_reason")
        if pending:
            flags.append(f"EXIT_PENDING:{pending}")
            return "MANAGED_EXIT_PENDING", flags
        if state not in {"OPEN", "ENTRY_SUBMITTED", "ADD_ON_SUBMITTED", "ADD_ON_RESERVED"}:
            flags.append(f"MANAGED_STATE:{state}")
        if support_rank is not None:
            return "HOLD_MODEL_SUPPORTED", flags
        return "HOLD_MANAGED_EXIT_RULES", flags

    flags.append("UNMANAGED_BROKER_HOLDING")
    if support_rank is not None:
        return "UNMANAGED_MODEL_SUPPORTED_REVIEW", flags
    if pnl_rate is not None and pnl_rate < 0:
        return "UNMANAGED_EXIT_REVIEW", flags
    return "UNMANAGED_HOLD_NO_ADD_REVIEW", flags


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


async def evaluate_holdings() -> dict[str, Any]:
    load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)
    settings = Settings()
    client = TossClient(settings)
    store = ManagedPositionStore(settings.state_db_path)

    holdings_root = unwrap(await client.holdings()) or {}
    holdings = _holding_items(holdings_root)
    active = store.active()
    managed_by_symbol = {
        str(row.get("symbol") or "").upper(): row
        for row in active
        if str(row.get("symbol") or "").strip()
    }

    signal = load_signal("LIVE", STRATEGY, POLICY)
    rank1_symbol = None
    rank1_score = None
    rank2_symbol = None
    rank2_score = None
    decision = None
    signal_meta: dict[str, Any] = {}

    if signal:
        rank1_symbol = str(signal.get("symbol") or "").upper() or None
        rank1_score, rank2_symbol, rank2_score = _rank_context_from_same_run(signal)
        if rank1_symbol and rank1_score is not None:
            gap_threshold = float(os.environ.get("AUTO_TRADE_CONDITIONAL_GAP_THRESHOLD", "0"))
            confidence_threshold = float(
                os.environ.get("AUTO_TRADE_CONDITIONAL_CONFIDENCE_THRESHOLD", "0")
            )
            decision = decide(
                rank1_symbol=rank1_symbol,
                rank1_score=rank1_score,
                rank2_symbol=rank2_symbol,
                rank2_score=rank2_score,
                gap_threshold=gap_threshold,
                confidence_threshold=confidence_threshold,
                total_krw=int(os.environ.get("AUTO_TRADE_CONDITIONAL_TOTAL_KRW", "20000")),
            )
        signal_meta = {
            "run_id": signal.get("run_id"),
            "as_of": signal.get("as_of"),
            "strategy_version": signal.get("strategy_version"),
        }

    support: dict[str, tuple[int, float | None]] = {}
    if rank1_symbol:
        support[rank1_symbol] = (1, rank1_score)
    if rank2_symbol:
        support[str(rank2_symbol).upper()] = (2, rank2_score)

    stop_loss = Decimal(os.environ.get("AUTO_TRADE_STOP_LOSS_PCT", "-0.03"))
    take_profit = Decimal(os.environ.get("AUTO_TRADE_TAKE_PROFIT_PCT", "0.20"))

    rows: list[dict[str, Any]] = []
    for holding in holdings:
        symbol = str(holding.get("symbol") or "").upper()
        qty = _dec(holding.get("quantity")) or Decimal("0")
        if not symbol or qty == 0:
            continue

        pnl_rate = _nested_decimal(holding, "profitLoss", "rate")
        daily_rate = _nested_decimal(holding, "dailyProfitLoss", "rate")
        purchase_amount = _nested_decimal(holding, "marketValue", "purchaseAmount")
        market_amount = _nested_decimal(holding, "marketValue", "amount")
        support_rank, model_score = support.get(symbol, (None, None))
        managed = managed_by_symbol.get(symbol)
        action, flags = _classification(
            managed=managed,
            support_rank=support_rank,
            pnl_rate=pnl_rate,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        rows.append(
            {
                "symbol": symbol,
                "name": holding.get("name"),
                "quantity": str(qty),
                "last_price": holding.get("lastPrice"),
                "average_purchase_price": holding.get("averagePurchasePrice"),
                "purchase_amount_usd": str(purchase_amount) if purchase_amount is not None else None,
                "market_value_usd": str(market_amount) if market_amount is not None else None,
                "pnl_rate": str(pnl_rate) if pnl_rate is not None else None,
                "daily_pnl_rate": str(daily_rate) if daily_rate is not None else None,
                "managed": managed is not None,
                "managed_state": managed.get("state") if managed else None,
                "managed_entry_count": int(managed.get("entry_count") or 0) if managed else 0,
                "managed_exit_pending_reason": managed.get("exit_pending_reason") if managed else None,
                "model_support_rank": support_rank,
                "model_score": model_score,
                "evaluation": action,
                "flags": flags,
            }
        )

    summary = {
        "holding_count": len(rows),
        "managed_count": sum(1 for row in rows if row["managed"]),
        "unmanaged_count": sum(1 for row in rows if not row["managed"]),
        "top2_supported_count": sum(1 for row in rows if row["model_support_rank"] is not None),
        "exit_review_count": sum(
            1 for row in rows if row["evaluation"] in {"UNMANAGED_EXIT_REVIEW", "MANAGED_EXIT_PENDING"}
        ),
    }

    return {
        "schema_version": "kalman-holdings-evaluation-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_NO_BROKER_ORDERS",
        "strategy": STRATEGY,
        "current_model": {
            **signal_meta,
            "rank1_symbol": rank1_symbol,
            "rank1_score": rank1_score,
            "rank2_symbol": rank2_symbol,
            "rank2_score": rank2_score,
            "conditional_regime": decision.regime if decision else None,
        },
        "risk_policy": {
            "stop_loss_pct": str(stop_loss),
            "take_profit_pct": str(take_profit),
            "managed_exit_policy_authority": "engine.position_manager",
            "unmanaged_auto_sell": False,
        },
        "summary": summary,
        "holdings": rows,
    }


async def main_async() -> int:
    report = await evaluate_holdings()
    path = Path(
        os.environ.get(
            "HOLDINGS_EVALUATION_PATH",
            "/opt/kalman/state/holdings-evaluation-latest.json",
        )
    )
    _atomic_write_json(path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
