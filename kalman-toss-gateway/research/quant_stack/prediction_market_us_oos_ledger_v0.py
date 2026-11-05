from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.quant_stack.prediction_market_leadlag_v0 import (
    align_asset,
    build_event_hours,
    load_asset_history,
)
from research.quant_stack.prediction_market_oos_v0 import filter_strict_oos, load_spec


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def event_id(hypothesis_id: str, event_hour: pd.Timestamp, channel: str) -> str:
    key = f"{hypothesis_id}|{pd.Timestamp(event_hour).isoformat()}|{channel}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def init_ledger(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            hypothesis_id TEXT NOT NULL,
            event_hour TEXT NOT NULL,
            event_at TEXT,
            dominant_channel TEXT NOT NULL,
            dominant_theme TEXT,
            event_score REAL,
            family_count INTEGER,
            market_count INTEGER,
            mean_abs_delta_1h REAL,
            entry_ts TEXT,
            entry_price REAL,
            entry_lag_minutes REAL,
            horizon_bars INTEGER NOT NULL,
            forward_return REAL,
            signed_return REAL,
            outcome_state TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            source TEXT NOT NULL
        )
        """
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_hour ON events(event_hour)"
    )
    con.commit()
    return con


def build_ledger_rows(
    prediction: pd.DataFrame,
    asset: pd.DataFrame,
    spec: dict[str, Any],
) -> pd.DataFrame:
    discovery = spec["discovery"]
    hypothesis = spec["hypothesis"]
    threshold = float(hypothesis["shock_threshold"])
    channel = str(hypothesis["dominant_channel"])
    horizon = int(hypothesis["horizon_bars"])
    max_lag = float(hypothesis["max_entry_lag_minutes"])

    oos = filter_strict_oos(prediction, discovery["data_end_utc"])

    asset = asset.copy()
    if "ts" not in asset.columns:
        raise ValueError("asset history requires ts")
    asset["ts"] = pd.to_datetime(asset["ts"], utc=True, errors="coerce").astype(
        "datetime64[ns, UTC]"
    )
    asset = asset.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)

    events = build_event_hours(oos, min_abs_delta_1h=threshold)
    events = events[events["dominant_channel"] == channel].copy()
    if events.empty:
        return pd.DataFrame()

    aligned = align_asset(events, asset)
    if aligned.empty:
        return pd.DataFrame()

    ret_col = f"fwd_return_{horizon}bar"
    if ret_col not in aligned.columns:
        raise ValueError(f"asset history missing {ret_col}")

    rows: list[dict[str, Any]] = []
    for row in aligned.itertuples(index=False):
        event_hour = pd.Timestamp(row.event_hour)
        event_at = pd.Timestamp(row.event_at) if pd.notna(row.event_at) else None
        entry_ts = pd.Timestamp(row.ts) if pd.notna(row.ts) else None
        entry_lag = (
            float(row.entry_lag_minutes)
            if pd.notna(row.entry_lag_minutes)
            else None
        )
        forward_return = (
            float(getattr(row, ret_col))
            if pd.notna(getattr(row, ret_col))
            else None
        )

        if entry_ts is None or entry_lag is None:
            state = "WAITING_ASSET_ENTRY"
        elif entry_lag > max_lag:
            state = "EXCLUDED_ENTRY_LAG"
        elif forward_return is None:
            state = "WAITING_HORIZON"
        else:
            state = "OUTCOME_READY"

        signed_return = None
        if forward_return is not None and state == "OUTCOME_READY":
            signed_return = float(np.sign(float(row.event_score)) * forward_return)

        rows.append(
            {
                "event_id": event_id(
                    spec["hypothesis_id"],
                    event_hour,
                    channel,
                ),
                "hypothesis_id": spec["hypothesis_id"],
                "event_hour": event_hour,
                "event_at": event_at,
                "dominant_channel": str(row.dominant_channel),
                "dominant_theme": str(row.dominant_theme),
                "event_score": float(row.event_score),
                "family_count": int(row.family_count),
                "market_count": int(row.market_count),
                "mean_abs_delta_1h": float(row.mean_abs_delta_1h),
                "entry_ts": entry_ts,
                "entry_price": float(row.price) if pd.notna(row.price) else None,
                "entry_lag_minutes": entry_lag,
                "horizon_bars": horizon,
                "forward_return": forward_return,
                "signed_return": signed_return,
                "outcome_state": state,
                "source": "Polymarket US official prospective BBO collector",
            }
        )
    return pd.DataFrame(rows).sort_values("event_hour").reset_index(drop=True)


def persist_ledger(
    rows: pd.DataFrame,
    *,
    sqlite_path: Path,
    parquet_path: Path,
) -> dict[str, Any]:
    con = init_ledger(sqlite_path)
    seen_at = now_iso()
    new_events = 0
    try:
        existing = {
            x[0]
            for x in con.execute("SELECT event_id FROM events").fetchall()
        }
        for row in rows.to_dict("records") if not rows.empty else []:
            eid = str(row["event_id"])
            if eid not in existing:
                new_events += 1
            payload = {
                **row,
                "event_hour": pd.Timestamp(row["event_hour"]).isoformat(),
                "event_at": (
                    pd.Timestamp(row["event_at"]).isoformat()
                    if pd.notna(row["event_at"])
                    else None
                ),
                "entry_ts": (
                    pd.Timestamp(row["entry_ts"]).isoformat()
                    if pd.notna(row["entry_ts"])
                    else None
                ),
                "first_seen_at": seen_at,
                "last_seen_at": seen_at,
            }
            con.execute(
                """
                INSERT INTO events (
                    event_id, hypothesis_id, event_hour, event_at,
                    dominant_channel, dominant_theme, event_score,
                    family_count, market_count, mean_abs_delta_1h,
                    entry_ts, entry_price, entry_lag_minutes, horizon_bars,
                    forward_return, signed_return, outcome_state,
                    first_seen_at, last_seen_at, source
                ) VALUES (
                    :event_id, :hypothesis_id, :event_hour, :event_at,
                    :dominant_channel, :dominant_theme, :event_score,
                    :family_count, :market_count, :mean_abs_delta_1h,
                    :entry_ts, :entry_price, :entry_lag_minutes, :horizon_bars,
                    :forward_return, :signed_return, :outcome_state,
                    :first_seen_at, :last_seen_at, :source
                )
                ON CONFLICT(event_id) DO UPDATE SET
                    event_at=excluded.event_at,
                    dominant_theme=excluded.dominant_theme,
                    event_score=excluded.event_score,
                    family_count=excluded.family_count,
                    market_count=excluded.market_count,
                    mean_abs_delta_1h=excluded.mean_abs_delta_1h,
                    entry_ts=excluded.entry_ts,
                    entry_price=excluded.entry_price,
                    entry_lag_minutes=excluded.entry_lag_minutes,
                    horizon_bars=excluded.horizon_bars,
                    forward_return=excluded.forward_return,
                    signed_return=excluded.signed_return,
                    outcome_state=excluded.outcome_state,
                    last_seen_at=excluded.last_seen_at,
                    source=excluded.source
                """,
                payload,
            )
        con.commit()

        ledger = pd.read_sql_query(
            "SELECT * FROM events ORDER BY event_hour, event_id",
            con,
        )
    finally:
        con.close()

    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    if len(ledger):
        ledger["event_hour"] = pd.to_datetime(ledger["event_hour"], utc=True)
        ledger["event_at"] = pd.to_datetime(ledger["event_at"], utc=True)
        ledger["entry_ts"] = pd.to_datetime(ledger["entry_ts"], utc=True)
        tmp = parquet_path.with_suffix(parquet_path.suffix + ".tmp")
        ledger.to_parquet(tmp, index=False)
        tmp.replace(parquet_path)

    states = (
        ledger["outcome_state"].value_counts().to_dict()
        if len(ledger)
        else {}
    )
    latest = None
    if len(ledger):
        latest_row = ledger.iloc[-1]
        latest = {
            "event_id": latest_row["event_id"],
            "event_hour": str(latest_row["event_hour"]),
            "event_at": str(latest_row["event_at"]),
            "event_score": float(latest_row["event_score"]),
            "market_count": int(latest_row["market_count"]),
            "outcome_state": latest_row["outcome_state"],
            "forward_return": (
                float(latest_row["forward_return"])
                if pd.notna(latest_row["forward_return"])
                else None
            ),
            "signed_return": (
                float(latest_row["signed_return"])
                if pd.notna(latest_row["signed_return"])
                else None
            ),
        }

    return {
        "status": "LEDGER_READY",
        "events_total": int(len(ledger)),
        "new_events_this_run": int(new_events),
        "states": {str(k): int(v) for k, v in states.items()},
        "latest_event": latest,
    }


def update_ledger(
    *,
    canonical_path: Path,
    asset_path: Path,
    spec_path: Path,
    sqlite_path: Path,
    parquet_path: Path,
) -> dict[str, Any]:
    if not canonical_path.exists():
        return {
            "status": "WAITING_FOR_CANONICAL",
            "events_total": 0,
            "new_events_this_run": 0,
        }

    prediction = pd.read_parquet(canonical_path)
    spec, spec_sha = load_spec(spec_path)
    asset = load_asset_history(
        asset_path,
        str(spec["hypothesis"]["symbol"]),
    )
    rows = build_ledger_rows(prediction, asset, spec)
    status = persist_ledger(
        rows,
        sqlite_path=sqlite_path,
        parquet_path=parquet_path,
    )
    status["spec_sha256"] = spec_sha
    status["hypothesis_id"] = spec["hypothesis_id"]
    status["production_promotion"] = False
    status["r51_mutated"] = False
    status["trade_execution"] = False
    return status
