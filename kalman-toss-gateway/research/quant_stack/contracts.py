from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class Mode(StrEnum):
    BACKTEST = "BACKTEST"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train_start: str
    train_end: str
    valid_start: str
    valid_end: str
    test_start: str
    test_end: str
    purge_observations: int


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_name: str
    market: str
    feature_version: str
    model_version: str
    start_date: str = "2017-01-01"
    mode: Mode = Mode.BACKTEST
    git_sha: str | None = None
    notes: str | None = None

    @property
    def experiment_hash(self) -> str:
        return stable_hash(asdict(self))


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 1_000_000.0
    position_fraction: float = 0.10
    max_open_positions: int = 5
    commission_bps: float = 5.0
    slippage_bps: float = 5.0
    max_hold_bars: int | None = 20
    allow_fractional: bool = True


def stable_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
