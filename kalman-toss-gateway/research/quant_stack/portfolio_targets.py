from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .portfolio import allocate


@dataclass(frozen=True)
class PortfolioTargetResult:
    targets: pd.DataFrame
    equity: pd.DataFrame
    metrics: dict[str, Any]


def _daily_equity(path: Path, sleeve: str) -> pd.Series:
    frame = pd.read_parquet(path)
    required = {"ts", "equity"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} missing columns: {sorted(missing)}")

    out = frame.copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True, errors="raise")
    out["equity"] = pd.to_numeric(out["equity"], errors="coerce")
    series = (
        out.dropna(subset=["ts", "equity"])
        .sort_values("ts")
        .drop_duplicates("ts", keep="last")
        .set_index("ts")["equity"]
        .resample("1D")
        .last()
        .ffill()
    )
    series.name = sleeve
    return series


def load_sleeve_returns(
    output_root: Path,
    markets: list[str],
) -> pd.DataFrame:
    equities: list[pd.Series] = []
    for market in markets:
        path = output_root / market.lower() / "historical_equity.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        equities.append(_daily_equity(path, market))

    panel = pd.concat(equities, axis=1).sort_index().ffill().dropna(how="any")
    if panel.empty or panel.shape[1] < 2:
        raise RuntimeError("portfolio layer requires at least two sleeves")

    returns = panel.pct_change().fillna(0.0)
    returns = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return returns


def _rebalance_dates(index: pd.DatetimeIndex, frequency: str) -> list[pd.Timestamp]:
    naive = index.tz_convert(None) if index.tz is not None else index
    if frequency.upper() == "M":
        periods = naive.to_period("M")
    elif frequency.upper() == "Q":
        periods = naive.to_period("Q")
    else:
        raise ValueError("frequency must be M or Q")

    first_mask = ~periods.duplicated()
    return [pd.Timestamp(x) for x in index[first_mask]]


def build_rolling_portfolio_targets(
    returns: pd.DataFrame,
    *,
    method: str = "hrp",
    lookback_days: int = 180,
    min_observations: int = 90,
    rebalance_frequency: str = "M",
) -> pd.DataFrame:
    if lookback_days <= 0:
        raise ValueError("lookback_days must be > 0")
    if min_observations < 20:
        raise ValueError("min_observations must be >= 20")

    frame = returns.copy().sort_index()
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index, utc=True, errors="raise"))
    frame = frame.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    rows: list[dict[str, Any]] = []
    for effective_ts in _rebalance_dates(frame.index, rebalance_frequency):
        history = frame.loc[frame.index < effective_ts].tail(lookback_days)
        if len(history) < min_observations:
            continue

        weights = allocate(history, method=method)
        if not np.isclose(float(weights.sum()), 1.0, atol=1e-8):
            raise RuntimeError("portfolio weights do not sum to 1")
        if (weights < -1e-12).any():
            raise RuntimeError("long-only portfolio produced a negative weight")

        for sleeve, weight in weights.items():
            rows.append(
                {
                    "decision_ts": history.index[-1],
                    "effective_ts": effective_ts,
                    "sleeve": str(sleeve),
                    "target_weight": float(weight),
                    "method": method,
                    "lookback_start": history.index[0],
                    "lookback_end": history.index[-1],
                    "observations": int(len(history)),
                    "source": "PYPFOPT" if method in {"hrp", "max_sharpe"} else "KALMAN",
                }
            )

    result = pd.DataFrame(rows)
    if result.empty:
        raise RuntimeError("no portfolio targets generated")
    return result.sort_values(["effective_ts", "sleeve"]).reset_index(drop=True)


def portfolio_equity_from_targets(
    returns: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    initial_equity: float = 1_000_000.0,
) -> pd.DataFrame:
    frame = returns.copy().sort_index()
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index, utc=True, errors="raise"))

    weight_rows = []
    for ts, group in targets.groupby("effective_ts"):
        row = {sleeve: 0.0 for sleeve in frame.columns}
        for item in group.itertuples(index=False):
            row[str(item.sleeve)] = float(item.target_weight)
        row["effective_ts"] = pd.Timestamp(ts)
        weight_rows.append(row)

    weight_frame = (
        pd.DataFrame(weight_rows)
        .set_index("effective_ts")
        .sort_index()
        .reindex(frame.index)
        .ffill()
    )

    # Do not use a target before its first effective timestamp.
    active = weight_frame.notna().all(axis=1)
    if not active.any():
        raise RuntimeError("portfolio targets never became active")

    active_returns = frame.loc[active, weight_frame.columns]
    active_weights = weight_frame.loc[active].fillna(0.0)
    portfolio_return = (active_returns * active_weights).sum(axis=1)

    equity = initial_equity * (1.0 + portfolio_return).cumprod()
    return pd.DataFrame(
        {
            "ts": equity.index,
            "portfolio_return": portfolio_return.to_numpy(),
            "equity": equity.to_numpy(),
        }
    )


def portfolio_metrics(equity: pd.DataFrame) -> dict[str, Any]:
    if equity.empty:
        return {}

    e = equity.copy()
    e["ts"] = pd.to_datetime(e["ts"], utc=True, errors="raise")
    e = e.sort_values("ts")
    ret = pd.to_numeric(e["portfolio_return"], errors="coerce").fillna(0.0)

    start = float(e["equity"].iloc[0])
    end = float(e["equity"].iloc[-1])
    days = max((e["ts"].iloc[-1] - e["ts"].iloc[0]).days, 1)
    years = days / 365.25
    total_return = end / start - 1.0
    cagr = (end / start) ** (1.0 / years) - 1.0 if start > 0 else np.nan
    sd = float(ret.std(ddof=0))
    sharpe = float(ret.mean() / sd * np.sqrt(365)) if sd > 0 else np.nan
    drawdown = e["equity"] / e["equity"].cummax() - 1.0

    return {
        "start": e["ts"].iloc[0],
        "end": e["ts"].iloc[-1],
        "initial_equity": start,
        "ending_equity": end,
        "total_return": float(total_return),
        "cagr": float(cagr),
        "annualized_volatility": float(sd * np.sqrt(365)),
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()),
        "observations": int(len(e)),
    }


def run_portfolio_target_layer(
    output_root: Path,
    *,
    markets: list[str],
    method: str = "hrp",
    lookback_days: int = 180,
    min_observations: int = 90,
    rebalance_frequency: str = "M",
) -> PortfolioTargetResult:
    returns = load_sleeve_returns(output_root, markets)
    targets = build_rolling_portfolio_targets(
        returns,
        method=method,
        lookback_days=lookback_days,
        min_observations=min_observations,
        rebalance_frequency=rebalance_frequency,
    )
    equity = portfolio_equity_from_targets(returns, targets)
    metrics = portfolio_metrics(equity)

    portfolio_dir = output_root / "portfolio"
    portfolio_dir.mkdir(parents=True, exist_ok=True)
    targets.to_parquet(portfolio_dir / "portfolio_target.parquet", index=False)
    equity.to_parquet(portfolio_dir / "portfolio_equity.parquet", index=False)
    (portfolio_dir / "portfolio_performance.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return PortfolioTargetResult(targets=targets, equity=equity, metrics=metrics)
