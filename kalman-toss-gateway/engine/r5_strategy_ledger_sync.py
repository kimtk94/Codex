from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb


STRATEGY_VERSION = "R5.1_BASE_HGB"
PROVENANCE = "R5_1_CANONICAL_FORWARD_LOG"
LEDGER_TYPE = "LIVE_SHADOW"
COST_BPS = 10.0
UUID_NAMESPACE = uuid.UUID("2b3b6258-78df-4a6f-a1dd-b02cc9567dd5")


def _none_if_na(value):
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _float(value):
    value = _none_if_na(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value):
    value = _none_if_na(value)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso(value):
    value = _none_if_na(value)
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.isoformat()


def _required(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _r51_paths(data_root: Path) -> dict[str, Path]:
    us = data_root / "US_ETF"
    r51 = us / "model_lab_v1/results/r5_1_prospective_shadow"
    return {
        "us": us,
        "signal": _required(r51 / "r5_1_signal_log.parquet"),
        "trade": _required(r51 / "r5_1_trade_entry_log.parquet"),
        "outcome": _required(r51 / "r5_1_outcome_log.parquet"),
        "locked_panel": us / "directional_research/canonical_history_v1/panel_1h_gap_aware",
        "live_panel": us / "directional_research/r4_live_canonical_v1/panel_1h_overlay",
    }


def _read_prices(path: Path, symbol: str) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame(columns=["expected_seq", "timestamp", "close"])
    df = pd.read_parquet(path)
    required = {"expected_seq", "close"}
    missing = required.difference(df.columns)
    if missing:
        raise RuntimeError(f"{path}: missing price columns {sorted(missing)}")
    if "timestamp" not in df.columns:
        if {"market_open_utc", "session_bucket"}.issubset(df.columns):
            df = df.copy()
            df["timestamp"] = (
                pd.to_datetime(df["market_open_utc"], utc=True, errors="coerce")
                + pd.to_timedelta(pd.to_numeric(df["session_bucket"], errors="coerce"), unit="h")
            )
        else:
            raise RuntimeError(f"{path}: timestamp columns unavailable")
    z = df[["expected_seq", "timestamp", "close"]].copy()
    z["expected_seq"] = pd.to_numeric(z["expected_seq"], errors="coerce")
    z["timestamp"] = pd.to_datetime(z["timestamp"], utc=True, errors="coerce")
    z["close"] = pd.to_numeric(z["close"], errors="coerce")
    z = z.dropna(subset=["expected_seq", "timestamp", "close"])
    z["expected_seq"] = z["expected_seq"].astype("int64")
    z["symbol"] = symbol
    return z


class PriceLookup:
    def __init__(self, locked_panel: Path, live_panel: Path):
        self.locked_panel = locked_panel
        self.live_panel = live_panel
        self.cache: dict[str, dict[int, tuple[str, float]]] = {}

    def _load(self, symbol: str) -> dict[int, tuple[str, float]]:
        symbol = symbol.upper().replace(".", "-")
        if symbol in self.cache:
            return self.cache[symbol]
        locked = _read_prices(self.locked_panel / f"{symbol}_1h_gap_aware.parquet", symbol)
        live = _read_prices(self.live_panel / f"{symbol}_1h_live.parquet", symbol)
        all_rows = pd.concat([locked, live], ignore_index=True)
        if len(all_rows):
            all_rows = (
                all_rows.sort_values(["expected_seq", "timestamp"])
                .drop_duplicates("expected_seq", keep="last")
            )
        mapping = {
            int(r.expected_seq): (_iso(r.timestamp), float(r.close))
            for r in all_rows.itertuples(index=False)
        }
        self.cache[symbol] = mapping
        return mapping

    def at(self, symbol: str, expected_seq: int) -> tuple[str | None, float | None]:
        row = self._load(symbol).get(int(expected_seq))
        return row if row is not None else (None, None)


def _build_forward_record(
    trade: dict[str, Any],
    outcome: dict[str, Any] | None,
    price_lookup,
) -> dict[str, Any]:
    original_trade_id = str(trade["trade_id"])
    symbol = str(trade["selected_symbol"]).upper().replace(".", "-")
    expected_seq = int(trade["expected_seq"])
    expected_exit_seq = int(trade["expected_exit_seq"])
    entry_time, entry_price = price_lookup(symbol, expected_seq)
    if entry_time is None or entry_price is None:
        raise RuntimeError(
            f"entry price unavailable for {original_trade_id} {symbol} seq={expected_seq}"
        )

    weight = _float(trade.get("position_weight"))
    if weight is None or weight <= 0:
        raise RuntimeError(f"invalid position weight for {original_trade_id}: {weight}")

    exit_time = exit_price = None
    gross_weighted_return = net10_return = raw_return = None
    if outcome is not None:
        gross_weighted_return = _float(outcome.get("gross_return"))
        net10_return = _float(outcome.get("net10_return"))
        if gross_weighted_return is not None:
            raw_return = gross_weighted_return / weight
        exit_time, exit_price = price_lookup(symbol, expected_exit_seq)
        if exit_price is None and raw_return is not None:
            exit_price = entry_price * (1.0 + raw_return)
        if exit_time is None:
            raise RuntimeError(
                f"closed outcome has no exit timestamp for {original_trade_id} "
                f"{symbol} seq={expected_exit_seq}"
            )

    closed = outcome is not None and exit_time is not None and exit_price is not None
    metadata = {
        "score": _float(trade.get("score")),
        "status": "CLOSED" if closed else "OPEN",
        "symbol": symbol,
        "warning": None,
        "cost_bps": COST_BPS,
        "execution": False,
        "exit_rule": "EXPECTED_SEQ_PLUS_4",
        "exit_time": exit_time if closed else None,
        "entry_time": entry_time,
        "exit_price": exit_price if closed else None,
        "provenance": PROVENANCE,
        "raw_return": raw_return if closed else None,
        "return_pct": net10_return if closed else None,
        "entry_price": entry_price,
        "ledger_type": LEDGER_TYPE,
        "prospective": True,
        "shadow_only": True,
        "expected_seq": expected_seq,
        "net10_return": net10_return if closed else None,
        "position_weight": weight,
        "trade_execution": False,
        "expected_exit_seq": expected_exit_seq,
        "in_sample_warning": False,
        "original_trade_id": original_trade_id,
        "model_freeze_sha256": _none_if_na(trade.get("model_freeze_sha256")),
        "gross_weighted_return": gross_weighted_return if closed else None,
        "model_was_not_prospective": False,
    }
    return {
        "original_trade_id": original_trade_id,
        "symbol": symbol,
        "entry_time": entry_time,
        "entry_price": entry_price,
        "exit_time": exit_time if closed else None,
        "exit_price": exit_price if closed else None,
        "return_pct": net10_return if closed else None,
        "exit_reason": "EXPECTED_SEQ_PLUS_4" if closed else None,
        "metadata": metadata,
    }


def _records_from_files(paths: dict[str, Path]) -> list[dict[str, Any]]:
    trades = pd.read_parquet(paths["trade"])
    outcomes = pd.read_parquet(paths["outcome"])

    required_trade = {
        "trade_id", "selected_symbol", "timestamp", "expected_seq",
        "expected_exit_seq", "position_weight"
    }
    missing = required_trade.difference(trades.columns)
    if missing:
        raise RuntimeError(f"R5.1 trade log missing columns: {sorted(missing)}")
    required_outcome = {"trade_id", "gross_return", "net10_return"}
    missing = required_outcome.difference(outcomes.columns)
    if missing:
        raise RuntimeError(f"R5.1 outcome log missing columns: {sorted(missing)}")

    if len(trades):
        trades = trades.sort_values(["expected_seq", "timestamp"]).drop_duplicates(
            "trade_id", keep="last"
        )
    if len(outcomes):
        outcomes = outcomes.drop_duplicates("trade_id", keep="last")
    outcome_map = {
        str(r["trade_id"]): r.to_dict()
        for _, r in outcomes.iterrows()
    }

    prices = PriceLookup(paths["locked_panel"], paths["live_panel"])
    records = []
    for _, row in trades.iterrows():
        trade = row.to_dict()
        trade_id = str(trade["trade_id"])
        records.append(
            _build_forward_record(trade, outcome_map.get(trade_id), prices.at)
        )
    return records


def _existing_ids(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT trade_id::text, metadata->>'original_trade_id'
            FROM strategy_ledger
            WHERE market='US'
              AND strategy_version=%s
              AND ledger_type=%s
              AND metadata->>'provenance'=%s
            """,
            (STRATEGY_VERSION, LEDGER_TYPE, PROVENANCE),
        )
        return {
            original: trade_id
            for trade_id, original in cur.fetchall()
            if original
        }


def _latest_us_run_id(conn) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id
            FROM pipeline_run
            WHERE market='US'
              AND status='SUCCESS'
              AND pipeline_version LIKE 'unified-v1/us-daily-ops%%'
            ORDER BY completed_at DESC NULLS LAST, started_at DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("latest successful US pipeline_run not found")
    return str(row[0])


def _uuid_for(original_trade_id: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, original_trade_id))


def sync_records(conn, records: list[dict[str, Any]]) -> dict[str, Any]:
    existing = _existing_ids(conn)
    run_id = _latest_us_run_id(conn)
    upserts = 0
    with conn.cursor() as cur:
        for record in records:
            original = record["original_trade_id"]
            trade_id = existing.get(original) or _uuid_for(original)
            metadata = dict(record["metadata"])
            metadata["trade_id"] = trade_id
            metadata["ledger_sync_run_id"] = run_id
            cur.execute(
                """
                INSERT INTO strategy_ledger (
                  trade_id,market,symbol,strategy_version,model_version,
                  entry_time,entry_price,exit_time,exit_price,return_pct,
                  exit_reason,ledger_type,run_id,metadata
                ) VALUES (
                  %s,'US',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                ON CONFLICT (trade_id) DO UPDATE SET
                  symbol=EXCLUDED.symbol,
                  strategy_version=EXCLUDED.strategy_version,
                  model_version=EXCLUDED.model_version,
                  entry_time=EXCLUDED.entry_time,
                  entry_price=EXCLUDED.entry_price,
                  exit_time=EXCLUDED.exit_time,
                  exit_price=EXCLUDED.exit_price,
                  return_pct=EXCLUDED.return_pct,
                  exit_reason=EXCLUDED.exit_reason,
                  ledger_type=EXCLUDED.ledger_type,
                  run_id=EXCLUDED.run_id,
                  metadata=EXCLUDED.metadata
                """,
                (
                    trade_id,
                    record["symbol"],
                    STRATEGY_VERSION,
                    STRATEGY_VERSION,
                    record["entry_time"],
                    record["entry_price"],
                    record["exit_time"],
                    record["exit_price"],
                    record["return_pct"],
                    record["exit_reason"],
                    LEDGER_TYPE,
                    run_id,
                    Jsonb(metadata),
                ),
            )
            upserts += 1

        cur.execute(
            """
            SELECT COUNT(*)::int,
                   COUNT(*) FILTER (WHERE exit_time IS NULL)::int,
                   MIN(entry_time),
                   MAX(entry_time),
                   MAX(exit_time)
            FROM strategy_ledger
            WHERE market='US'
              AND strategy_version=%s
              AND ledger_type=%s
              AND metadata->>'provenance'=%s
            """,
            (STRATEGY_VERSION, LEDGER_TYPE, PROVENANCE),
        )
        count, open_count, first_entry, last_entry, last_exit = cur.fetchone()

    return {
        "run_id": run_id,
        "upserts": upserts,
        "rows": count,
        "open_rows": open_count,
        "first_entry": _iso(first_entry),
        "last_entry": _iso(last_entry),
        "last_exit": _iso(last_exit),
    }


def main() -> int:
    load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)
    db_url = os.environ.get("DATABASE_URL_WRITER")
    if not db_url:
        raise RuntimeError("DATABASE_URL_WRITER is missing")

    data_root = Path(os.environ.get("KALMAN_DATA_ROOT") or "/opt/kalman/data")
    paths = _r51_paths(data_root)
    records = _records_from_files(paths)

    with psycopg.connect(db_url) as conn:
        report = sync_records(conn, records)
        conn.commit()

    print(json.dumps({
        "status": "SYNCED",
        "source": PROVENANCE,
        "strategyVersion": STRATEGY_VERSION,
        "localTrades": len(records),
        **report,
        "trade_execution": False,
        "read_only_broker_calls": True,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
