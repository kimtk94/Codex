from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pathlib
import sqlite3
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.prospective_shadow import (
    CANDIDATE_ID,
    ProspectiveShadowConfig,
    ProspectiveShadowStore,
)
from engine.prospective_shadow import manage_prospective_shadows


class FakeManagedStore:
    def __init__(self, row: dict):
        self.row = dict(row)

    def get(self, position_id: str):
        if position_id == self.row.get("position_id"):
            return dict(self.row)
        return None


class FakeClient:
    async def prices(self, symbols):
        return [
            {
                "symbol": symbols[0],
                "lastPrice": "100",
                "timestamp": "2026-09-24T00:00:00Z",
            }
        ]


def _config(activated_at: datetime) -> ProspectiveShadowConfig:
    return ProspectiveShadowConfig(
        enabled=True,
        activated_at=activated_at,
    )


def _position(created_at: datetime) -> dict:
    return {
        "position_id": "p-1",
        "entry_run_id": "run-1",
        "symbol": "AMD",
        "strategy_version": "R5.1_BASE_HGB",
        "entry_signal_as_of": "2026-09-24T00:00:00+00:00",
        "created_at": created_at.isoformat(),
        "entry_avg_fill_price": "100",
        "remaining_quantity": "1.0",
        "entry_count": 1,
        "state": "OPEN",
        "exit_reason": None,
    }


def test_shadow_seed_is_strictly_prospective(tmp_path):
    activated = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)
    store = ProspectiveShadowStore(tmp_path / "state.sqlite3")

    old = _position(activated - timedelta(seconds=1))
    assert store.seed_or_sync(old, _config(activated)) is None
    assert store.summary(CANDIDATE_ID)["total"] == 0

    new = _position(activated + timedelta(seconds=1))
    seeded = store.seed_or_sync(new, _config(activated))
    assert seeded is not None
    assert seeded["state"] == "OPEN"
    assert seeded["entry_average_price"] == "100"
    assert store.summary(CANDIDATE_ID)["total"] == 1


def test_shadow_stop_loss_is_not_pending_across_recovery(tmp_path, monkeypatch):
    activated = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)
    config = _config(activated)
    store = ProspectiveShadowStore(tmp_path / "state.sqlite3")
    position = _position(activated + timedelta(seconds=1))
    store.seed_or_sync(position, config)
    managed = FakeManagedStore(position)

    async def window_closed(_client):
        return False, {"session": "CLOSED"}

    monkeypatch.setattr(
        "engine.prospective_shadow.us_fractional_order_window",
        window_closed,
    )

    reports = asyncio.run(manage_prospective_shadows(
        config=config,
        shadow_store=store,
        managed_store=managed,
        client=FakeClient(),
        db_url="unused",
        elapsed_buckets_fn=lambda _db, _asof: 0,
        price_overrides={"p-1": Decimal("96")},
        watch_source="POSITION_WATCH",
    ))
    assert reports[0]["action"] == "SHADOW_EXIT_DUE_WINDOW_CLOSED"
    assert reports[0]["exitReason"] == "STOP_LOSS_3PCT"
    assert reports[0]["brokerOrderAttempted"] is False
    assert store.open_positions(CANDIDATE_ID)

    # The no-profit-flip candidate has no pending exit state. Recovery before
    # an executable window cancels the stop signal naturally.
    reports = asyncio.run(manage_prospective_shadows(
        config=config,
        shadow_store=store,
        managed_store=managed,
        client=FakeClient(),
        db_url="unused",
        elapsed_buckets_fn=lambda _db, _asof: 0,
        price_overrides={"p-1": Decimal("100")},
        watch_source="EXECUTION_WATCH",
    ))
    assert reports[0]["action"] == "SHADOW_HOLD"
    assert reports[0]["exitReason"] is None
    assert store.open_positions(CANDIDATE_ID)


def test_shadow_closes_virtual_position_without_broker_order(tmp_path, monkeypatch):
    activated = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)
    config = _config(activated)
    store = ProspectiveShadowStore(tmp_path / "state.sqlite3")
    position = _position(activated + timedelta(seconds=1))
    store.seed_or_sync(position, config)
    managed = FakeManagedStore(position)

    async def window_open(_client):
        return True, {"session": "OPEN"}

    monkeypatch.setattr(
        "engine.prospective_shadow.us_fractional_order_window",
        window_open,
    )

    reports = asyncio.run(manage_prospective_shadows(
        config=config,
        shadow_store=store,
        managed_store=managed,
        client=FakeClient(),
        db_url="unused",
        elapsed_buckets_fn=lambda _db, _asof: 0,
        price_overrides={"p-1": Decimal("96")},
        watch_source="EXECUTION_WATCH",
    ))
    assert reports[0]["action"] == "SHADOW_EXIT"
    assert reports[0]["exitReason"] == "STOP_LOSS_3PCT"
    assert reports[0]["brokerOrderAttempted"] is False

    recent = store.recent(CANDIDATE_ID, 1)[0]
    assert recent["state"] == "CLOSED"
    assert recent["exit_reason"] == "STOP_LOSS_3PCT"
    assert Decimal(recent["exit_return"]) == Decimal("-0.04")


def test_shadow_uses_frozen_four_bucket_exit_without_profit_flip(
    tmp_path, monkeypatch
):
    activated = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)
    config = _config(activated)
    store = ProspectiveShadowStore(tmp_path / "state.sqlite3")
    position = _position(activated + timedelta(seconds=1))
    store.seed_or_sync(position, config)
    managed = FakeManagedStore(position)

    async def window_open(_client):
        return True, {"session": "OPEN"}

    monkeypatch.setattr(
        "engine.prospective_shadow.us_fractional_order_window",
        window_open,
    )

    reports = asyncio.run(manage_prospective_shadows(
        config=config,
        shadow_store=store,
        managed_store=managed,
        client=FakeClient(),
        db_url="unused",
        elapsed_buckets_fn=lambda _db, _asof: 4,
        price_overrides={"p-1": Decimal("99.5")},
        watch_source="EXECUTION_WATCH",
    ))
    assert reports[0]["action"] == "SHADOW_EXIT"
    assert reports[0]["exitReason"] == "MAX_HOLD_4_BUCKETS"
    assert "PROFIT" not in str(reports[0]["exitReason"])
    assert reports[0]["brokerOrderAttempted"] is False



def test_shadow_store_additive_schema_migration(tmp_path):
    db = tmp_path / "state.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE prospective_shadow_position (
                candidate_id TEXT NOT NULL,
                live_position_id TEXT NOT NULL,
                PRIMARY KEY (candidate_id, live_position_id)
            )
            """
        )

    ProspectiveShadowStore(db)

    with sqlite3.connect(db) as conn:
        cols = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(prospective_shadow_position)"
            ).fetchall()
        }

    assert "live_policy_exit_observed_at" in cols
    assert "live_policy_exit_reference_price" in cols
    assert "live_policy_exit_reference_return" in cols
    assert "live_policy_exit_reference_reason" in cols
