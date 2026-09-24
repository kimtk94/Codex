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
    source_feed: str | None = None


def _is_overnight_local_time(value: Any) -> bool:
    local = _to_utc(value).tz_convert(NY)
    return local.time() >= dt_time(20, 0) or local.time() < dt_time(4, 0)


def _merge_session_feeds(
    primary: pd.DataFrame,
    overnight: pd.DataFrame,
    *,
    primary_feed: str,
    overnight_feed: str,
) -> pd.DataFrame:
    """Compose 04:00-20:00 ET primary data with 20:00-04:00 ET overnight data."""

    def normalize(frame: pd.DataFrame, source: str) -> pd.DataFrame:
        z = frame.copy()
        if "timestamp" not in z.columns:
            z["timestamp"] = pd.Series(dtype="datetime64[ns, UTC]")
        z["timestamp"] = pd.to_datetime(z["timestamp"], utc=True, errors="coerce")
        z = z.dropna(subset=["timestamp"]).copy()
        z["source_feed"] = source
        return z

    p = normalize(primary, primary_feed)
    o = normalize(overnight, overnight_feed)

    if not p.empty:
        local = p["timestamp"].dt.tz_convert(NY)
        overnight_mask = (local.dt.time >= dt_time(20, 0)) | (local.dt.time < dt_time(4, 0))
        p = p.loc[~overnight_mask].copy()

    if not o.empty:
        local = o["timestamp"].dt.tz_convert(NY)
        overnight_mask = (local.dt.time >= dt_time(20, 0)) | (local.dt.time < dt_time(4, 0))
        o = o.loc[overnight_mask].copy()

    parts = [part for part in (p, o) if not part.empty]
    if not parts:
        return pd.DataFrame(columns=list(dict.fromkeys([*p.columns, *o.columns])))
    out = pd.concat(parts, ignore_index=True, sort=False)
    return (
        out.sort_values(["timestamp", "source_feed"])
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )


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
        # Pandas 3 may preserve datetime64[us, UTC] internally. Timestamp.value
        # is always nanoseconds, so astype("int64") can silently create a
        # 1,000x unit mismatch. Normalize explicitly to ns epoch integers.
        self._times_ns = np.fromiter(
            (int(pd.Timestamp(ts).value) for ts in z["timestamp"]),
            dtype=np.int64,
            count=len(z),
        )
        self._open = z["open"].to_numpy(dtype=float)
        self._close = z["close"].to_numpy(dtype=float)
        if "source_feed" in z.columns:
            self._source_feed = z["source_feed"].fillna("").astype(str).to_numpy()
        else:
            self._source_feed = np.array([""] * len(z), dtype=object)
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
        self,
        timestamp: Any,
        *,
        lookback_minutes: int = 10,
        required_feed: str | None = None,
    ) -> PricePoint | None:
        if len(self._times_ns) == 0:
            return None
        ts = _to_utc(timestamp)
        target_ns = int(ts.value)
        idx = int(np.searchsorted(self._times_ns, target_ns, side="left")) - 1
        min_ns = target_ns - int(lookback_minutes * 60 * 1_000_000_000)
        while idx >= 0:
            bar_ns = int(self._times_ns[idx])
            if bar_ns < min_ns:
                return None
            source = str(self._source_feed[idx] or "")
            if required_feed is None or source == required_feed:
                age_seconds = (target_ns - bar_ns) / 1_000_000_000
                if age_seconds <= 0:
                    return None
                value = float(self._close[idx])
                if math.isfinite(value) and value > 0:
                    return PricePoint(
                        requested_at=ts,
                        bar_timestamp=pd.Timestamp(bar_ns, tz="UTC"),
                        price=value,
                        lag_seconds=float(max(0.0, age_seconds - 60.0)),
                        source_feed=source or None,
                    )
            idx -= 1
        return None

    def live_price_proxy(
        self,
        timestamp: Any,
        *,
        required_feed: str | None = None,
        lookback_minutes: int = 600,
    ) -> PricePoint | None:
        """Causal proxy for Toss lastPrice at a scheduled watcher tick.

        Prefer the bar open only when a bar starts exactly at the watcher
        minute. Otherwise use the latest completed minute close strictly
        before the tick. Never consume a bar that starts after the tick.
        """

        if len(self._times_ns) == 0:
            return None
        ts = _to_utc(timestamp)
        target_ns = int(ts.value)
        idx = int(np.searchsorted(self._times_ns, target_ns, side="left"))

        if idx < len(self._times_ns) and int(self._times_ns[idx]) == target_ns:
            source = str(self._source_feed[idx] or "")
            if required_feed is None or source == required_feed:
                value = float(self._open[idx])
                if math.isfinite(value) and value > 0:
                    return PricePoint(
                        requested_at=ts,
                        bar_timestamp=pd.Timestamp(target_ns, tz="UTC"),
                        price=value,
                        lag_seconds=0.0,
                        source_feed=source or None,
                    )

        return self.close_before(
            ts,
            lookback_minutes=lookback_minutes,
            required_feed=required_feed,
        )


class BarWindowStore:
    """Disk-backed minute-window cache with a bounded in-process LRU."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        feed: str,
        overnight_feed: str | None,
        refresh: bool,
        cache_only: bool,
        memory_windows: int = 24,
    ):
        self.cache_dir = Path(cache_dir)
        self.feed = str(feed)
        self.overnight_feed = (
            str(overnight_feed).strip() if overnight_feed is not None else ""
        ) or None
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
        feed_key = self.feed if not self.overnight_feed else f"{self.feed}+{self.overnight_feed}"
        return self.cache_dir / feed_key / self._safe_symbol(symbol) / f"{stamp}.parquet"

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
            primary = _fetch_alpaca_1m(
                self._safe_symbol(symbol),
                start_utc=start_utc,
                end_utc=end_utc,
                feed=self.feed,
            )
            if self.overnight_feed:
                overnight = _fetch_alpaca_1m(
                    self._safe_symbol(symbol),
                    start_utc=start_utc,
                    end_utc=end_utc,
                    feed=self.overnight_feed,
                )
                frame = _merge_session_feeds(
                    primary,
                    overnight,
                    primary_feed=self.feed,
                    overnight_feed=self.overnight_feed,
                )
            else:
                frame = primary.copy()
                frame["source_feed"] = self.feed
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
    primary_feed: str | None = None,
    overnight_feed: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    get = row.get
    entry_ts = _to_utc(get("entry_timestamp"))
    fixed4_ts = _to_utc(get("exit_timestamp"))
    entry_effective = _effective_bar_close(entry_ts)
    fixed4_effective = _effective_bar_close(fixed4_ts)
    index = MinuteBarIndex(bars)
    entry_point = index.close_before(entry_effective)
    fixed4_point = index.close_before(fixed4_effective)

    feed_counts = (
        bars["source_feed"].fillna("UNKNOWN").astype(str).value_counts().to_dict()
        if "source_feed" in bars.columns
        else {}
    )
    bar_timestamps = pd.to_datetime(
        bars.get("timestamp"), utc=True, errors="coerce"
    ) if "timestamp" in bars.columns else pd.Series(dtype="datetime64[ns, UTC]")

    base: dict[str, Any] = {
        "replay_data_ready": False,
        "bar_rows_total": int(len(bars)),
        "primary_feed_bar_rows": int(feed_counts.get(primary_feed or "", 0)),
        "overnight_feed_bar_rows": int(feed_counts.get(overnight_feed or "", 0)),
        "bar_window_first_timestamp": (
            None if bar_timestamps.dropna().empty else bar_timestamps.dropna().min()
        ),
        "bar_window_last_timestamp": (
            None if bar_timestamps.dropna().empty else bar_timestamps.dropna().max()
        ),
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
        "watch_ticks_scheduled_total": 0,
        "watch_ticks_total": 0,
        "watch_ticks_with_price": 0,
        "position_watch_ticks_total": 0,
        "position_watch_ticks_with_price": 0,
        "execution_watch_ticks_total": 0,
        "execution_watch_ticks_with_price": 0,
        "regular_exec_ticks_total": 0,
        "regular_exec_ticks_with_price": 0,
        "overnight_watch_ticks_total": 0,
        "overnight_watch_ticks_with_price": 0,
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
    base["watch_ticks_scheduled_total"] = len(ticks)
    for tick in ticks:
        # Coverage is defined over ticks actually evaluated while the
        # historical position still exists. Once an exit is triggered and the
        # replay breaks, later scheduled ticks are no longer part of the live
        # position lifecycle and must not dilute the denominator.
        base["watch_ticks_total"] += 1
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

        overnight_tick = _is_overnight_local_time(tick.timestamp)
        if overnight_tick:
            base["overnight_watch_ticks_total"] += 1

        required_feed = (
            overnight_feed if overnight_tick and overnight_feed else primary_feed
        )
        local_tick = tick.timestamp.tz_convert(NY)
        if overnight_tick:
            session_day = (
                local_tick.date()
                if local_tick.time() >= dt_time(20, 0)
                else local_tick.date() - timedelta(days=1)
            )
            session_start = pd.Timestamp(
                datetime.combine(session_day, dt_time(20, 0), tzinfo=NY)
            ).tz_convert("UTC")
        else:
            session_start = pd.Timestamp(
                datetime.combine(local_tick.date(), dt_time(4, 0), tzinfo=NY)
            ).tz_convert("UTC")
        lookback_minutes = max(
            2,
            int(math.ceil((tick.timestamp - session_start).total_seconds() / 60.0)) + 1,
        )

        point = index.live_price_proxy(
            tick.timestamp,
            required_feed=required_feed,
            lookback_minutes=lookback_minutes,
        )
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
        if overnight_tick:
            base["overnight_watch_ticks_with_price"] += 1

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
                    "price_source_feed": point.source_feed,
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
        candidate_exit_reason=exit_reason,
        candidate_exit_at=exit_at,
        candidate_exit_bar_at=exit_bar_at,
        candidate_exit_price_vendor=exit_price,
        candidate_raw_return=candidate_raw,
        final_peak_price_return=(
            None if state.peak_price_return is None else float(state.peak_price_return)
        ),
        final_profit_flip_armed=state.armed,
        final_profit_flip_negative_count=state.negative_count,
        final_pending_exit_reason=state.pending_reason,
        final_pending_exit_since=state.pending_since,
    )
    for num, den, name in [
        (base["watch_ticks_with_price"], base["watch_ticks_total"], "watch_coverage"),
        (
            base["position_watch_ticks_with_price"],
            base["position_watch_ticks_total"],
            "position_watch_coverage",
        ),
        (
            base["execution_watch_ticks_with_price"],
            base["execution_watch_ticks_total"],
            "execution_watch_coverage",
        ),
        (
            base["regular_exec_ticks_with_price"],
            base["regular_exec_ticks_total"],
            "regular_exec_coverage",
        ),
        (
            base["overnight_watch_ticks_with_price"],
            base["overnight_watch_ticks_total"],
            "overnight_watch_coverage",
        ),
    ]:
        base[name] = float(num / den) if den else 1.0
    return base, events


def _prepare_baseline(
    ledger: pd.DataFrame,
    *,
    start: str | None,
    end: str | None,
    max_trades: int | None,
) -> pd.DataFrame:
    required = {
        "policy",
        "fold",
        "entry_timestamp",
        "exit_timestamp",
        "symbol",
        "weight",
        "gross_return",
        "net_return",
    }
    missing = required.difference(ledger.columns)
    if missing:
        raise RuntimeError(f"baseline ledger missing columns: {sorted(missing)}")

    base = ledger.loc[ledger["policy"].astype(str) == "FIXED_4"].copy()
    base["entry_timestamp"] = pd.to_datetime(
        base["entry_timestamp"], utc=True, errors="coerce"
    )
    base["exit_timestamp"] = pd.to_datetime(
        base["exit_timestamp"], utc=True, errors="coerce"
    )
    base = base.dropna(
        subset=["entry_timestamp", "exit_timestamp", "symbol", "net_return"]
    )
    if start:
        base = base.loc[base["entry_timestamp"] >= _to_utc(start)]
    if end:
        base = base.loc[
            base["entry_timestamp"] < _to_utc(end) + pd.Timedelta(1, unit="D")
        ]
    base = base.sort_values(["entry_timestamp", "symbol"]).reset_index(drop=True)
    if max_trades is not None:
        base = base.head(max(0, int(max_trades))).copy()
    if base.empty:
        raise RuntimeError("no FIXED_4 trades matched the requested replay range")

    for col in ("weight", "gross_return", "net_return"):
        base[col] = pd.to_numeric(base[col], errors="coerce")
    base["cost_proxy"] = base["gross_return"] - base["net_return"]
    return base


def build_replay_audit(
    ledger: pd.DataFrame,
    *,
    config: ReplayPolicyConfig,
    window_store: BarWindowStore,
    start: str | None,
    end: str | None,
    max_trades: int | None,
    event_audit: Literal["none", "changes", "full"],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = _prepare_baseline(
        ledger, start=start, end=end, max_trades=max_trades
    )
    results: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []

    for n, (_, row) in enumerate(base.iterrows(), start=1):
        symbol = str(row["symbol"]).upper().replace(".", "-")
        entry_effective = _effective_bar_close(row["entry_timestamp"])
        fixed4_effective = _effective_bar_close(row["exit_timestamp"])
        entry_day_et = entry_effective.tz_convert(NY).date()
        exit_day_et = fixed4_effective.tz_convert(NY).date()
        # Normalize the cache window by ET calendar dates so multiple trades
        # for the same symbol/session pair reuse one disk/API object.
        fetch_start = pd.Timestamp(
            datetime.combine(entry_day_et, dt_time(0, 0), tzinfo=NY)
        ).tz_convert("UTC")
        fetch_end = pd.Timestamp(
            datetime.combine(exit_day_et, dt_time(20, 5), tzinfo=NY)
        ).tz_convert("UTC")

        try:
            bars, cache_path, cache_hit = window_store.load_or_fetch(
                symbol,
                start_utc=fetch_start,
                end_utc=fetch_end,
            )
            replay, events = replay_one_trade(
                row,
                bars=bars,
                config=config,
                event_audit=event_audit,
                primary_feed=window_store.feed,
                overnight_feed=window_store.overnight_feed,
            )
            replay["cache_path"] = str(cache_path)
            replay["cache_hit"] = bool(cache_hit)
        except Exception as exc:
            replay = {
                "replay_data_ready": False,
                "replay_error": f"{type(exc).__name__}: {exc}",
            }
            events = []

        results.append(replay)
        for event in events:
            event_rows.append(
                {
                    "trade_row": n - 1,
                    "symbol": symbol,
                    "fold": row.get("fold"),
                    "entry_timestamp": row["entry_timestamp"],
                    "exit_timestamp": row["exit_timestamp"],
                    **event,
                }
            )

        if n % 50 == 0 or n == len(base):
            ready = sum(bool(x.get("replay_data_ready")) for x in results)
            print(
                json.dumps(
                    {
                        "phase": "LIVE_POLICY_REPLAY",
                        "processed": n,
                        "target": len(base),
                        "ready": ready,
                    }
                )
            )

    replay_frame = pd.DataFrame(results)
    audit = pd.concat([base.reset_index(drop=True), replay_frame], axis=1)
    audit["candidate_net_return"] = audit["net_return"].astype(float)
    audit["reconstructed_fixed4_net_return"] = np.nan

    ready = audit["replay_data_ready"].fillna(False).astype(bool)
    if ready.any():
        audit.loc[ready, "reconstructed_fixed4_net_return"] = (
            audit.loc[ready, "weight"].astype(float)
            * pd.to_numeric(
                audit.loc[ready, "reconstructed_fixed4_raw_return"],
                errors="coerce",
            )
            - audit.loc[ready, "cost_proxy"].astype(float)
        )
        raw_delta = (
            pd.to_numeric(
                audit.loc[ready, "candidate_raw_return"], errors="coerce"
            )
            - pd.to_numeric(
                audit.loc[ready, "reconstructed_fixed4_raw_return"],
                errors="coerce",
            )
        )
        audit.loc[ready, "candidate_net_return"] = (
            audit.loc[ready, "net_return"].astype(float)
            + audit.loc[ready, "weight"].astype(float) * raw_delta
        )

    audit["candidate_delta_vs_fixed4"] = (
        audit["candidate_net_return"] - audit["net_return"]
    )
    return audit, pd.DataFrame(event_rows)


def _safe_median(series: pd.Series) -> float | None:
    z = pd.to_numeric(series, errors="coerce").dropna().astype(float)
    return None if z.empty else float(z.median())


def _coverage_summary(audit: pd.DataFrame) -> dict[str, Any]:
    ready = audit["replay_data_ready"].fillna(False).astype(bool)
    rows = int(len(audit))
    ready_rows = int(ready.sum())
    return {
        "rows": rows,
        "ready_rows": ready_rows,
        "ready_ratio": float(ready_rows / rows) if rows else 0.0,
        "median_watch_coverage": _safe_median(
            audit.loc[ready, "watch_coverage"]
        ),
        "median_position_watch_coverage": _safe_median(
            audit.loc[ready, "position_watch_coverage"]
        ),
        "median_execution_watch_coverage": _safe_median(
            audit.loc[ready, "execution_watch_coverage"]
        ),
        "median_regular_exec_coverage": _safe_median(
            audit.loc[ready, "regular_exec_coverage"]
        ),
        "median_overnight_watch_coverage": _safe_median(
            audit.loc[ready, "overnight_watch_coverage"]
        ),
        "trades_with_overnight_feed_rows": int(
            (
                pd.to_numeric(
                    audit.loc[ready, "overnight_feed_bar_rows"], errors="coerce"
                ).fillna(0)
                > 0
            ).sum()
        ),
        "median_overnight_feed_bar_rows": _safe_median(
            audit.loc[ready, "overnight_feed_bar_rows"]
        ),
    }


def _reconciliation_summary(audit: pd.DataFrame) -> dict[str, Any]:
    ready = audit["replay_data_ready"].fillna(False).astype(bool)
    z = audit.loc[ready].copy()
    if z.empty:
        return {
            "rows": 0,
            "median_abs_net_diff": None,
            "mean_abs_net_diff": None,
            "corr": None,
        }
    reconstructed = pd.to_numeric(
        z["reconstructed_fixed4_net_return"], errors="coerce"
    )
    baseline = pd.to_numeric(z["net_return"], errors="coerce")
    diff = reconstructed - baseline
    corr = reconstructed.corr(baseline)
    return {
        "rows": int(len(z)),
        "median_abs_net_diff": float(diff.abs().median()),
        "mean_abs_net_diff": float(diff.abs().mean()),
        "corr": (
            None
            if corr is None or not math.isfinite(float(corr))
            else float(corr)
        ),
    }


def _reason_attribution(audit: pd.DataFrame) -> list[dict[str, Any]]:
    z = audit.copy()
    z["attribution_reason"] = z["candidate_exit_reason"].fillna("NO_EARLY_EXIT")
    rows: list[dict[str, Any]] = []
    for reason, part in z.groupby("attribution_reason", dropna=False):
        delta = pd.to_numeric(
            part["candidate_delta_vs_fixed4"], errors="coerce"
        ).fillna(0.0)
        rows.append(
            {
                "exit_reason": str(reason),
                "trades": int(len(part)),
                "baseline_net_sum": float(
                    pd.to_numeric(part["net_return"], errors="coerce").sum()
                ),
                "candidate_net_sum": float(
                    pd.to_numeric(
                        part["candidate_net_return"], errors="coerce"
                    ).sum()
                ),
                "delta_net_sum": float(delta.sum()),
                "mean_delta_per_trade": float(delta.mean()),
                "positive_delta_rate": float((delta > 0).mean()),
            }
        )
    rows.sort(key=lambda x: x["delta_net_sum"], reverse=True)
    return rows


def evaluate_replay(
    audit: pd.DataFrame,
    *,
    config: ReplayPolicyConfig,
    feed: str,
    n_boot: int,
) -> dict[str, Any]:
    baseline = _metrics(audit, "net_return")
    candidate = _metrics(audit, "candidate_net_return")
    boot = _bootstrap_daily_delta(
        audit, "candidate_net_return", n_boot=n_boot, seed=42
    )
    folds = _fold_summary(audit, "candidate_net_return")
    positive_folds = sum(
        1
        for row in folds
        if row["paired_log_delta"] is not None
        and row["paired_log_delta"] > 0
    )
    coverage = _coverage_summary(audit)
    reconciliation = _reconciliation_summary(audit)
    attribution = _reason_attribution(audit)
    triggered = audit["candidate_exit_triggered"].fillna(False).astype(bool)
    reasons = Counter(
        str(x)
        for x in audit.loc[
            triggered, "candidate_exit_reason"
        ].dropna().tolist()
    )

    delta_log = (
        None
        if baseline["log_growth"] is None
        or candidate["log_growth"] is None
        else float(candidate["log_growth"] - baseline["log_growth"])
    )
    mdd_delta = (
        None
        if baseline["mdd"] is None or candidate["mdd"] is None
        else float(candidate["mdd"] - baseline["mdd"])
    )
    min_positive_folds = max(1, math.ceil(len(folds) * 0.60))

    research_survivor = bool(
        boot["ci95_low"] is not None
        and boot["ci95_low"] > 0
        and boot["p_one_sided"] is not None
        and boot["p_one_sided"] <= 0.10
        and positive_folds >= min_positive_folds
        and (mdd_delta is None or mdd_delta >= -0.02)
        and coverage["ready_ratio"] >= 0.90
        and coverage["median_watch_coverage"] is not None
        and coverage["median_watch_coverage"] >= 0.80
        and coverage["median_position_watch_coverage"] is not None
        and coverage["median_position_watch_coverage"] >= 0.80
        and coverage["median_execution_watch_coverage"] is not None
        and coverage["median_execution_watch_coverage"] >= 0.95
        and coverage["median_regular_exec_coverage"] is not None
        and coverage["median_regular_exec_coverage"] >= 0.95
        and coverage["median_overnight_watch_coverage"] is not None
        and coverage["median_overnight_watch_coverage"] >= 0.80
    )

    return {
        "schema": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "research_only": True,
        "production_changed": False,
        "automation_changed": False,
        "candidate": CANDIDATE_NAME,
        "source_baseline": "exit_policy_v1_0_1 FIXED_4",
        "feed": feed,
        "policy_config": config.jsonable(),
        "policy_fingerprint": config.fingerprint(),
        "baseline": baseline,
        "candidate_metrics": candidate,
        "delta_log_growth_vs_fixed4": delta_log,
        "mdd_delta_vs_fixed4": mdd_delta,
        "paired_bootstrap": boot,
        "positive_folds": int(positive_folds),
        "fold_count": int(len(folds)),
        "folds": folds,
        "coverage": coverage,
        "coverage_gate": {
            "ready_ratio_min": 0.90,
            "watch_coverage_min": 0.80,
            "position_watch_coverage_min": 0.80,
            "execution_watch_coverage_min": 0.95,
            "regular_exec_coverage_min": 0.95,
            "overnight_watch_coverage_min": 0.80,
            "passed": bool(
                coverage["ready_ratio"] >= 0.90
                and coverage["median_watch_coverage"] is not None
                and coverage["median_watch_coverage"] >= 0.80
                and coverage["median_position_watch_coverage"] is not None
                and coverage["median_position_watch_coverage"] >= 0.80
                and coverage["median_execution_watch_coverage"] is not None
                and coverage["median_execution_watch_coverage"] >= 0.95
                and coverage["median_regular_exec_coverage"] is not None
                and coverage["median_regular_exec_coverage"] >= 0.95
                and coverage["median_overnight_watch_coverage"] is not None
                and coverage["median_overnight_watch_coverage"] >= 0.80
            ),
        },
        "reconciliation": reconciliation,
        "reason_attribution": attribution,
        "triggered_exits": int(triggered.sum()),
        "trigger_rate_ready": (
            float(triggered.sum() / coverage["ready_rows"])
            if coverage["ready_rows"]
            else 0.0
        ),
        "exit_reason_counts": dict(sorted(reasons.items())),
        "research_survivor": research_survivor,
        "promotion_recommendation": (
            "PROSPECTIVE_SHADOW_ONLY"
            if research_survivor
            else "NO_PROMOTION"
        ),
        "limitations": [
            "Historical vendor bars are a proxy for Toss lastPrice and market fills.",
            "Missing overnight bars are never forward-filled; coverage gates fail closed.",
            "The Toss live market calendar is proxied by 09:30-16:00 America/New_York plus observed bars.",
            "Historical add-on opportunities are not synthesized; pending-state add-on blocking is audited only.",
            "Model rotation must be disabled unless a point-in-time eligible-signal stream is added.",
            "Candidate P&L preserves the original baseline and adds only the same-feed counterfactual return delta.",
        ],
    }


def parse_args() -> argparse.Namespace:
    root = _default_us_etf_root()
    p = argparse.ArgumentParser(
        description=(
            "Research-only exact-cadence replay of the current Kalman "
            "live exit policy"
        )
    )
    p.add_argument(
        "--baseline-ledger",
        default=str(
            root
            / "model_lab_v1/results/exit_policy_v1_0_pre2026/"
            "exit_policy_v1_0_1_trade_ledger.parquet"
        ),
    )
    p.add_argument(
        "--cache-dir",
        default=str(
            root
            / "directional_research/live_policy_replay_1m_alpaca_v1"
        ),
    )
    p.add_argument(
        "--output-dir",
        default=str(root / "model_lab_v1/results/live_policy_replay_v1"),
    )
    p.add_argument(
        "--feed",
        default=os.environ.get("LIVE_POLICY_REPLAY_ALPACA_FEED", "iex"),
        help="Primary Alpaca feed for 04:00-20:00 ET (default: iex)",
    )
    p.add_argument(
        "--overnight-feed",
        default=os.environ.get(
            "LIVE_POLICY_REPLAY_ALPACA_OVERNIGHT_FEED", "boats"
        ),
        help="Alpaca feed for 20:00-04:00 ET (default: boats; empty disables)",
    )
    p.add_argument("--start", default=None)
    p.add_argument("--end", default="2025-12-31")
    p.add_argument("--max-trades", type=int, default=None)
    p.add_argument("--refresh-cache", action="store_true")
    p.add_argument("--cache-only", action="store_true")
    p.add_argument(
        "--event-audit",
        choices=("none", "changes", "full"),
        default="changes",
    )
    p.add_argument("--n-boot", type=int, default=4000)
    p.add_argument("--backfill-only", action="store_true")
    return p.parse_args()


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(
            os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"),
            override=False,
        )
    except ImportError:
        pass

    args = parse_args()
    if args.n_boot < 100 or args.n_boot > 100_000:
        raise RuntimeError("--n-boot must be between 100 and 100000")

    config = ReplayPolicyConfig.from_env()
    if config.model_rotation_enabled:
        raise RuntimeError(
            "AUTO_TRADE_MODEL_ROTATION_ENABLED=true cannot be replayed "
            "exactly from the FIXED_4 ledger alone; disable it or add a "
            "point-in-time eligible-signal stream before running this study"
        )

    baseline_path = Path(args.baseline_ledger)
    if not baseline_path.is_file():
        raise FileNotFoundError(baseline_path)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "status.json"
    policy_path = output_dir / "policy_snapshot.json"

    _write_json(
        policy_path,
        {
            "schema": SCHEMA_VERSION,
            "captured_at_utc": datetime.now(UTC).isoformat(),
            "source": "live environment snapshot",
            "policy": config.jsonable(),
            "fingerprint": config.fingerprint(),
        },
    )
    _write_json(
        status_path,
        {
            "schema": SCHEMA_VERSION,
            "status": "RUNNING",
            "phase": "LOAD_BASELINE",
            "research_only": True,
            "production_changed": False,
            "automation_changed": False,
            "baseline_ledger": str(baseline_path),
            "baseline_sha256": _sha256(baseline_path),
            "feed": args.feed,
            "policy_fingerprint": config.fingerprint(),
        },
    )

    ledger = pd.read_parquet(baseline_path)
    store = BarWindowStore(
        cache_dir=Path(args.cache_dir),
        feed=args.feed,
        overnight_feed=(args.overnight_feed or None),
        refresh=bool(args.refresh_cache),
        cache_only=bool(args.cache_only),
    )
    audit, events = build_replay_audit(
        ledger,
        config=config,
        window_store=store,
        start=args.start,
        end=args.end,
        max_trades=args.max_trades,
        event_audit=args.event_audit,
    )

    audit_path = output_dir / "live_policy_replay_trade_audit.parquet"
    audit.to_parquet(audit_path, index=False)

    event_path: Path | None = None
    if args.event_audit != "none":
        event_path = output_dir / "live_policy_replay_event_audit.parquet"
        if events.empty:
            events = pd.DataFrame(
                columns=[
                    "trade_row",
                    "symbol",
                    "fold",
                    "entry_timestamp",
                    "exit_timestamp",
                    "timestamp",
                    "source",
                    "price_available",
                ]
            )
        events.to_parquet(event_path, index=False)

    if args.backfill_only:
        result = {
            "schema": SCHEMA_VERSION,
            "status": "BACKFILL_COMPLETE",
            "research_only": True,
            "production_changed": False,
            "automation_changed": False,
            "rows": int(len(audit)),
            "ready_rows": int(
                audit["replay_data_ready"].fillna(False).sum()
            ),
            "coverage": _coverage_summary(audit),
            "audit": str(audit_path),
            "event_audit": str(event_path) if event_path else None,
            "policy_snapshot": str(policy_path),
        }
        _write_json(status_path, result)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0

    decision = evaluate_replay(
        audit,
        config=config,
        feed=(
            args.feed
            if not args.overnight_feed
            else f"{args.feed}+{args.overnight_feed}"
        ),
        n_boot=int(args.n_boot),
    )
    decision.update(
        baseline_ledger=str(baseline_path),
        baseline_sha256=_sha256(baseline_path),
        audit_path=str(audit_path),
        event_audit_path=str(event_path) if event_path else None,
        policy_snapshot=str(policy_path),
    )

    decision_path = output_dir / "live_policy_replay_decision.json"
    _write_json(decision_path, decision)

    pd.DataFrame(decision["folds"]).to_csv(
        output_dir / "live_policy_replay_fold_summary.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {"exit_reason": reason, "count": count}
            for reason, count in decision["exit_reason_counts"].items()
        ]
    ).to_csv(
        output_dir / "live_policy_replay_reason_summary.csv",
        index=False,
    )
    pd.DataFrame(decision["reason_attribution"]).to_csv(
        output_dir / "live_policy_replay_attribution.csv",
        index=False,
    )

    final_status = {
        "schema": SCHEMA_VERSION,
        "status": "COMPLETE",
        "research_only": True,
        "production_changed": False,
        "automation_changed": False,
        "rows": int(len(audit)),
        "ready_rows": decision["coverage"]["ready_rows"],
        "coverage": decision["coverage"],
        "triggered_exits": decision["triggered_exits"],
        "research_survivor": decision["research_survivor"],
        "promotion_recommendation": decision["promotion_recommendation"],
        "decision": str(decision_path),
        "audit": str(audit_path),
        "event_audit": str(event_path) if event_path else None,
        "policy_snapshot": str(policy_path),
    }
    _write_json(status_path, final_status)
    print(json.dumps(final_status, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
