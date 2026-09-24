from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

CANDIDATE_ID = "LIVE_POLICY_NO_PROFIT_FLIP_V1"
STOP_LOSS = Decimal("-0.03")
TAKE_PROFIT = Decimal("0.20")
TARGET_EXIT_BUCKETS = 4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _candidate_fingerprint() -> str:
    payload = {
        "candidate_id": CANDIDATE_ID,
        "profit_flip_enabled": False,
        "stop_loss_pct": str(STOP_LOSS),
        "take_profit_pct": str(TAKE_PROFIT),
        "model_rotation_enabled": False,
        "target_exit_buckets": TARGET_EXIT_BUCKETS,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ProspectiveShadowConfig:
    enabled: bool
    activated_at: datetime | None
    candidate_id: str = CANDIDATE_ID
    stop_loss: Decimal = STOP_LOSS
    take_profit: Decimal = TAKE_PROFIT
    target_exit_buckets: int = TARGET_EXIT_BUCKETS
    fingerprint: str = _candidate_fingerprint()

    @classmethod
    def from_env(cls) -> "ProspectiveShadowConfig":
        enabled = (
            os.environ.get("PROSPECTIVE_SHADOW_ENABLED", "false")
            .strip()
            .lower()
            == "true"
        )
        candidate_id = (
            os.environ.get("PROSPECTIVE_SHADOW_CANDIDATE_ID", CANDIDATE_ID)
            .strip()
            or CANDIDATE_ID
        )
        if candidate_id != CANDIDATE_ID:
            raise RuntimeError(
                f"unsupported prospective shadow candidate: {candidate_id}"
            )

        activated_at = _parse_utc(
            os.environ.get("PROSPECTIVE_SHADOW_ACTIVATED_AT")
        )
        if enabled and activated_at is None:
            raise RuntimeError(
                "PROSPECTIVE_SHADOW_ACTIVATED_AT is required when "
                "PROSPECTIVE_SHADOW_ENABLED=true"
            )
        return cls(enabled=enabled, activated_at=activated_at)

    def jsonable(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "candidate_id": self.candidate_id,
            "activated_at": (
                None if self.activated_at is None else self.activated_at.isoformat()
            ),
            "profit_flip_enabled": False,
            "stop_loss_pct": str(self.stop_loss),
            "take_profit_pct": str(self.take_profit),
            "model_rotation_enabled": False,
            "target_exit_buckets": self.target_exit_buckets,
            "fingerprint": self.fingerprint,
        }


class ProspectiveShadowStore:
    """Persistent virtual-position ledger. It never submits broker orders."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return None if row is None else dict(row)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prospective_shadow_position (
                    candidate_id TEXT NOT NULL,
                    candidate_fingerprint TEXT NOT NULL,
                    live_position_id TEXT NOT NULL,
                    entry_run_id TEXT,
                    symbol TEXT NOT NULL,
                    strategy_version TEXT,
                    entry_signal_as_of TEXT NOT NULL,
                    live_created_at TEXT,
                    seeded_at TEXT NOT NULL,
                    entry_average_price TEXT NOT NULL,
                    entry_quantity TEXT,
                    entry_count INTEGER NOT NULL DEFAULT 1,
                    target_exit_buckets INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    last_observed_at TEXT,
                    last_price TEXT,
                    last_price_return TEXT,
                    last_elapsed_buckets INTEGER,
                    last_watch_source TEXT,
                    last_exit_signal_reason TEXT,
                    exit_at TEXT,
                    exit_price TEXT,
                    exit_return TEXT,
                    exit_reason TEXT,
                    live_state_last TEXT,
                    live_exit_reason_last TEXT,
                    live_policy_exit_observed_at TEXT,
                    live_policy_exit_reference_price TEXT,
                    live_policy_exit_reference_return TEXT,
                    live_policy_exit_reference_reason TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (candidate_id, live_position_id)
                )
                """
            )
            existing_columns = {
                str(row["name"])
                for row in conn.execute(
                    "PRAGMA table_info(prospective_shadow_position)"
                ).fetchall()
            }
            additive_columns = {
                "live_policy_exit_observed_at": "TEXT",
                "live_policy_exit_reference_price": "TEXT",
                "live_policy_exit_reference_return": "TEXT",
                "live_policy_exit_reference_reason": "TEXT",
            }
            for name, sql_type in additive_columns.items():
                if name not in existing_columns:
                    conn.execute(
                        f"ALTER TABLE prospective_shadow_position "
                        f"ADD COLUMN {name} {sql_type}"
                    )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prospective_shadow_observation (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    live_position_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    watch_source TEXT,
                    symbol TEXT NOT NULL,
                    price TEXT NOT NULL,
                    price_return TEXT NOT NULL,
                    elapsed_buckets INTEGER NOT NULL,
                    order_window_open INTEGER NOT NULL,
                    exit_signal_reason TEXT,
                    action TEXT NOT NULL,
                    live_state TEXT,
                    live_exit_reason TEXT,
                    FOREIGN KEY (candidate_id, live_position_id)
                      REFERENCES prospective_shadow_position(candidate_id, live_position_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_prospective_shadow_state
                ON prospective_shadow_position(candidate_id, state, seeded_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_prospective_shadow_obs
                ON prospective_shadow_observation(candidate_id, observed_at)
                """
            )

    def seed_or_sync(
        self,
        position: dict[str, Any],
        config: ProspectiveShadowConfig,
    ) -> dict[str, Any] | None:
        if not config.enabled or config.activated_at is None:
            return None

        live_created_at = _parse_utc(position.get("created_at"))
        if live_created_at is None or live_created_at < config.activated_at:
            return None

        live_position_id = str(position.get("position_id") or "").strip()
        symbol = str(position.get("symbol") or "").strip().upper()
        entry_signal_as_of = str(position.get("entry_signal_as_of") or "").strip()
        entry_price_raw = position.get("entry_avg_fill_price")
        if not live_position_id or not symbol or not entry_signal_as_of:
            return None
        try:
            entry_price = Decimal(str(entry_price_raw or "0"))
        except Exception:
            return None
        if entry_price <= 0:
            return None

        now = utc_now()
        with self._connect() as conn:
            current = conn.execute(
                """
                SELECT * FROM prospective_shadow_position
                WHERE candidate_id=? AND live_position_id=?
                """,
                (config.candidate_id, live_position_id),
            ).fetchone()

            if current is None:
                conn.execute(
                    """
                    INSERT INTO prospective_shadow_position (
                        candidate_id,candidate_fingerprint,live_position_id,
                        entry_run_id,symbol,strategy_version,entry_signal_as_of,
                        live_created_at,seeded_at,entry_average_price,
                        entry_quantity,entry_count,target_exit_buckets,state,
                        live_state_last,live_exit_reason_last,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'OPEN',?,?,?)
                    """,
                    (
                        config.candidate_id,
                        config.fingerprint,
                        live_position_id,
                        position.get("entry_run_id"),
                        symbol,
                        position.get("strategy_version"),
                        entry_signal_as_of,
                        position.get("created_at"),
                        now,
                        str(entry_price),
                        position.get("remaining_quantity"),
                        int(position.get("entry_count") or 1),
                        config.target_exit_buckets,
                        position.get("state"),
                        position.get("exit_reason"),
                        now,
                    ),
                )
            elif str(current["state"]).upper() == "OPEN":
                # Mirror only entry/add-on facts that actually happened before
                # the live policy diverged. Once the shadow closes, it is frozen.
                conn.execute(
                    """
                    UPDATE prospective_shadow_position
                    SET entry_average_price=?, entry_quantity=?, entry_count=?,
                        live_state_last=?, live_exit_reason_last=?, updated_at=?
                    WHERE candidate_id=? AND live_position_id=? AND state='OPEN'
                    """,
                    (
                        str(entry_price),
                        position.get("remaining_quantity"),
                        int(position.get("entry_count") or 1),
                        position.get("state"),
                        position.get("exit_reason"),
                        now,
                        config.candidate_id,
                        live_position_id,
                    ),
                )
            row = conn.execute(
                """
                SELECT * FROM prospective_shadow_position
                WHERE candidate_id=? AND live_position_id=?
                """,
                (config.candidate_id, live_position_id),
            ).fetchone()
            return self._dict(row)

    def record_live_policy_exit_reference(
        self,
        candidate_id: str,
        live_position_id: str,
        *,
        observed_at: str,
        price: Decimal,
        price_return: Decimal,
        reason: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE prospective_shadow_position
                SET live_policy_exit_observed_at=?,
                    live_policy_exit_reference_price=?,
                    live_policy_exit_reference_return=?,
                    live_policy_exit_reference_reason=?,
                    updated_at=?
                WHERE candidate_id=? AND live_position_id=?
                  AND live_policy_exit_observed_at IS NULL
                """,
                (
                    observed_at,
                    str(price),
                    str(price_return),
                    reason,
                    observed_at,
                    candidate_id,
                    live_position_id,
                ),
            )

    def update_live_link(
        self,
        candidate_id: str,
        live_position_id: str,
        *,
        live_state: str | None,
        live_exit_reason: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE prospective_shadow_position
                SET live_state_last=?, live_exit_reason_last=?, updated_at=?
                WHERE candidate_id=? AND live_position_id=?
                """,
                (
                    live_state,
                    live_exit_reason,
                    utc_now(),
                    candidate_id,
                    live_position_id,
                ),
            )

    def open_positions(self, candidate_id: str = CANDIDATE_ID) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM prospective_shadow_position
                WHERE candidate_id=? AND state='OPEN'
                ORDER BY seeded_at, live_position_id
                """,
                (candidate_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def has_open(self, candidate_id: str = CANDIDATE_ID) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM prospective_shadow_position
                WHERE candidate_id=? AND state='OPEN' LIMIT 1
                """,
                (candidate_id,),
            ).fetchone()
            return row is not None

    def observe(
        self,
        *,
        candidate_id: str,
        live_position_id: str,
        observed_at: str,
        watch_source: str,
        price: Decimal,
        price_return: Decimal,
        elapsed_buckets: int,
        order_window_open: bool,
        exit_signal_reason: str | None,
        live_state: str | None,
        live_exit_reason: str | None,
        close_shadow: bool,
    ) -> dict[str, Any] | None:
        action = "SHADOW_EXIT" if close_shadow else (
            "EXIT_DUE_WINDOW_CLOSED" if exit_signal_reason else "HOLD"
        )
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM prospective_shadow_position
                WHERE candidate_id=? AND live_position_id=?
                """,
                (candidate_id, live_position_id),
            ).fetchone()
            if row is None or str(row["state"]).upper() != "OPEN":
                conn.rollback()
                return self._dict(row)

            conn.execute(
                """
                INSERT INTO prospective_shadow_observation (
                    candidate_id,live_position_id,observed_at,watch_source,
                    symbol,price,price_return,elapsed_buckets,order_window_open,
                    exit_signal_reason,action,live_state,live_exit_reason
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    candidate_id,
                    live_position_id,
                    observed_at,
                    watch_source,
                    row["symbol"],
                    str(price),
                    str(price_return),
                    int(elapsed_buckets),
                    1 if order_window_open else 0,
                    exit_signal_reason,
                    action,
                    live_state,
                    live_exit_reason,
                ),
            )

            if close_shadow:
                conn.execute(
                    """
                    UPDATE prospective_shadow_position
                    SET state='CLOSED', last_observed_at=?, last_price=?,
                        last_price_return=?, last_elapsed_buckets=?,
                        last_watch_source=?, last_exit_signal_reason=?,
                        exit_at=?, exit_price=?, exit_return=?, exit_reason=?,
                        live_state_last=?, live_exit_reason_last=?, updated_at=?
                    WHERE candidate_id=? AND live_position_id=?
                    """,
                    (
                        observed_at,
                        str(price),
                        str(price_return),
                        int(elapsed_buckets),
                        watch_source,
                        exit_signal_reason,
                        observed_at,
                        str(price),
                        str(price_return),
                        exit_signal_reason,
                        live_state,
                        live_exit_reason,
                        observed_at,
                        candidate_id,
                        live_position_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE prospective_shadow_position
                    SET last_observed_at=?, last_price=?, last_price_return=?,
                        last_elapsed_buckets=?, last_watch_source=?,
                        last_exit_signal_reason=?, live_state_last=?,
                        live_exit_reason_last=?, updated_at=?
                    WHERE candidate_id=? AND live_position_id=?
                    """,
                    (
                        observed_at,
                        str(price),
                        str(price_return),
                        int(elapsed_buckets),
                        watch_source,
                        exit_signal_reason,
                        live_state,
                        live_exit_reason,
                        observed_at,
                        candidate_id,
                        live_position_id,
                    ),
                )

            out = conn.execute(
                """
                SELECT * FROM prospective_shadow_position
                WHERE candidate_id=? AND live_position_id=?
                """,
                (candidate_id, live_position_id),
            ).fetchone()
            conn.commit()
            return self._dict(out)

    def recent(self, candidate_id: str = CANDIDATE_ID, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM prospective_shadow_position
                WHERE candidate_id=?
                ORDER BY seeded_at DESC LIMIT ?
                """,
                (candidate_id, int(limit)),
            ).fetchall()
            return [dict(row) for row in rows]

    def summary(self, candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    count(*) AS total,
                    sum(CASE WHEN state='OPEN' THEN 1 ELSE 0 END) AS open_count,
                    sum(CASE WHEN state='CLOSED' THEN 1 ELSE 0 END) AS closed_count,
                    min(seeded_at) AS first_seeded_at,
                    max(seeded_at) AS last_seeded_at
                FROM prospective_shadow_position
                WHERE candidate_id=?
                """,
                (candidate_id,),
            ).fetchone()
            obs = conn.execute(
                """
                SELECT count(*) AS observations,
                       count(DISTINCT substr(observed_at,1,10)) AS utc_days
                FROM prospective_shadow_observation
                WHERE candidate_id=?
                """,
                (candidate_id,),
            ).fetchone()
            return {
                "candidate_id": candidate_id,
                "total": int(row["total"] or 0),
                "open": int(row["open_count"] or 0),
                "closed": int(row["closed_count"] or 0),
                "first_seeded_at": row["first_seeded_at"],
                "last_seeded_at": row["last_seeded_at"],
                "observations": int(obs["observations"] or 0),
                "utc_days": int(obs["utc_days"] or 0),
            }
