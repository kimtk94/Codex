from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.live_exit_policy import (
    PROFIT_TO_LOSS_FLIP,
    ProfitFlipState,
    advance_profit_flip,
    choose_exit_reason,
    clear_profit_flip_pending,
    should_clear_profit_flip_pending,
    validate_profit_flip_parameters,
)
from research.quant_stack.open_revalidation_backtest import (
    NY,
    UTC,
    _bootstrap_daily_delta,
    _default_us_etf_root,
    _effective_bar_close,
    _fetch_alpaca_1m,
    _fold_summary,
    _metrics,
    _sha256,
    _to_utc,
    _write_json,
)

KST = ZoneInfo("Asia/Seoul")
SCHEMA_VERSION = "kalman-live-policy-replay-v1"
CANDIDATE_NAME = "LIVE_POLICY_REPLAY_V1"


@dataclass(frozen=True)
class ReplayPolicyConfig:
    profit_flip_enabled: bool
    arm_pct: Decimal
    trigger_pct: Decimal
    recovery_pct: Decimal
    confirm_observations: int
    stop_loss: Decimal
    take_profit: Decimal
    model_rotation_enabled: bool
    target_exit_buckets: int = 4

    @classmethod
    def from_env(cls) -> "ReplayPolicyConfig":
        enabled = os.environ.get(
            "AUTO_TRADE_PROFIT_FLIP_GUARD_ENABLED", "false"
        ).strip().lower() == "true"
        arm = Decimal(os.environ.get("AUTO_TRADE_PROFIT_FLIP_ARM_PCT", "0.002"))
        trigger = Decimal(os.environ.get("AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT", "-0.002"))
        recovery = Decimal(os.environ.get("AUTO_TRADE_PROFIT_FLIP_RECOVERY_PCT", "0"))
        try:
            confirm = int(os.environ.get("AUTO_TRADE_PROFIT_FLIP_CONFIRM_OBSERVATIONS", "2"))
        except ValueError as exc:
            raise RuntimeError(
                "AUTO_TRADE_PROFIT_FLIP_CONFIRM_OBSERVATIONS must be an integer"
            ) from exc
        validate_profit_flip_parameters(
            arm_pct=arm,
            trigger_pct=trigger,
            recovery_pct=recovery,
            confirm_observations=confirm,
        )

        stop_loss = Decimal(os.environ.get("AUTO_TRADE_STOP_LOSS_PCT", "-0.03"))
        take_profit = Decimal(os.environ.get("AUTO_TRADE_TAKE_PROFIT_PCT", "0.20"))
        if stop_loss >= 0 or stop_loss < Decimal("-0.50"):
            raise RuntimeError("AUTO_TRADE_STOP_LOSS_PCT must be between -0.50 and 0")
        if take_profit <= 0 or take_profit > Decimal("5"):
            raise RuntimeError("AUTO_TRADE_TAKE_PROFIT_PCT must be > 0 and <= 5")

        rotation = os.environ.get(
            "AUTO_TRADE_MODEL_ROTATION_ENABLED", "true"
        ).strip().lower() == "true"
        return cls(
            profit_flip_enabled=enabled,
            arm_pct=arm,
            trigger_pct=trigger,
            recovery_pct=recovery,
            confirm_observations=confirm,
            stop_loss=stop_loss,
            take_profit=take_profit,
            model_rotation_enabled=rotation,
        )

    def jsonable(self) -> dict[str, Any]:
        return {
            "profit_flip_enabled": self.profit_flip_enabled,
            "arm_pct": str(self.arm_pct),
            "trigger_pct": str(self.trigger_pct),
            "recovery_pct": str(self.recovery_pct),
            "confirm_observations": self.confirm_observations,
            "stop_loss": str(self.stop_loss),
            "take_profit": str(self.take_profit),
            "model_rotation_enabled": self.model_rotation_enabled,
            "target_exit_buckets": self.target_exit_buckets,
        }

    def fingerprint(self) -> str:
        raw = json.dumps(
            self.jsonable(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class WatchTick:
    timestamp: pd.Timestamp
    source: Literal["POSITION_WATCH", "EXECUTION_WATCH"]


@dataclass(frozen=True)
class PricePoint:
    requested_at: pd.Timestamp
    bar_timestamp: pd.Timestamp
    price: float
    lag_seconds: float


class MinuteBarIndex:
    """O(log n) no-lookahead lookup over one cached minute window."""

    def __init__(self, frame: pd.DataFrame):
        z = frame.copy()
        z["timestamp"] = pd.to_datetime(z["timestamp"], utc=True, errors="coerce")
        for col in ("open", "close"):
            z[col] = pd.to_numeric(z[col], errors="coerce")
        z = (
            z.dropna(subset=["timestamp", "open", "close"])
            .sort_values("timestamp")
            .drop_duplicates("timestamp", keep="last")
            .reset_index(drop=True)
        )
        self.frame = z
        self._times_ns = z["timestamp"].astype("int64").to_numpy(dtype=np.int64)
        self._open = z["open"].to_numpy(dtype=float)
        self._close = z["close"].to_numpy(dtype=float)
        if z.empty:
            self._regular_session_dates: set[date] = set()
        else:
            local = z["timestamp"].dt.tz_convert(NY)
            mask = (local.dt.time >= dt_time(9, 30)) & (local.dt.time < dt_time(16, 0))
            self._regular_session_dates = set(local.loc[mask].dt.date.tolist())

    def has_regular_session(self, timestamp: Any) -> bool:
        return _to_utc(timestamp).tz_convert(NY).date() in self._regular_session_dates

    def open_at_or_after(
        self, timestamp: Any, *, tolerance_minutes: int = 3
    ) -> PricePoint | None:
        if len(self._times_ns) == 0:
            return None
        ts = _to_utc(timestamp)
        target_ns = int(ts.value)
        idx = int(np.searchsorted(self._times_ns, target_ns, side="left"))
        if idx >= len(self._times_ns):
            return None
        bar_ns = int(self._times_ns[idx])
        lag_seconds = (bar_ns - target_ns) / 1_000_000_000
        if lag_seconds < 0 or lag_seconds > tolerance_minutes * 60:
            return None
        value = float(self._open[idx])
        if not math.isfinite(value) or value <= 0:
            return None
        return PricePoint(
            requested_at=ts,
            bar_timestamp=pd.Timestamp(bar_ns, tz="UTC"),
            price=value,
            lag_seconds=float(lag_seconds),
        )

    def close_before(
        self, timestamp: Any, *, lookback_minutes: int = 10
    ) -> PricePoint | None:
        if len(self._times_ns) == 0:
            return None
        ts = _to_utc(timestamp)
        target_ns = int(ts.value)
        idx = int(np.searchsorted(self._times_ns, target_ns, side="left")) - 1
        if idx < 0:
            return None
        bar_ns = int(self._times_ns[idx])
        age_seconds = (target_ns - bar_ns) / 1_000_000_000
        if age_seconds <= 0 or age_seconds > lookback_minutes * 60:
            return None
        value = float(self._close[idx])
        if not math.isfinite(value) or value <= 0:
            return None
        return PricePoint(
            requested_at=ts,
            bar_timestamp=pd.Timestamp(bar_ns, tz="UTC"),
            price=value,
            lag_seconds=float(age_seconds),
        )


class BarWindowStore:
    """Disk-backed minute-window cache with a bounded in-process LRU."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        feed: str,
        refresh: bool,
        cache_only: bool,
        memory_windows: int = 24,
    ):
        self.cache_dir = Path(cache_dir)
        self.feed = str(feed)
        self.refresh = bool(refresh)
        self.cache_only = bool(cache_only)
        self.memory_windows = max(1, int(memory_windows))
        self._memory: OrderedDict[str, pd.DataFrame] = OrderedDict()

    @staticmethod
    def _safe_symbol(symbol: str) -> str:
        return symbol.upper().replace("/", "-").replace(".", "-")

    def _path(self, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> Path:
        stamp = (
            f"{start.strftime('%Y%m%dT%H%M%SZ')}__"
            f"{end.strftime('%Y%m%dT%H%M%SZ')}"
        )
        return self.cache_dir / self.feed / self._safe_symbol(symbol) / f"{stamp}.parquet"

    def load_or_fetch(
        self, symbol: str, *, start_utc: pd.Timestamp, end_utc: pd.Timestamp
    ) -> tuple[pd.DataFrame, Path, bool]:
        start_utc = _to_utc(start_utc)
        end_utc = _to_utc(end_utc)
        path = self._path(symbol, start_utc, end_utc)
        key = str(path)
        if key in self._memory and not self.refresh:
            frame = self._memory.pop(key)
            self._memory[key] = frame
            return frame.copy(), path, True

        hit = path.is_file() and not self.refresh
        if hit:
            frame = pd.read_parquet(path)
        else:
            if self.cache_only:
                raise FileNotFoundError(f"minute cache missing: {path}")
            frame = _fetch_alpaca_1m(
