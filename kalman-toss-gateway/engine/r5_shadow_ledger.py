from __future__ import annotations

import argparse
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv

MODEL_VERSION = "R5.1_BASE_HGB"
STRATEGY_VERSION = "R5.1_BASE_HGB"
LEDGER_TYPE = "LIVE_SHADOW"
SOURCE = "unified-server-v1"
UUID_NAMESPACE = uuid.UUID("9f7e4f21-90fe-4a87-b78c-94a643771d3b")


@dataclass(frozen=True)
class Snapshot:
    run_id: str
    as_of: datetime
    symbol: str
    entry_signal: bool
    selected_price: Decimal
    prices: dict[str, Decimal]


@dataclass(frozen=True)
class Trade:
    trade_id: uuid.UUID
    symbol: str
    entry_run_id: str
    entry_time: datetime
    entry_price: Decimal
    exit_run_id: str | None
    exit_time: datetime | None
    exit_price: Decimal | None
    return_pct: float | None
    exit_reason: str | None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build idempotent R5.1 US SHADOW lifecycle trades from Neon snapshots"
    )
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def trade_id_for(entry_run_id: str, symbol: str, entry_time: datetime) -> uuid.UUID:
    return uuid.uuid5(
        UUID_NAMESPACE,
        f"{STRATEGY_VERSION}|{entry_run_id}|{symbol}|{entry_time.isoformat()}",
    )


def build_trades(snapshots: list[Snapshot]) -> list[Trade]:
    trades: list[Trade] = []
    open_trade: dict[str, Any] | None = None

    for snap in sorted(snapshots, key=lambda x: x.as_of):
        if open_trade is not None:
            keep_open = snap.entry_signal and snap.symbol == open_trade["symbol"]
            if not keep_open:
                old_symbol = str(open_trade["symbol"])
                exit_price = snap.prices.get(old_symbol)
                if exit_price is None:
                    raise RuntimeError(
                        f"missing exit reference_price for {old_symbol} in run {snap.run_id}"
                    )
                entry_price = Decimal(open_trade["entry_price"])
                return_pct = float((exit_price / entry_price) - Decimal("1"))
                reason = (
                    "ENTRY_GATE_OFF"
                    if snap.symbol == old_symbol and not snap.entry_signal
                    else "SELECTOR_CHANGED"
                )
                trades.append(
                    Trade(
                        trade_id=open_trade["trade_id"],
                        symbol=old_symbol,
                        entry_run_id=open_trade["entry_run_id"],
                        entry_time=open_trade["entry_time"],
                        entry_price=entry_price,
                        exit_run_id=snap.run_id,
                        exit_time=snap.as_of,
                        exit_price=exit_price,
                        return_pct=return_pct,
                        exit_reason=reason,
                    )
                )
                open_trade = None

        if open_trade is None and snap.entry_signal:
            open_trade = {
                "trade_id": trade_id_for(snap.run_id, snap.symbol, snap.as_of),
                "symbol": snap.symbol,
                "entry_run_id": snap.run_id,
                "entry_time": snap.as_of,
                "entry_price": snap.selected_price,
            }

    if open_trade is not None:
        trades.append(
            Trade(
                trade_id=open_trade["trade_id"],
                symbol=open_trade["symbol"],
                entry_run_id=open_trade["entry_run_id"],
                entry_time=open_trade["entry_time"],
                entry_price=Decimal(open_trade["entry_price"]),
                exit_run_id=None,
                exit_time=None,
                exit_price=None,
                return_pct=None,
                exit_reason=None,
            )
        )

    return trades


def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() == "true"


def load_snapshots(cur: Any) -> list[Snapshot]:
    cur.execute(
        """
        WITH dedup AS (
          SELECT DISTINCT ON (ss.as_of)
                 ss.run_id,
                 ss.as_of,
                 ss.symbol,
                 COALESCE((ss.payload->>'shadow_entry_this_signal')::boolean,false) AS entry_signal,
                 ss.entry_allowed,
                 ss.signal,
                 ss.position_state,
                 ss.payload,
                 pr.completed_at
          FROM strategy_signal ss
          JOIN pipeline_run pr ON pr.run_id=ss.run_id
          WHERE ss.market='US'
            AND pr.market='US'
            AND pr.status='SUCCESS'
            AND pr.model_version=%s
            AND ss.strategy_version=%s
            AND ss.signal='SHADOW'
            AND COALESCE(ss.payload->>'source','')=%s
          ORDER BY ss.as_of, pr.completed_at DESC
        )
        SELECT d.run_id,d.as_of,d.symbol,d.entry_signal,
               d.entry_allowed,d.signal,d.position_state,d.payload,
               mo.symbol,mo.payload
        FROM dedup d
        JOIN model_output mo
          ON mo.run_id=d.run_id
         AND mo.market='US'
         AND mo.model_version=%s
        ORDER BY d.as_of,mo.symbol
        """,
        (MODEL_VERSION, STRATEGY_VERSION, SOURCE, MODEL_VERSION),
    )

    grouped: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        (
            run_id,
            as_of,
            selected_symbol,
            entry_signal,
            entry_allowed,
            signal,
            position_state,
            signal_payload,
            model_symbol,
            model_payload,
        ) = row

        if entry_allowed not in (False, None):
            raise RuntimeError(f"{run_id}: entry_allowed must remain false")
        if str(signal).upper() != "SHADOW":
            raise RuntimeError(f"{run_id}: signal must remain SHADOW")
        if _bool((signal_payload or {}).get("live_execution")):
            raise RuntimeError(f"{run_id}: live_execution must remain false")

        ref = (model_payload or {}).get("reference_price")
        if ref is None:
            continue
        rec = grouped.setdefault(
            run_id,
            {
                "run_id": run_id,
                "as_of": as_of,
                "symbol": str(selected_symbol),
                "entry_signal": bool(entry_signal),
                "prices": {},
            },
        )
        rec["prices"][str(model_symbol)] = Decimal(str(ref))

    snapshots: list[Snapshot] = []
    for rec in sorted(grouped.values(), key=lambda x: x["as_of"]):
        selected_price = rec["prices"].get(rec["symbol"])
        if selected_price is None:
            raise RuntimeError(
                f"{rec['run_id']}: selected symbol {rec['symbol']} has no reference_price"
            )
        snapshots.append(
            Snapshot(
                run_id=rec["run_id"],
                as_of=rec["as_of"],
                symbol=rec["symbol"],
                entry_signal=rec["entry_signal"],
                selected_price=selected_price,
                prices=dict(rec["prices"]),
            )
        )
    return snapshots


def upsert_trades(cur: Any, trades: list[Trade]) -> None:
    for trade in trades:
        metadata = {
            "source": SOURCE,
            "lifecycle": "R5.1_SHADOW_SELECTOR",
            "entry_run_id": trade.entry_run_id,
            "exit_run_id": trade.exit_run_id,
            "execution": False,
            "trade_execution": False,
            "shadow_only": True,
            "event_semantics": {
                "entry": "shadow_entry_this_signal=true",
                "hold": "same selected symbol and shadow_entry_this_signal=true",
                "exit": "entry gate off or selector changed",
            },
        }
        cur.execute(
            """
            INSERT INTO strategy_ledger (
                trade_id,market,symbol,strategy_version,model_version,
                entry_time,entry_price,exit_time,exit_price,return_pct,
                exit_reason,ledger_type,run_id,metadata
            ) VALUES (
                %s,'US',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb
            )
            ON CONFLICT (trade_id) DO UPDATE SET
                exit_time=EXCLUDED.exit_time,
                exit_price=EXCLUDED.exit_price,
                return_pct=EXCLUDED.return_pct,
                exit_reason=EXCLUDED.exit_reason,
                metadata=EXCLUDED.metadata
            """,
            (
                trade.trade_id,
                trade.symbol,
                STRATEGY_VERSION,
                MODEL_VERSION,
                trade.entry_time,
                trade.entry_price,
                trade.exit_time,
                trade.exit_price,
                trade.return_pct,
                trade.exit_reason,
                LEDGER_TYPE,
                trade.entry_run_id,
                json.dumps(metadata, separators=(",", ":")),
            ),
        )


def build_dashboard_ledger_payload(trades: list[Trade]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    closed_multiple = Decimal("1")
    closed_returns: list[float] = []

    for trade in sorted(trades, key=lambda x: x.entry_time):
        row = {
            "trade_id": str(trade.trade_id),
            "symbol": trade.symbol,
            "entry_time": trade.entry_time.isoformat(),
            "entry_price": float(trade.entry_price),
            "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
            "exit_price": float(trade.exit_price) if trade.exit_price is not None else None,
            "return_pct": trade.return_pct,
            "exit_reason": trade.exit_reason,
            "status": "CLOSED" if trade.exit_time else "OPEN",
            "ledger_type": LEDGER_TYPE,
            "shadow_only": True,
            "execution": False,
        }
        trade_rows.append(row)
        events.append(
            {
                "trade_id": str(trade.trade_id),
                "symbol": trade.symbol,
                "time": trade.entry_time.isoformat(),
                "price": float(trade.entry_price),
                "signal": "BUY",
                "event_type": "R5_1_SHADOW_ENTER",
                "source": "R5.1_SHADOW_LEDGER",
            }
        )
        if trade.exit_time is not None and trade.exit_price is not None:
            events.append(
                {
                    "trade_id": str(trade.trade_id),
                    "symbol": trade.symbol,
                    "time": trade.exit_time.isoformat(),
                    "price": float(trade.exit_price),
                    "signal": "SELL",
                    "event_type": "R5_1_SHADOW_EXIT",
                    "source": "R5.1_SHADOW_LEDGER",
                    "exit_reason": trade.exit_reason,
                }
            )
            if trade.return_pct is not None:
                closed_returns.append(float(trade.return_pct))
                closed_multiple *= Decimal(str(1.0 + float(trade.return_pct)))

    closed_count = len(closed_returns)
    return {
        "schema_version": "r5-shadow-lifecycle-v0.1",
        "model_version": MODEL_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "ledger_type": LEDGER_TYPE,
        "shadow_only": True,
        "execution": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "trade_count": len(trade_rows),
            "closed_count": closed_count,
            "open_count": sum(x.exit_time is None for x in trades),
            "closed_compound_return_pct": float(closed_multiple - Decimal("1")) * 100.0,
            "closed_mean_return_pct": (
                sum(closed_returns) / closed_count * 100.0 if closed_count else None
            ),
            "open_symbols": [x.symbol for x in trades if x.exit_time is None],
        },
        "trades": trade_rows,
        "events": sorted(events, key=lambda x: (x["time"], x["symbol"], x["signal"])),
    }


def enrich_latest_dashboard(cur: Any, trades: list[Trade]) -> str:
    payload = build_dashboard_ledger_payload(trades)
    cur.execute(
        """
        SELECT snapshot_id,run_id
        FROM dashboard_snapshot
        WHERE market='US'
          AND status='READY'
          AND model_version=%s
        ORDER BY generated_at DESC
        LIMIT 1
        FOR UPDATE
        """,
        (MODEL_VERSION,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("latest R5.1 US dashboard snapshot not found")
    snapshot_id, run_id = row

    cur.execute(
        """
        UPDATE dashboard_snapshot
        SET payload = jsonb_set(
            payload,
            '{source_payload,r5_shadow_ledger}',
            %s::jsonb,
            true
        )
        WHERE snapshot_id=%s
        """,
        (json.dumps(payload, separators=(",", ":")), snapshot_id),
    )
    if cur.rowcount != 1:
        raise RuntimeError(f"dashboard snapshot update failed: {snapshot_id}")

    cur.execute(
        """
        SELECT payload #> '{source_payload,r5_shadow_ledger}'
        FROM dashboard_snapshot
        WHERE snapshot_id=%s
        """,
        (snapshot_id,),
    )
    stored = cur.fetchone()[0] or {}
    if stored.get("shadow_only") is not True or stored.get("execution") is not False:
        raise RuntimeError("dashboard R5.1 ledger safety metadata mismatch")
    if len(stored.get("trades") or []) != len(trades):
        raise RuntimeError("dashboard R5.1 ledger trade count mismatch")
    return str(run_id)


def validate_written(cur: Any, expected: list[Trade]) -> None:
    ids = [x.trade_id for x in expected]
    cur.execute(
        """
        SELECT trade_id,symbol,entry_time,entry_price,exit_time,exit_price,
               return_pct,exit_reason,ledger_type,metadata
        FROM strategy_ledger
        WHERE trade_id = ANY(%s)
        ORDER BY entry_time
        """,
        (ids,),
    )
    rows = cur.fetchall()
    if len(rows) != len(expected):
        raise RuntimeError(
            f"ledger row count mismatch: expected={len(expected)} actual={len(rows)}"
        )
    for row in rows:
        if row[8] != LEDGER_TYPE:
            raise RuntimeError(f"unexpected ledger_type: {row[8]}")
        metadata = row[9] or {}
        if metadata.get("execution") is not False:
            raise RuntimeError("R5.1 shadow ledger execution flag changed")
        if metadata.get("shadow_only") is not True:
            raise RuntimeError("R5.1 shadow ledger must remain shadow_only")


def main() -> int:
    args = parse_args()
    env_file = os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env")
    load_dotenv(env_file, override=True)
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL/NEON_DATABASE_URL is required")

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required") from exc

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('r5_shadow_ledger_v1'))")
            snapshots = load_snapshots(cur)
            trades = build_trades(snapshots)

            summary = {
                "snapshots": len(snapshots),
                "trades": len(trades),
                "closed": sum(t.exit_time is not None for t in trades),
                "open": sum(t.exit_time is None for t in trades),
                "symbols": [t.symbol for t in trades],
            }
            print(json.dumps(summary, ensure_ascii=False))

            if args.dry_run:
                conn.rollback()
                for t in trades:
                    print(
                        json.dumps(
                            {
                                "symbol": t.symbol,
                                "entry_time": t.entry_time.isoformat(),
                                "entry_price": str(t.entry_price),
                                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                                "exit_price": str(t.exit_price) if t.exit_price is not None else None,
                                "return_pct": t.return_pct,
                                "exit_reason": t.exit_reason,
                            },
                            ensure_ascii=False,
                        )
                    )
                return 0

            upsert_trades(cur, trades)
            validate_written(cur, trades)
            dashboard_run_id = enrich_latest_dashboard(cur, trades)
        conn.commit()

    print(f"R5_SHADOW_LEDGER_SYNC_COMPLETE dashboard_run_id={dashboard_run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
