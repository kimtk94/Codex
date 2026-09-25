from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.live_exit_policy import ProfitFlipState, advance_profit_flip

ACTIVE_STATES = (
    'ENTRY_RESERVED',
    'ENTRY_SUBMITTED',
    'ADD_ON_RESERVED',
    'ADD_ON_SUBMITTED',
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
                    entry_count INTEGER NOT NULL DEFAULT 1,
                    last_entry_run_id TEXT,
                    last_entry_signal_as_of TEXT,
                    add_on_client_order_id TEXT,
                    add_on_order_id TEXT,
                    add_on_status TEXT,
                    add_on_signal_run_id TEXT,
                    add_on_signal_as_of TEXT,
                    add_on_target_krw TEXT,
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

            cols = {
                row[1] for row in conn.execute("PRAGMA table_info(managed_position)").fetchall()
            }
            if 'exit_reason' not in cols:
                conn.execute("ALTER TABLE managed_position ADD COLUMN exit_reason TEXT")
            migrations = {
                'entry_count': "ALTER TABLE managed_position ADD COLUMN entry_count INTEGER NOT NULL DEFAULT 1",
                'last_entry_run_id': "ALTER TABLE managed_position ADD COLUMN last_entry_run_id TEXT",
                'last_entry_signal_as_of': "ALTER TABLE managed_position ADD COLUMN last_entry_signal_as_of TEXT",
                'add_on_client_order_id': "ALTER TABLE managed_position ADD COLUMN add_on_client_order_id TEXT",
                'add_on_order_id': "ALTER TABLE managed_position ADD COLUMN add_on_order_id TEXT",
                'add_on_status': "ALTER TABLE managed_position ADD COLUMN add_on_status TEXT",
                'add_on_signal_run_id': "ALTER TABLE managed_position ADD COLUMN add_on_signal_run_id TEXT",
                'add_on_signal_as_of': "ALTER TABLE managed_position ADD COLUMN add_on_signal_as_of TEXT",
                'add_on_target_krw': "ALTER TABLE managed_position ADD COLUMN add_on_target_krw TEXT",
                'peak_price_return': "ALTER TABLE managed_position ADD COLUMN peak_price_return TEXT",
                'last_price_return': "ALTER TABLE managed_position ADD COLUMN last_price_return TEXT",
                'last_price_observed_at': "ALTER TABLE managed_position ADD COLUMN last_price_observed_at TEXT",
                'profit_flip_armed': "ALTER TABLE managed_position ADD COLUMN profit_flip_armed INTEGER NOT NULL DEFAULT 0",
                'profit_flip_negative_count': "ALTER TABLE managed_position ADD COLUMN profit_flip_negative_count INTEGER NOT NULL DEFAULT 0",
                'exit_pending_reason': "ALTER TABLE managed_position ADD COLUMN exit_pending_reason TEXT",
                'exit_pending_since': "ALTER TABLE managed_position ADD COLUMN exit_pending_since TEXT",
            }
            for name, ddl in migrations.items():
                if name not in cols:
                    conn.execute(ddl)
            conn.execute(
                """UPDATE managed_position
                   SET entry_count=COALESCE(entry_count, 1),
                       last_entry_run_id=COALESCE(last_entry_run_id, entry_run_id),
                       last_entry_signal_as_of=COALESCE(last_entry_signal_as_of, entry_signal_as_of)"""
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
            # Multiple different symbols may be managed concurrently when cash
            # is available. A second active lot for the same symbol is blocked
            # because exit reconciliation tracks broker quantity per symbol.
            cur = conn.execute(
                f'''SELECT * FROM managed_position
                    WHERE state IN ({marks}) AND upper(symbol)=upper(?)
                    ORDER BY created_at LIMIT 1''',
                (*ACTIVE_STATES, symbol),
            )
            active_same_symbol = self._dict(cur, cur.fetchone())
            if active_same_symbol:
                conn.rollback()
                return False, active_same_symbol
            conn.execute(
                """INSERT INTO managed_position (
                    position_id,symbol,strategy_version,entry_run_id,entry_signal_as_of,
                    entry_client_order_id,entry_count,last_entry_run_id,last_entry_signal_as_of,
                    target_exit_buckets,state,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    pid,
                    symbol.upper(),
                    strategy_version,
                    run_id,
                    signal_as_of,
                    client_order_id,
                    1,
                    run_id,
                    signal_as_of,
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

    def active_for_symbol(self, symbol: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            marks = ','.join('?' for _ in ACTIVE_STATES)
            cur = conn.execute(
                f'''SELECT * FROM managed_position
                    WHERE state IN ({marks}) AND upper(symbol)=upper(?)
                    ORDER BY created_at LIMIT 1''',
                (*ACTIVE_STATES, symbol),
            )
            return self._dict(cur, cur.fetchone())

    def reserve_add_on(
        self,
        position_id: str,
        *,
        run_id: str,
        signal_as_of: str,
        client_order_id: str,
        target_krw: str | None,
        max_entries: int,
        min_gap_minutes: int,
    ) -> tuple[bool, dict[str, Any] | None]:
        now = utc_now()
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            cur = conn.execute('SELECT * FROM managed_position WHERE position_id=?', (position_id,))
            row = self._dict(cur, cur.fetchone())
            if not row or row['state'] != 'OPEN':
                conn.rollback()
                return False, row

            entry_count = int(row.get('entry_count') or 1)
            if entry_count >= int(max_entries):
                conn.rollback()
                return False, row

            last_raw = row.get('last_entry_signal_as_of') or row.get('entry_signal_as_of')
            try:
                last_dt = datetime.fromisoformat(str(last_raw).replace('Z', '+00:00'))
                next_dt = datetime.fromisoformat(str(signal_as_of).replace('Z', '+00:00'))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                if next_dt.tzinfo is None:
                    next_dt = next_dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                conn.rollback()
                return False, row

            if next_dt <= last_dt or (next_dt - last_dt).total_seconds() < int(min_gap_minutes) * 60:
                conn.rollback()
                return False, row

            cur = conn.execute(
                '''SELECT * FROM managed_position
                   WHERE add_on_client_order_id=? AND position_id<>? LIMIT 1''',
                (client_order_id, position_id),
            )
            if cur.fetchone():
                conn.rollback()
                return False, row

            conn.execute(
                """UPDATE managed_position
                   SET add_on_client_order_id=?, add_on_order_id=NULL, add_on_status='RESERVED',
                       add_on_signal_run_id=?, add_on_signal_as_of=?, add_on_target_krw=?,
                       state='ADD_ON_RESERVED', note=NULL, updated_at=?
                   WHERE position_id=?""",
                (
                    client_order_id,
                    run_id,
                    signal_as_of,
                    target_krw,
                    now,
                    position_id,
                ),
            )
            cur = conn.execute('SELECT * FROM managed_position WHERE position_id=?', (position_id,))
            updated = self._dict(cur, cur.fetchone())
            conn.commit()
            return True, updated

    def mark_add_on_submitted(self, position_id: str, order_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE managed_position
                   SET add_on_order_id=?, add_on_status='SUBMITTED', state='ADD_ON_SUBMITTED', updated_at=?
                   WHERE position_id=?""",
                (order_id, utc_now(), position_id),
            )

    def update_add_on_status(self, position_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE managed_position SET add_on_status=?, updated_at=? WHERE position_id=?",
                (status, utc_now(), position_id),
            )

    def release_add_on(self, position_id: str, note: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE managed_position
                   SET add_on_client_order_id=NULL, add_on_order_id=NULL, add_on_status=NULL,
                       add_on_signal_run_id=NULL, add_on_signal_as_of=NULL, add_on_target_krw=NULL,
                       state='OPEN', note=?, updated_at=? WHERE position_id=?""",
                (note[:1000], utc_now(), position_id),
            )

    def mark_ambiguous_add_on(self, position_id: str, note: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE managed_position
                   SET state='MANUAL_RECONCILE', note=?, updated_at=? WHERE position_id=?""",
                (note[:1000], utc_now(), position_id),
            )

    def apply_add_on_fill(
        self,
        position_id: str,
        *,
        status: str,
        filled_quantity: Decimal,
        average_price: str | None,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            cur = conn.execute('SELECT * FROM managed_position WHERE position_id=?', (position_id,))
            row = self._dict(cur, cur.fetchone())
            if not row:
                conn.rollback()
                return None

            old_qty = Decimal(str(row.get('remaining_quantity') or '0'))
            old_avg = Decimal(str(row.get('entry_avg_fill_price') or '0'))
            add_qty = Decimal(str(filled_quantity or '0'))
            add_avg = Decimal(str(average_price or '0'))
            if old_qty <= 0 or old_avg <= 0 or add_qty <= 0 or add_avg <= 0:
                conn.rollback()
                raise ValueError('invalid aggregate inputs for add-on fill')

            total_qty = old_qty + add_qty
            weighted_avg = ((old_qty * old_avg) + (add_qty * add_avg)) / total_qty
            entry_count = int(row.get('entry_count') or 1) + 1
            conn.execute(
                """UPDATE managed_position
                   SET entry_status=?, entry_filled_quantity=?, entry_avg_fill_price=?,
                       remaining_quantity=?, entry_count=?,
                       last_entry_run_id=add_on_signal_run_id,
                       last_entry_signal_as_of=add_on_signal_as_of,
                       add_on_client_order_id=NULL, add_on_order_id=NULL, add_on_status=NULL,
                       add_on_signal_run_id=NULL, add_on_signal_as_of=NULL, add_on_target_krw=NULL,
                       peak_price_return=NULL, last_price_return=NULL, last_price_observed_at=NULL,
                       profit_flip_armed=0, profit_flip_negative_count=0,
                       exit_pending_reason=NULL, exit_pending_since=NULL,
                       state='OPEN', note=NULL, updated_at=?
                   WHERE position_id=?""",
                (
                    status,
                    str(total_qty),
                    str(weighted_avg),
                    str(total_qty),
                    entry_count,
                    utc_now(),
                    position_id,
                ),
            )
            cur = conn.execute('SELECT * FROM managed_position WHERE position_id=?', (position_id,))
            updated = self._dict(cur, cur.fetchone())
            conn.commit()
            return updated

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
                       remaining_quantity=?, peak_price_return=NULL, last_price_return=NULL,
                       last_price_observed_at=NULL, profit_flip_armed=0,
                       profit_flip_negative_count=0, exit_pending_reason=NULL,
                       exit_pending_since=NULL, state='OPEN', note=NULL, updated_at=?
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
                           exit_order_id=NULL, exit_status=NULL, exit_reason=NULL, state='OPEN', note=?, updated_at=?
                       WHERE position_id=?""",
                    (note[:1000], utc_now(), position_id),
                )
            else:
                conn.execute(
                    """UPDATE managed_position
                       SET exit_client_order_id=NULL, exit_order_id=NULL, exit_status=NULL,
                           exit_reason=NULL, state='OPEN', note=?, updated_at=? WHERE position_id=?""",
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

    def set_exit_reason(self, position_id: str, reason: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE managed_position SET exit_reason=?, updated_at=? WHERE position_id=?",
                (reason[:100], utc_now(), position_id),
            )

    def observe_price_return(
        self,
        position_id: str,
        *,
        price_return: Decimal,
        arm_pct: Decimal,
        trigger_pct: Decimal,
        confirm_observations: int,
    ) -> dict[str, Any] | None:
        """Persist profit-to-loss guard state for an OPEN managed position."""
        now = utc_now()
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            cur = conn.execute('SELECT * FROM managed_position WHERE position_id=?', (position_id,))
            row = self._dict(cur, cur.fetchone())
            if not row or row['state'] != 'OPEN':
                conn.rollback()
                return row

            previous_peak_raw = row.get('peak_price_return')
            state = advance_profit_flip(
                ProfitFlipState(
                    peak_price_return=(
                        Decimal(str(previous_peak_raw))
                        if previous_peak_raw not in (None, '')
                        else None
                    ),
                    armed=bool(int(row.get('profit_flip_armed') or 0)),
                    negative_count=int(row.get('profit_flip_negative_count') or 0),
                    pending_reason=row.get('exit_pending_reason'),
                    pending_since=row.get('exit_pending_since'),
                ),
                price_return=price_return,
                arm_pct=arm_pct,
                trigger_pct=trigger_pct,
                confirm_observations=confirm_observations,
                observed_at=now,
            )
            peak = state.peak_price_return
            armed = state.armed
            negative_count = state.negative_count
            pending_reason = state.pending_reason
            pending_since = state.pending_since

            conn.execute(
                """UPDATE managed_position
                   SET peak_price_return=?, last_price_return=?, last_price_observed_at=?,
                       profit_flip_armed=?, profit_flip_negative_count=?,
                       exit_pending_reason=?, exit_pending_since=?, updated_at=?
                   WHERE position_id=?""",
                (
                    str(peak),
                    str(price_return),
                    now,
                    1 if armed else 0,
                    negative_count,
                    pending_reason,
                    pending_since,
                    now,
                    position_id,
                ),
            )
            cur = conn.execute('SELECT * FROM managed_position WHERE position_id=?', (position_id,))
            updated = self._dict(cur, cur.fetchone())
            conn.commit()
            return updated

    def clear_exit_pending(self, position_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE managed_position
                   SET exit_pending_reason=NULL, exit_pending_since=NULL,
                       profit_flip_negative_count=0, updated_at=?
                   WHERE position_id=?""",
                (utc_now(), position_id),
            )

    def mark_manual_reconcile(self, position_id: str, note: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE managed_position SET state='MANUAL_RECONCILE', note=?, updated_at=? WHERE position_id=?",
                (note[:1000], utc_now(), position_id),
            )

    def mark_closed_manual(self, position_id: str, note: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE managed_position SET remaining_quantity='0', state='CLOSED_MANUAL', exit_reason='MANUAL_BROKER_FLAT', note=?, updated_at=?
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
