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
                self._safe_symbol(symbol),
                start_utc=start_utc,
                end_utc=end_utc,
                feed=self.feed,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(path, index=False)

        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        self._memory[key] = frame
        while len(self._memory) > self.memory_windows:
            self._memory.popitem(last=False)
        return frame.copy(), path, hit


def _iter_dates(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def iter_live_watch_ticks(start_utc: Any, end_utc: Any) -> list[WatchTick]:
    """Reproduce the committed KST cron cadence without invoking cron itself."""

    start = _to_utc(start_utc)
    end = _to_utc(end_utc)
    if end <= start:
        return []

    start_kst = start.tz_convert(KST)
    end_kst = end.tz_convert(KST)
    ticks: list[WatchTick] = []

    for day in _iter_dates(start_kst.date() - timedelta(days=1), end_kst.date()):
        if day.weekday() >= 5:
            continue

        local = datetime.combine(day, dt_time(9, 0), tzinfo=KST)
        cutoff = datetime.combine(day, dt_time(21, 30), tzinfo=KST)
        while local <= cutoff:
            ts = pd.Timestamp(local).tz_convert("UTC")
            if start < ts <= end:
                ticks.append(WatchTick(ts, "POSITION_WATCH"))
            local += timedelta(minutes=30)

        ts_2200 = pd.Timestamp(
            datetime.combine(day, dt_time(22, 0), tzinfo=KST)
        ).tz_convert("UTC")
        if start < ts_2200 <= end:
            ticks.append(WatchTick(ts_2200, "POSITION_WATCH"))

        local = datetime.combine(day, dt_time(22, 25), tzinfo=KST)
        overnight_end = datetime.combine(
            day + timedelta(days=1), dt_time(5, 55), tzinfo=KST
        )
        while local <= overnight_end:
            ts = pd.Timestamp(local).tz_convert("UTC")
            if start < ts <= end:
                ticks.append(WatchTick(ts, "EXECUTION_WATCH"))
            local += timedelta(minutes=5)

    ticks.sort(key=lambda x: (x.timestamp, 0 if x.source == "POSITION_WATCH" else 1))
    return ticks


def fractional_window_open(timestamp: Any) -> bool:
    """DST-safe regular-session proxy for Toss' authoritative live guard."""

    local = _to_utc(timestamp).tz_convert(NY)
    if local.weekday() >= 5:
        return False
    return dt_time(9, 30) <= local.time() < dt_time(16, 0)


def _state_json(state: ProfitFlipState) -> dict[str, Any]:
    return {
        "peak_price_return": (
            None if state.peak_price_return is None else str(state.peak_price_return)
        ),
        "armed": state.armed,
        "negative_count": state.negative_count,
        "pending_reason": state.pending_reason,
        "pending_since": state.pending_since,
    }


def replay_one_trade(
    row: pd.Series | dict[str, Any],
    *,
    bars: pd.DataFrame,
    config: ReplayPolicyConfig,
    event_audit: Literal["none", "changes", "full"] = "changes",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    get = row.get
    entry_ts = _to_utc(get("entry_timestamp"))
    fixed4_ts = _to_utc(get("exit_timestamp"))
    entry_effective = _effective_bar_close(entry_ts)
    fixed4_effective = _effective_bar_close(fixed4_ts)
    index = MinuteBarIndex(bars)
    entry_point = index.close_before(entry_effective)
    fixed4_point = index.close_before(fixed4_effective)

    base: dict[str, Any] = {
        "replay_data_ready": False,
        "replay_error": None,
        "entry_effective_ts": entry_effective,
        "fixed4_effective_ts": fixed4_effective,
        "entry_price_vendor": None,
        "fixed4_exit_price_vendor": None,
        "reconstructed_fixed4_raw_return": None,
        "candidate_exit_triggered": False,
        "candidate_exit_reason": None,
        "candidate_exit_at": None,
        "candidate_exit_bar_at": None,
        "candidate_exit_price_vendor": None,
        "candidate_raw_return": None,
        "watch_ticks_total": 0,
        "watch_ticks_with_price": 0,
        "position_watch_ticks_total": 0,
        "position_watch_ticks_with_price": 0,
        "execution_watch_ticks_total": 0,
        "execution_watch_ticks_with_price": 0,
        "regular_exec_ticks_total": 0,
        "regular_exec_ticks_with_price": 0,
        "profit_flip_arm_at": None,
        "profit_flip_pending_at": None,
        "profit_flip_recovery_clears": 0,
        "pending_add_on_block_observations": 0,
        "final_peak_price_return": None,
        "final_profit_flip_armed": False,
        "final_profit_flip_negative_count": 0,
        "final_pending_exit_reason": None,
        "final_pending_exit_since": None,
    }
    events: list[dict[str, Any]] = []
    if entry_point is None or fixed4_point is None:
        base["replay_error"] = "ENTRY_OR_FIXED4_PRICE_UNAVAILABLE"
        return base, events

    entry_price = float(entry_point.price)
    fixed4_price = float(fixed4_point.price)
    fixed4_raw = fixed4_price / entry_price - 1.0
    base.update(
        replay_data_ready=True,
        entry_price_vendor=entry_price,
        fixed4_exit_price_vendor=fixed4_price,
        reconstructed_fixed4_raw_return=fixed4_raw,
    )

    state = ProfitFlipState()
    exit_price: float | None = None
    exit_at: pd.Timestamp | None = None
    exit_bar_at: pd.Timestamp | None = None
    exit_reason: str | None = None

    ticks = iter_live_watch_ticks(entry_effective, fixed4_effective)
    base["watch_ticks_total"] = len(ticks)
    for tick in ticks:
        if tick.source == "POSITION_WATCH":
            base["position_watch_ticks_total"] += 1
        else:
            base["execution_watch_ticks_total"] += 1

        regular_exec = (
            tick.source == "EXECUTION_WATCH"
            and fractional_window_open(tick.timestamp)
            and index.has_regular_session(tick.timestamp)
        )
        if regular_exec:
            base["regular_exec_ticks_total"] += 1

        point = index.open_at_or_after(tick.timestamp, tolerance_minutes=3)
        if point is None:
            if event_audit == "full":
                events.append(
                    {
                        "timestamp": tick.timestamp,
                        "source": tick.source,
                        "price_available": False,
                        "regular_execution_window": regular_exec,
                    }
                )
            continue

        base["watch_ticks_with_price"] += 1
        if tick.source == "POSITION_WATCH":
            base["position_watch_ticks_with_price"] += 1
        else:
            base["execution_watch_ticks_with_price"] += 1
        if regular_exec:
            base["regular_exec_ticks_with_price"] += 1

        price_return = Decimal(str(point.price / entry_price - 1.0))
        before = state
        if config.profit_flip_enabled:
            state = advance_profit_flip(
                state,
                price_return=price_return,
                arm_pct=config.arm_pct,
                trigger_pct=config.trigger_pct,
                confirm_observations=config.confirm_observations,
                observed_at=tick.timestamp.isoformat(),
            )
            if not before.armed and state.armed and base["profit_flip_arm_at"] is None:
                base["profit_flip_arm_at"] = tick.timestamp
            if (
                before.pending_reason is None
                and state.pending_reason == PROFIT_TO_LOSS_FLIP
                and base["profit_flip_pending_at"] is None
            ):
                base["profit_flip_pending_at"] = tick.timestamp

            if should_clear_profit_flip_pending(
                pending_reason=state.pending_reason,
                price_return=price_return,
                recovery_pct=config.recovery_pct,
            ):
                state = clear_profit_flip_pending(state)
                base["profit_flip_recovery_clears"] += 1

        if state.pending_reason:
            base["pending_add_on_block_observations"] += 1

        reason = choose_exit_reason(
            price_return=price_return,
            stop_loss=config.stop_loss,
            take_profit=config.take_profit,
            model_rotation=False,
            elapsed_buckets=0,
            target_buckets=config.target_exit_buckets,
            pending_exit_reason=state.pending_reason,
        )
        state_changed = state != before
        should_log = (
            event_audit == "full"
            or (
                event_audit == "changes"
                and (state_changed or reason is not None or regular_exec)
            )
        )
        if should_log:
            events.append(
                {
                    "timestamp": tick.timestamp,
                    "bar_timestamp": point.bar_timestamp,
                    "source": tick.source,
                    "price_available": True,
                    "price": point.price,
                    "price_lag_seconds": point.lag_seconds,
                    "price_return": float(price_return),
                    "regular_execution_window": regular_exec,
                    "exit_due_reason": reason,
                    **_state_json(state),
                }
            )

        if reason is not None and regular_exec:
            exit_price = float(point.price)
            exit_at = tick.timestamp
            exit_bar_at = point.bar_timestamp
            exit_reason = reason
            break

    candidate_raw = fixed4_raw if exit_price is None else exit_price / entry_price - 1.0
    base.update(
        candidate_exit_triggered=exit_price is not None,
