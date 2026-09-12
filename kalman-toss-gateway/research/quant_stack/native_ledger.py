from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .contracts import BacktestConfig


BUY_LABELS = {"BUY", "LONG", "ENTER", "1"}
SELL_LABELS = {"SELL", "EXIT", "CLOSE", "-1"}


@dataclass(frozen=True)
class BacktestResult:
    trades: pd.DataFrame
    equity: pd.DataFrame
    metrics: dict[str, Any]


def _check_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{name} missing columns: {sorted(missing)}")


def _as_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def map_next_bar(signals: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Map each signal to the strictly next available price bar.

    Required signals columns:
        symbol, signal_ts, signal
    Optional:
        entry_allowed

    Required prices columns:
        symbol, ts, open, close
    """
    _check_columns(signals, {"symbol", "signal_ts", "signal"}, "signals")
    _check_columns(prices, {"symbol", "ts", "open", "close"}, "prices")

    s = signals.copy()
    p = prices.copy()
    s["signal_ts"] = pd.to_datetime(s["signal_ts"], utc=True, errors="raise")
    p["ts"] = pd.to_datetime(p["ts"], utc=True, errors="raise")
    p = p.sort_values(["symbol", "ts"]).drop_duplicates(["symbol", "ts"], keep="last")

    if "entry_allowed" not in s:
        s["entry_allowed"] = True
    s["entry_allowed"] = s["entry_allowed"].map(_as_bool)
    s["signal"] = s["signal"].astype(str).str.upper().str.strip()

    rows: list[dict[str, Any]] = []
    grouped = {symbol: g.reset_index(drop=True) for symbol, g in p.groupby("symbol")}

    for row in s.sort_values(["signal_ts", "symbol"]).to_dict("records"):
        symbol = str(row["symbol"])
        bars = grouped.get(symbol)
        if bars is None or bars.empty:
            continue
        i = bars["ts"].searchsorted(row["signal_ts"], side="right")
        if i >= len(bars):
            continue
        bar = bars.iloc[i]
        out = dict(row)
        out.update(
            {
                "fill_ts": bar["ts"],
                "fill_open": float(bar["open"]),
                "fill_close": float(bar["close"]),
            }
        )
        rows.append(out)

    columns = list(s.columns) + ["fill_ts", "fill_open", "fill_close"]
    return pd.DataFrame(rows, columns=columns)


def _fee(notional: float, bps: float) -> float:
    return abs(float(notional)) * float(bps) / 10_000.0


def run_backtest(
    signals: pd.DataFrame,
    prices: pd.DataFrame,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Long-only, next-bar-open simulator used as Kalman's reference ledger."""
    cfg = config or BacktestConfig()
    mapped = map_next_bar(signals, prices)

    p = prices.copy()
    p["ts"] = pd.to_datetime(p["ts"], utc=True, errors="raise")
    p = p.sort_values(["symbol", "ts"]).drop_duplicates(["symbol", "ts"], keep="last")
    _check_columns(p, {"symbol", "ts", "open", "close"}, "prices")

    price_map = {symbol: g.set_index("ts").sort_index() for symbol, g in p.groupby("symbol")}
    signal_map = (
        {}
        if mapped.empty
        else {pd.Timestamp(ts): g.copy() for ts, g in mapped.groupby("fill_ts")}
    )

    cash = float(cfg.initial_cash)
    positions: dict[str, dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []

    all_ts = sorted(pd.to_datetime(p["ts"], utc=True).unique())

    for ts_value in all_ts:
        ts = pd.Timestamp(ts_value)
        batch = signal_map.get(ts)

        if batch is not None:
            # Exit before entry.
            for row in batch.itertuples(index=False):
                symbol = str(row.symbol)
                action = str(row.signal).upper()
                if action not in SELL_LABELS or symbol not in positions:
                    continue
                pos = positions.pop(symbol)
                exit_price = float(row.fill_open) * (1.0 - cfg.slippage_bps / 10_000.0)
                exit_fee = _fee(pos["qty"] * exit_price, cfg.commission_bps)
                cash += pos["qty"] * exit_price - exit_fee
                gross = pos["qty"] * (exit_price - pos["entry_price"])
                net = gross - pos["entry_fee"] - exit_fee
                trades.append(
                    {
                        "symbol": symbol,
                        "entry_ts": pos["entry_ts"],
                        "exit_ts": ts,
                        "qty": pos["qty"],
                        "entry_price": pos["entry_price"],
                        "exit_price": exit_price,
                        "entry_fee": pos["entry_fee"],
                        "exit_fee": exit_fee,
                        "gross_pnl": gross,
                        "net_pnl": net,
                        "return_pct": exit_price / pos["entry_price"] - 1.0,
                        "exit_reason": "SELL_SIGNAL",
                    }
                )

            for row in batch.itertuples(index=False):
                symbol = str(row.symbol)
                action = str(row.signal).upper()
                allowed = _as_bool(getattr(row, "entry_allowed", True))
                if (
                    action not in BUY_LABELS
                    or not allowed
                    or symbol in positions
                    or len(positions) >= cfg.max_open_positions
                ):
                    continue

                position_value = 0.0
                for open_symbol, pos in positions.items():
                    bars = price_map[open_symbol]
                    mark = (
                        float(bars.loc[ts, "close"])
                        if ts in bars.index
                        else float(pos["entry_price"])
                    )
                    position_value += pos["qty"] * mark

                equity_before = cash + position_value
                budget = min(cash, equity_before * cfg.position_fraction)
                if budget <= 0:
                    continue

                entry_price = float(row.fill_open) * (1.0 + cfg.slippage_bps / 10_000.0)
                qty = budget / entry_price
                if not cfg.allow_fractional:
                    qty = float(np.floor(qty))
                entry_fee = _fee(qty * entry_price, cfg.commission_bps)
                total = qty * entry_price + entry_fee
                if total > cash:
                    qty = cash / (entry_price * (1.0 + cfg.commission_bps / 10_000.0))
                    if not cfg.allow_fractional:
                        qty = float(np.floor(qty))
                    entry_fee = _fee(qty * entry_price, cfg.commission_bps)
                    total = qty * entry_price + entry_fee
                if qty <= 0:
                    continue

                cash -= total
                positions[symbol] = {
                    "qty": qty,
                    "entry_ts": ts,
                    "entry_price": entry_price,
                    "entry_fee": entry_fee,
                    "bars_held": 0,
                }

        # Time-based exit in bars, not calendar days.
        if cfg.max_hold_bars is not None:
            to_exit: list[str] = []
            for symbol, pos in positions.items():
                if symbol in price_map and ts in price_map[symbol].index:
                    pos["bars_held"] += 1
                    if pos["bars_held"] >= cfg.max_hold_bars:
                        to_exit.append(symbol)

            for symbol in to_exit:
                pos = positions.pop(symbol)
                close_price = float(price_map[symbol].loc[ts, "close"])
                exit_price = close_price * (1.0 - cfg.slippage_bps / 10_000.0)
                exit_fee = _fee(pos["qty"] * exit_price, cfg.commission_bps)
                cash += pos["qty"] * exit_price - exit_fee
                gross = pos["qty"] * (exit_price - pos["entry_price"])
                net = gross - pos["entry_fee"] - exit_fee
                trades.append(
                    {
                        "symbol": symbol,
                        "entry_ts": pos["entry_ts"],
                        "exit_ts": ts,
                        "qty": pos["qty"],
                        "entry_price": pos["entry_price"],
                        "exit_price": exit_price,
                        "entry_fee": pos["entry_fee"],
                        "exit_fee": exit_fee,
                        "gross_pnl": gross,
                        "net_pnl": net,
                        "return_pct": exit_price / pos["entry_price"] - 1.0,
                        "exit_reason": "MAX_HOLD_BARS",
                    }
                )

        marked = 0.0
        for symbol, pos in positions.items():
            bars = price_map[symbol]
            mark = float(bars.loc[ts, "close"]) if ts in bars.index else pos["entry_price"]
            marked += pos["qty"] * mark

        equity_rows.append(
            {
                "ts": ts,
                "cash": cash,
                "position_value": marked,
                "equity": cash + marked,
                "open_positions": len(positions),
            }
        )

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_rows)
    metrics = performance_metrics(trades_df, equity_df)
    return BacktestResult(trades=trades_df, equity=equity_df, metrics=metrics)


def performance_metrics(trades: pd.DataFrame, equity: pd.DataFrame) -> dict[str, Any]:
    if equity.empty:
        return {"trade_count": 0}

    e = equity.sort_values("ts").copy()
    e["ts"] = pd.to_datetime(e["ts"], utc=True)
    # Always evaluate risk metrics on daily closing equity so intraday bars do not
    # inflate annualization.
    daily = e.set_index("ts")["equity"].resample("1D").last().dropna()
    returns = daily.pct_change().dropna()

    start = float(daily.iloc[0])
    end = float(daily.iloc[-1])
    span_days = max((daily.index[-1] - daily.index[0]).days, 1)
    years = span_days / 365.25
    total_return = end / start - 1.0
    cagr = (end / start) ** (1.0 / years) - 1.0 if years > 0 and start > 0 else np.nan

    vol = float(returns.std(ddof=0) * np.sqrt(252)) if not returns.empty else 0.0
    sharpe = (
        float(returns.mean() / returns.std(ddof=0) * np.sqrt(252))
        if len(returns) > 1 and returns.std(ddof=0) > 0
        else np.nan
    )
    downside = returns[returns < 0].std(ddof=0)
    sortino = (
        float(returns.mean() / downside * np.sqrt(252))
        if pd.notna(downside) and downside > 0
        else np.nan
    )

    drawdown = daily / daily.cummax() - 1.0
    max_drawdown = float(drawdown.min())

    pnl = (
        pd.to_numeric(trades["net_pnl"], errors="coerce").fillna(0.0)
        if not trades.empty and "net_pnl" in trades
        else pd.Series(dtype=float)
    )
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    profit_factor = (
        float(wins.sum() / abs(losses.sum()))
        if not losses.empty and abs(losses.sum()) > 0
        else np.nan
    )

    return {
        "trade_count": int(len(trades)),
        "start": daily.index[0],
        "end": daily.index[-1],
        "ending_equity": end,
        "total_return": float(total_return),
        "cagr": float(cagr),
        "annualized_volatility": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "win_rate": float((pnl > 0).mean()) if not pnl.empty else np.nan,
        "profit_factor": profit_factor,
        "exposure": float((e["position_value"] > 0).mean()),
    }
