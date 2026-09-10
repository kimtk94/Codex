from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

ACTIVE_STATES = (
    'ENTRY_RESERVED',
    'ENTRY_SUBMITTED',
    'OPEN',
    'EXIT_RESERVED',
    'EXIT_SUBMITTED',
    'MANUAL_RECONCILE',
    'AMBIGUOUS_ENTRY',
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def position_id_for(run_id: str, strategy_version: str, symbol: str) -> str:
    raw = f'{run_id}|{strategy_version}|{symbol.upper()}'.encode()
    return 'pos-' + hashlib.sha256(raw).hexdigest()[:20]


class ManagedPositionStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS managed_position (
                    position_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    entry_run_id TEXT NOT NULL,
                    entry_signal_as_of TEXT NOT NULL,
                    entry_client_order_id TEXT NOT NULL UNIQUE,
                    entry_order_id TEXT,
                    entry_status TEXT,
                    entry_filled_quantity TEXT NOT NULL DEFAULT '0',
                    entry_avg_fill_price TEXT,
                    remaining_quantity TEXT NOT NULL DEFAULT '0',
                    target_exit_buckets INTEGER NOT NULL DEFAULT 4,
                    exit_attempt INTEGER NOT NULL DEFAULT 0,
                    exit_client_order_id TEXT,
                    exit_order_id TEXT,
                    exit_status TEXT,
                    exit_avg_fill_price TEXT,
                    state TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )

    def _connect(self):
        return sqlite3.connect(self.path, timeout=15, isolation_level=None)

    @staticmethod
    def _dict(cursor, row) -> dict[str, Any] | None:
        if row is None:
            return None
        return {d[0]: row[i] for i, d in enumerate(cursor.description)}

    def reserve_entry(
        self,
        *,
        run_id: str,
        symbol: str,
        strategy_version: str,
        signal_as_of: str,
        client_order_id: str,
        target_exit_buckets: int,
    ) -> tuple[bool, dict[str, Any] | None]:
        now = utc_now()
        pid = position_id_for(run_id, strategy_version, symbol)
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            cur = conn.execute(
                'SELECT * FROM managed_position WHERE position_id=? OR entry_client_order_id=? LIMIT 1',
                (pid, client_order_id),
            )
            existing = self._dict(cur, cur.fetchone())
            if existing:
                conn.rollback()
                return False, existing

            marks = ','.join('?' for _ in ACTIVE_STATES)
            cur = conn.execute(
                f'SELECT * FROM managed_position WHERE state IN ({marks}) ORDER BY created_at LIMIT 1',
                ACTIVE_STATES,
            )
            active = self._dict(cur, cur.fetchone())
            if active:
                conn.rollback()
                return False, active
            conn.execute(
                """INSERT INTO managed_position (
                    position_id,symbol,strategy_version,entry_run_id,entry_signal_as_of,
                    entry_client_order_id,target_exit_buckets,state,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    pid,
                    symbol.upper(),
                    strategy_version,
                    run_id,
                    signal_as_of,
                    client_order_id,
                    int(target_exit_buckets),
                    'ENTRY_RESERVED',
                    now,
                    now,
                ),
            )
            cur = conn.execute('SELECT * FROM managed_position WHERE position_id=?', (pid,))
            row = self._dict(cur, cur.fetchone())
            conn.commit()
            return True, row

    def mark_entry_submitted(self, position_id: str, order_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE managed_position
                   SET entry_order_id=?, entry_status='SUBMITTED', state='ENTRY_SUBMITTED', updated_at=?
                   WHERE position_id=?""",
                (order_id, utc_now(), position_id),
            )

    def mark_entry_aborted(self, position_id: str, note: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE managed_position SET state='ABORTED', note=?, updated_at=? WHERE position_id=?",
                (note[:1000], utc_now(), position_id),
            )

    def mark_ambiguous_entry(self, position_id: str, note: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE managed_position SET state='AMBIGUOUS_ENTRY', note=?, updated_at=? WHERE position_id=?",
                (note[:1000], utc_now(), position_id),
            )

    def mark_open(self, position_id: str, *, entry_status: str, filled_quantity: Decimal, average_price: str | None) -> None:
        q = str(filled_quantity)
        with self._connect() as conn:
            conn.execute(
                """UPDATE managed_position
                   SET entry_status=?, entry_filled_quantity=?, entry_avg_fill_price=?,
                       remaining_quantity=?, state='OPEN', note=NULL, updated_at=?
                   WHERE position_id=?""",
                (entry_status, q, average_price, q, utc_now(), position_id),
            )

    def update_entry_status(self, position_id: str, status: str, filled_quantity: Decimal) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE managed_position SET entry_status=?, entry_filled_quantity=?, updated_at=? WHERE position_id=?",
                (status, str(filled_quantity), utc_now(), position_id),
            )

    def reserve_exit(self, position_id: str, client_order_id: str) -> tuple[bool, dict[str, Any] | None]:
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            cur = conn.execute('SELECT * FROM managed_position WHERE position_id=?', (position_id,))
            row = self._dict(cur, cur.fetchone())
            if not row or row['state'] != 'OPEN':
                conn.rollback()
                return False, row
            conn.execute(
                """UPDATE managed_position
                   SET exit_client_order_id=?, exit_order_id=NULL, exit_status='RESERVED',
                       state='EXIT_RESERVED', updated_at=? WHERE position_id=?""",
                (client_order_id, utc_now(), position_id),
            )
            cur = conn.execute('SELECT * FROM managed_position WHERE position_id=?', (position_id,))
            updated = self._dict(cur, cur.fetchone())
            conn.commit()
            return True, updated

    def mark_exit_submitted(self, position_id: str, order_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE managed_position
                   SET exit_order_id=?, exit_status='SUBMITTED', state='EXIT_SUBMITTED', updated_at=?
                   WHERE position_id=?""",
                (order_id, utc_now(), position_id),
            )

    def release_exit(self, position_id: str, note: str, *, increment_attempt: bool = True) -> None:
        with self._connect() as conn:
            if increment_attempt:
                conn.execute(
                    """UPDATE managed_position
                       SET exit_attempt=exit_attempt+1, exit_client_order_id=NULL,
                           exit_order_id=NULL, exit_status=NULL, state='OPEN', note=?, updated_at=?
                       WHERE position_id=?""",
                    (note[:1000], utc_now(), position_id),
                )
            else:
                conn.execute(
                    """UPDATE managed_position
                       SET exit_client_order_id=NULL, exit_order_id=NULL, exit_status=NULL,
                           state='OPEN', note=?, updated_at=? WHERE position_id=?""",
                    (note[:1000], utc_now(), position_id),
                )

    def apply_exit_fill(self, position_id: str, *, status: str, newly_filled_quantity: Decimal, average_price: str | None) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            cur = conn.execute('SELECT * FROM managed_position WHERE position_id=?', (position_id,))
            row = self._dict(cur, cur.fetchone())
            if not row:
                conn.rollback()
                return None
            remaining = Decimal(str(row['remaining_quantity'] or '0'))
            remaining = max(Decimal('0'), remaining - newly_filled_quantity)
            state = 'CLOSED' if remaining == 0 else 'OPEN'
            attempt = int(row['exit_attempt'] or 0) + 1
            conn.execute(
                """UPDATE managed_position
                   SET remaining_quantity=?, exit_status=?, exit_avg_fill_price=?, exit_attempt=?, state=?,
                       exit_client_order_id=CASE WHEN ?='CLOSED' THEN exit_client_order_id ELSE NULL END,
                       exit_order_id=CASE WHEN ?='CLOSED' THEN exit_order_id ELSE NULL END,
                       note=?, updated_at=? WHERE position_id=?""",
                (
                    str(remaining), status, average_price, attempt, state, state, state,
                    None if state == 'CLOSED' else f'partial/terminal exit; remaining={remaining}',
                    utc_now(), position_id,
                ),
            )
            cur = conn.execute('SELECT * FROM managed_position WHERE position_id=?', (position_id,))
            out = self._dict(cur, cur.fetchone())
            conn.commit()
            return out

    def mark_manual_reconcile(self, position_id: str, note: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE managed_position SET state='MANUAL_RECONCILE', note=?, updated_at=? WHERE position_id=?",
                (note[:1000], utc_now(), position_id),
            )

    def mark_closed_manual(self, position_id: str, note: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE managed_position SET remaining_quantity='0', state='CLOSED_MANUAL', note=?, updated_at=?
                   WHERE position_id=?""",
                (note[:1000], utc_now(), position_id),
            )

    def get(self, position_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            cur = conn.execute('SELECT * FROM managed_position WHERE position_id=?', (position_id,))
            return self._dict(cur, cur.fetchone())

    def active(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            marks = ','.join('?' for _ in ACTIVE_STATES)
            cur = conn.execute(f'SELECT * FROM managed_position WHERE state IN ({marks}) ORDER BY created_at', ACTIVE_STATES)
            return [self._dict(cur, row) for row in cur.fetchall()]

    def has_active(self) -> bool:
        return bool(self.active())

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute('SELECT * FROM managed_position ORDER BY created_at DESC LIMIT ?', (int(limit),))
            return [self._dict(cur, row) for row in cur.fetchall()]
