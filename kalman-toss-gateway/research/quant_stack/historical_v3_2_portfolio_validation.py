from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .historical_v2_candidate import _load_prices
from .portfolio import equal_weight, inverse_volatility, pypfopt_hrp
from .riskfolio_benchmarks import build_riskfolio_targets

MARKETS = ("US", "KR", "BTC")
PYPFOPT_METHODS = ("equal_weight", "inverse_volatility", "hrp", "max_sharpe")
RISKFOLIO_METHODS = ("cvar_minrisk", "risk_parity", "cdar_minrisk")
ALL_METHODS = PYPFOPT_METHODS + RISKFOLIO_METHODS


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def _normalize(weights: pd.Series, columns: list[str]) -> pd.Series:
    out = (
        pd.to_numeric(weights, errors="coerce")
        .reindex(columns)
        .fillna(0.0)
        .clip(lower=0.0)
    )
    total = float(out.sum())
    if total <= 0:
        raise RuntimeError("weights sum to zero")
    return out / total


def _load_v3_sleeve_returns(v3_root: Path, markets: list[str]) -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    for market in markets:
        path = v3_root / market.lower() / "strategy_100pct_equity.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        frame = pd.read_parquet(path)
        required = {"ts", "equity"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"{path} missing columns: {sorted(missing)}")

        ts = pd.to_datetime(frame["ts"], utc=True, errors="raise")
        equity = pd.Series(
            pd.to_numeric(frame["equity"], errors="coerce").to_numpy(dtype=float),
            index=ts,
            name=market,
        )
        daily = (
            equity.dropna()
            .sort_index()
            .groupby(level=0)
            .last()
            .resample("1D")
            .last()
            .ffill()
        )
        series[market] = daily

    panel = pd.concat(series, axis=1).sort_index().ffill().dropna(how="any")
    if panel.empty or panel.shape[1] < 2:
        raise RuntimeError("V3.2 validation requires at least two common sleeves")

    returns = panel.pct_change().fillna(0.0)
    returns = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    returns.attrs["annualization_days"] = 365
    return returns


def _rebalance_dates(index: pd.DatetimeIndex, frequency: str) -> list[pd.Timestamp]:
    naive = index.tz_convert(None) if index.tz is not None else index
    freq = frequency.upper()
    if freq == "M":
        periods = naive.to_period("M")
    elif freq == "Q":
        periods = naive.to_period("Q")
    else:
        raise ValueError("rebalance frequency must be M or Q")
    return [pd.Timestamp(x) for x in index[~periods.duplicated()]]


def _max_sharpe_or_min_vol(
    returns: pd.DataFrame,
    *,
    annualization_days: int,
) -> tuple[pd.Series, str, str | None]:
    from pypfopt import EfficientFrontier, expected_returns, risk_models

    clean = (
        returns.copy()
        .replace([np.inf, -np.inf], np.nan)
        .dropna(how="all")
        .fillna(0.0)
    )
    columns = [str(x) for x in clean.columns]
    if clean.empty:
        return equal_weight(returns), "FALLBACK_EQUAL_WEIGHT", "empty lookback"

    prices = (1.0 + clean).cumprod()
    mu = expected_returns.mean_historical_return(
        prices,
        frequency=annualization_days,
    )
    cov = risk_models.CovarianceShrinkage(
        prices,
        frequency=annualization_days,
    ).ledoit_wolf()

    try:
        if not np.isfinite(mu.to_numpy(dtype=float)).all():
            raise ValueError("non-finite expected returns")
        if float(mu.max()) <= 0.0:
            raise ValueError("no asset has positive expected return")

        ef = EfficientFrontier(mu, cov, weight_bounds=(0.0, 1.0))
        ef.max_sharpe(risk_free_rate=0.0)
        weights = _normalize(
            pd.Series(ef.clean_weights(), dtype=float),
            columns,
        )
        return weights, "READY", None
    except Exception as exc:
        try:
            ef = EfficientFrontier(mu.fillna(0.0), cov, weight_bounds=(0.0, 1.0))
            ef.min_volatility()
            weights = _normalize(
                pd.Series(ef.clean_weights(), dtype=float),
                columns,
            )
            return weights, "FALLBACK_MIN_VOL", f"{type(exc).__name__}: {exc}"
        except Exception as fallback_exc:
            weights = inverse_volatility(clean)
            return (
                _normalize(weights, columns),
                "FALLBACK_INVERSE_VOL",
                (
                    f"max_sharpe={type(exc).__name__}: {exc}; "
                    f"min_vol={type(fallback_exc).__name__}: {fallback_exc}"
                ),
            )


def _allocator(
    history: pd.DataFrame,
    *,
    method: str,
    annualization_days: int,
) -> tuple[pd.Series, str, str | None]:
    method = method.lower()
    columns = [str(x) for x in history.columns]
    if method == "equal_weight":
        return _normalize(equal_weight(history), columns), "READY", None
    if method == "inverse_volatility":
        return _normalize(inverse_volatility(history), columns), "READY", None
    if method == "hrp":
        return _normalize(pypfopt_hrp(history), columns), "READY", None
    if method == "max_sharpe":
        return _max_sharpe_or_min_vol(
            history,
            annualization_days=annualization_days,
        )
    raise ValueError(f"unsupported allocation method: {method}")


def build_pypfopt_targets_v32(
    returns: pd.DataFrame,
    *,
    method: str,
    lookback_days: int,
    min_observations: int,
    rebalance_frequency: str,
    annualization_days: int = 365,
) -> pd.DataFrame:
    frame = returns.copy().sort_index()
    frame.index = pd.DatetimeIndex(
        pd.to_datetime(frame.index, utc=True, errors="raise")
    )
    rows: list[dict[str, Any]] = []

    for effective_ts in _rebalance_dates(frame.index, rebalance_frequency):
        history = frame.loc[frame.index < effective_ts].tail(lookback_days)
        if len(history) < min_observations:
            continue

        weights, optimization_status, fallback_reason = _allocator(
            history,
            method=method,
            annualization_days=annualization_days,
        )
        if not np.isclose(float(weights.sum()), 1.0, atol=1e-8):
            raise RuntimeError(f"{method}: weights do not sum to one")
        if (weights < -1e-12).any():
            raise RuntimeError(f"{method}: negative long-only weight")

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
                    "source": (
                        "PYPFOPT"
                        if method in {"hrp", "max_sharpe"}
                        else "KALMAN"
                    ),
                    "optimization_status": optimization_status,
                    "fallback_reason": fallback_reason,
                    "annualization_days": annualization_days,
                }
            )

    result = pd.DataFrame(rows)
    if result.empty:
        raise RuntimeError(f"{method}: no portfolio targets generated")
    return result.sort_values(["effective_ts", "sleeve"]).reset_index(drop=True)


def portfolio_equity_with_costs(
    returns: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    initial_equity: float = 1_000_000.0,
    rebalance_cost_bps: float = 10.0,
    charge_initial_allocation: bool = True,
) -> pd.DataFrame:
    frame = returns.copy().sort_index()
    frame.index = pd.DatetimeIndex(
        pd.to_datetime(frame.index, utc=True, errors="raise")
    )

    weight_rows: list[dict[str, Any]] = []
    for ts, group in targets.groupby("effective_ts"):
        row: dict[str, Any] = {str(sleeve): 0.0 for sleeve in frame.columns}
        for item in group.itertuples(index=False):
            row[str(item.sleeve)] = float(item.target_weight)
        row["effective_ts"] = pd.Timestamp(ts)
        weight_rows.append(row)

    if not weight_rows:
        raise RuntimeError("no portfolio weights")

    target_weights = (
        pd.DataFrame(weight_rows)
        .set_index("effective_ts")
        .sort_index()
        .reindex(columns=frame.columns)
    )
    weight_frame = target_weights.reindex(frame.index).ffill()
    active = weight_frame.notna().all(axis=1)
    if not active.any():
        raise RuntimeError("portfolio targets never became active")

    frame = frame.loc[active, weight_frame.columns]
    weight_frame = weight_frame.loc[active].fillna(0.0)

    effective_set = set(pd.DatetimeIndex(target_weights.index))
    previous_target = pd.Series(0.0, index=weight_frame.columns, dtype=float)
    current_equity = float(initial_equity)
    fee_rate = float(rebalance_cost_bps) / 10_000.0
    rows: list[dict[str, Any]] = []

    for ts in frame.index:
        weights = weight_frame.loc[ts].astype(float)
        gross_return = float((frame.loc[ts] * weights).sum())

        half_l1_turnover = 0.0
        traded_notional_ratio = 0.0
        rebalance_cost_rate = 0.0
        is_rebalance = ts in effective_set

        if is_rebalance:
            delta = weights - previous_target
            l1 = float(np.abs(delta).sum())
            if previous_target.abs().sum() <= 1e-12 and not charge_initial_allocation:
                l1 = 0.0
            traded_notional_ratio = l1
            half_l1_turnover = 0.5 * l1
            rebalance_cost_rate = traded_notional_ratio * fee_rate
            previous_target = weights.copy()

        net_return = (1.0 - rebalance_cost_rate) * (1.0 + gross_return) - 1.0
        current_equity *= 1.0 + net_return
        rows.append(
            {
                "ts": ts,
                "gross_portfolio_return": gross_return,
                "rebalance_cost_rate": rebalance_cost_rate,
                "net_portfolio_return": net_return,
                "half_l1_turnover": half_l1_turnover,
                "traded_notional_ratio": traded_notional_ratio,
                "equity": current_equity,
                "is_rebalance": is_rebalance,
            }
        )

    return pd.DataFrame(rows)


def corrected_portfolio_metrics(
    equity: pd.DataFrame,
    *,
    initial_equity: float = 1_000_000.0,
    annualization_days: int = 365,
) -> dict[str, Any]:
    if equity.empty:
        return {}

    e = equity.copy()
    e["ts"] = pd.to_datetime(e["ts"], utc=True, errors="raise")
    e = e.sort_values("ts").reset_index(drop=True)

    net = pd.to_numeric(
        e["net_portfolio_return"], errors="coerce"
    ).fillna(0.0)
    gross = pd.to_numeric(
        e["gross_portfolio_return"], errors="coerce"
    ).fillna(0.0)

    ending_equity = float(e["equity"].iloc[-1])
    total_return = ending_equity / float(initial_equity) - 1.0
    start_ts = pd.Timestamp(e["ts"].iloc[0])
    end_ts = pd.Timestamp(e["ts"].iloc[-1])
    days = max((end_ts - start_ts).days + 1, 1)
    years = days / 365.25
    cagr = (
        (ending_equity / float(initial_equity)) ** (1.0 / years) - 1.0
        if initial_equity > 0
        else np.nan
    )

    sd = float(net.std(ddof=0))
    sharpe = (
        float(net.mean() / sd * np.sqrt(annualization_days))
        if sd > 0
        else np.nan
    )

    augmented = pd.concat(
        [
            pd.Series([float(initial_equity)]),
            pd.to_numeric(e["equity"], errors="coerce").reset_index(drop=True),
        ],
        ignore_index=True,
    )
    drawdown = augmented / augmented.cummax() - 1.0

    cvar = None
    values = net.dropna().to_numpy(dtype=float)
    if len(values) >= 20:
        cutoff = np.quantile(values, 0.05)
        tail = values[values <= cutoff]
        if len(tail):
            cvar = float(-np.mean(tail))

    return {
        "start": start_ts,
        "end": end_ts,
        "initial_equity": float(initial_equity),
        "ending_equity": ending_equity,
        "total_return": float(total_return),
        "cagr": float(cagr),
        "annualized_volatility": float(sd * np.sqrt(annualization_days)),
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()),
        "historical_cvar_95": cvar,
        "gross_total_return": float((1.0 + gross).prod() - 1.0),
        "net_total_return": float((1.0 + net).prod() - 1.0),
        "rebalance_count": int(e["is_rebalance"].sum()),
        "half_l1_turnover_total": float(
            pd.to_numeric(e["half_l1_turnover"], errors="coerce").fillna(0.0).sum()
        ),
        "traded_notional_ratio_total": float(
            pd.to_numeric(e["traded_notional_ratio"], errors="coerce").fillna(0.0).sum()
        ),
        "rebalance_cost_rate_total": float(
            pd.to_numeric(e["rebalance_cost_rate"], errors="coerce").fillna(0.0).sum()
        ),
        "observations": int(len(e)),
        "annualization_days": int(annualization_days),
    }


def _method_row(
    *,
    method: str,
    source: str,
    status: str,
    metrics: dict[str, Any] | None,
    fallback_rebalances: int = 0,
    target_rebalances: int = 0,
    note: str | None = None,
) -> dict[str, Any]:
    metrics = metrics or {}
    fallback_ratio = (
        fallback_rebalances / target_rebalances
        if target_rebalances > 0
        else 0.0
    )
    champion_eligible = (
        status == "READY"
        and fallback_ratio <= 0.25
        and metrics.get("sharpe") is not None
    )
    return {
        "status": status,
        "method": method,
        "source": source,
        "total_return": metrics.get("total_return"),
        "gross_total_return": metrics.get("gross_total_return"),
        "cagr": metrics.get("cagr"),
        "sharpe": metrics.get("sharpe"),
        "max_drawdown": metrics.get("max_drawdown"),
        "annualized_volatility": metrics.get("annualized_volatility"),
        "historical_cvar_95": metrics.get("historical_cvar_95"),
        "rebalance_count": metrics.get("rebalance_count"),
        "half_l1_turnover_total": metrics.get("half_l1_turnover_total"),
        "traded_notional_ratio_total": metrics.get("traded_notional_ratio_total"),
        "rebalance_cost_rate_total": metrics.get("rebalance_cost_rate_total"),
        "fallback_rebalance_count": int(fallback_rebalances),
        "fallback_ratio": float(fallback_ratio),
        "champion_eligible": bool(champion_eligible),
        "note": note,
    }


def run_portfolio_tournament(
    returns: pd.DataFrame,
    output_root: Path,
    *,
    lookback_days: int,
    min_observations: int,
    rebalance_frequency: str,
    annualization_days: int,
    rebalance_cost_bps: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for method in PYPFOPT_METHODS:
        source = "PYPFOPT" if method in {"hrp", "max_sharpe"} else "KALMAN"
        root = output_root / "portfolio" / method
        root.mkdir(parents=True, exist_ok=True)
        try:
            targets = build_pypfopt_targets_v32(
                returns,
                method=method,
                lookback_days=lookback_days,
                min_observations=min_observations,
                rebalance_frequency=rebalance_frequency,
                annualization_days=annualization_days,
            )
            equity = portfolio_equity_with_costs(
                returns,
                targets,
                rebalance_cost_bps=rebalance_cost_bps,
            )
            metrics = corrected_portfolio_metrics(
                equity,
                annualization_days=annualization_days,
            )
            fallback_count = int(
                targets.loc[
                    targets["optimization_status"] != "READY",
                    "effective_ts",
                ].nunique()
            )
            target_rebalances = int(targets["effective_ts"].nunique())

            targets.to_parquet(root / "portfolio_target.parquet", index=False)
            equity.to_parquet(root / "portfolio_equity.parquet", index=False)
            _write_json(
                root / "portfolio_performance.json",
                {
                    **metrics,
                    "method": method,
                    "source": source,
                    "fallback_rebalance_count": fallback_count,
                    "target_rebalance_count": target_rebalances,
                },
            )
            rows.append(
                _method_row(
                    method=method,
                    source=source,
                    status="READY",
                    metrics=metrics,
                    fallback_rebalances=fallback_count,
                    target_rebalances=target_rebalances,
                )
            )
        except Exception as exc:
            _write_json(
                root / "failure.json",
                {
                    "status": "FAIL",
                    "method": method,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            rows.append(
                _method_row(
                    method=method,
                    source=source,
                    status="FAIL",
                    metrics=None,
                    note=f"{type(exc).__name__}: {exc}",
                )
            )

    for method in RISKFOLIO_METHODS:
        root = output_root / "riskfolio" / method
        root.mkdir(parents=True, exist_ok=True)
        try:
            targets = build_riskfolio_targets(
                returns,
                method=method,
                lookback_days=lookback_days,
                min_observations=min_observations,
                rebalance_frequency=rebalance_frequency,
            )
            equity = portfolio_equity_with_costs(
                returns,
                targets,
                rebalance_cost_bps=rebalance_cost_bps,
            )
            metrics = corrected_portfolio_metrics(
                equity,
                annualization_days=annualization_days,
            )
            fallback_count = int(
                targets.loc[
                    targets["optimization_status"] != "READY",
                    "effective_ts",
                ].nunique()
            )
            target_rebalances = int(targets["effective_ts"].nunique())

            targets.to_parquet(root / "portfolio_target.parquet", index=False)
            equity.to_parquet(root / "portfolio_equity.parquet", index=False)
            _write_json(
                root / "portfolio_performance.json",
                {
                    **metrics,
                    "method": method,
                    "source": "RISKFOLIO",
                    "fallback_rebalance_count": fallback_count,
                    "target_rebalance_count": target_rebalances,
                },
            )
            rows.append(
                _method_row(
                    method=method,
                    source="RISKFOLIO",
                    status="READY",
                    metrics=metrics,
                    fallback_rebalances=fallback_count,
                    target_rebalances=target_rebalances,
                )
            )
        except Exception as exc:
            _write_json(
                root / "failure.json",
                {
                    "status": "FAIL",
                    "method": method,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            rows.append(
                _method_row(
                    method=method,
                    source="RISKFOLIO",
                    status="FAIL",
                    metrics=None,
                    note=f"{type(exc).__name__}: {exc}",
                )
            )

    return rows


def _map_signals_to_next_bar(
    signals: pd.DataFrame,
    bars: pd.DataFrame,
) -> dict[int, list[str]]:
    ts = pd.DatetimeIndex(bars["ts"])
    mapped: dict[int, list[str]] = {}
    for row in signals.sort_values("signal_ts").itertuples(index=False):
        signal_ts = pd.Timestamp(row.signal_ts)
        i = int(ts.searchsorted(signal_ts, side="right"))
        if i >= len(ts):
            continue
        mapped.setdefault(i, []).append(str(row.signal).upper().strip())
    return mapped


def _stateful_vectorbt_orders(
    event_map: dict[int, list[str]],
    bars: pd.DataFrame,
    *,
    max_hold_bars: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str | None]]:
    n = len(bars)
    entries = np.zeros(n, dtype=bool)
    exits = np.zeros(n, dtype=bool)
    execution_price = pd.to_numeric(
        bars["open"], errors="coerce"
    ).to_numpy(dtype=float)
    reasons: list[str | None] = [None] * n

    in_position = False
    bars_held = 0

    for i in range(n):
        actions = event_map.get(i, [])

        if in_position and any(action in {"SELL", "EXIT", "CLOSE", "-1"} for action in actions):
            exits[i] = True
            execution_price[i] = float(bars.iloc[i]["open"])
            reasons[i] = "SELL_SIGNAL_NEXT_OPEN"
            in_position = False
            bars_held = 0

        if (not in_position) and any(action in {"BUY", "LONG", "ENTER", "1"} for action in actions):
            entries[i] = True
            execution_price[i] = float(bars.iloc[i]["open"])
            reasons[i] = (
                f"{reasons[i]}+BUY_NEXT_OPEN"
                if reasons[i]
                else "BUY_NEXT_OPEN"
            )
            in_position = True
            bars_held = 0

        if in_position:
            bars_held += 1
            if bars_held >= max_hold_bars:
                exits[i] = True
                execution_price[i] = float(bars.iloc[i]["close"])
                reasons[i] = (
                    f"{reasons[i]}+MAX_HOLD_CLOSE"
                    if reasons[i]
                    else "MAX_HOLD_CLOSE"
                )
                in_position = False
                bars_held = 0

    return entries, exits, execution_price, reasons


def _scalar(value: Any) -> float | int | None:
    if hasattr(value, "item"):
        value = value.item()
    number = _safe_float(value)
    if number is None:
        return None
    if float(number).is_integer():
        return int(number)
    return float(number)


def _vectorbt_metrics(pf: Any) -> dict[str, Any]:
    value = pf.value()
    return {
        "total_return": _scalar(pf.total_return()),
        "sharpe": _scalar(pf.sharpe_ratio()),
        "max_drawdown": _scalar(pf.max_drawdown()),
        "trade_count": _scalar(pf.trades.count()),
        "ending_value": _scalar(value.iloc[-1] if len(value) else np.nan),
    }


def validate_vectorbt_market_v32(
    *,
    market: str,
    v3_root: Path,
    matrix_dir: Path,
    spec: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    import vectorbt as vbt

    market_spec = spec["markets"][market]
    symbol = str(market_spec["symbol"])
    max_hold_bars = int(market_spec.get("max_hold_bars", 20))

    signals = pd.read_parquet(
        v3_root / market.lower() / "historical_strategy_signal.parquet"
    )
    signals["signal_ts"] = pd.to_datetime(
        signals["signal_ts"], utc=True, errors="raise"
    )

    prices = _load_prices(matrix_dir, market, symbol)
    prices = prices.loc[prices["ts"] >= signals["signal_ts"].min()].copy()
    prices = (
        prices.sort_values("ts")
        .drop_duplicates("ts", keep="last")
        .reset_index(drop=True)
    )
    if prices.empty:
        raise RuntimeError(f"{market}: no prices for vectorbt validation")

    event_map = _map_signals_to_next_bar(signals, prices)
    entries, exits, execution_price, reasons = _stateful_vectorbt_orders(
        event_map,
        prices,
        max_hold_bars=max_hold_bars,
    )

    index = pd.DatetimeIndex(prices["ts"])
    close_series = pd.Series(
        pd.to_numeric(prices["close"], errors="coerce").to_numpy(dtype=float),
        index=index,
    )
    exec_series = pd.Series(execution_price, index=index)

    pf = vbt.Portfolio.from_signals(
        close_series,
        pd.Series(entries, index=index),
        pd.Series(exits, index=index),
        price=exec_series,
        init_cash=1_000_000.0,
        size=0.10,
        size_type="percent",
        fees=0.0005,
        slippage=0.0005,
        freq="1D",
    )

    native_summary = _load_json(
        v3_root / market.lower() / "candidate_summary.json"
    )
    native = (
        native_summary
        .get("backtests", {})
        .get("10pct", {})
        .get("strategy", {})
    )
    vector_metrics = _vectorbt_metrics(pf)

    native_return = _safe_float(native.get("total_return"))
    vector_return = _safe_float(vector_metrics.get("total_return"))
    gap = (
        float(vector_return - native_return)
        if native_return is not None and vector_return is not None
        else None
    )
    abs_gap = abs(gap) if gap is not None else None
    parity = (
        "PASS"
        if abs_gap is not None and abs_gap <= 0.001
        else "WARN"
        if abs_gap is not None and abs_gap <= 0.005
        else "FAIL"
    )

    order_audit = pd.DataFrame(
        {
            "ts": index,
            "entry": entries,
            "exit": exits,
            "execution_price": execution_price,
            "reason": reasons,
        }
    )
    order_audit = order_audit.loc[
        order_audit["entry"] | order_audit["exit"]
    ].reset_index(drop=True)
    out_dir = output_root / "vectorbt"
    out_dir.mkdir(parents=True, exist_ok=True)
    order_audit.to_parquet(
        out_dir / f"{market.lower()}_order_audit.parquet",
        index=False,
    )

    result = {
        "status": "READY",
        "market": market,
        "validator": "VECTORBT_1_1_0",
        "scope": "V3_SIGNAL_NEXT_BAR_10PCT_MIXED_PRICE_REPLAY",
        "execution_semantics": {
            "BUY": "NEXT_BAR_OPEN",
            "SELL_SIGNAL": "NEXT_BAR_OPEN",
            "MAX_HOLD": "CURRENT_BAR_CLOSE",
        },
        "position_fraction": 0.10,
        "commission_bps": 5.0,
        "slippage_bps": 5.0,
        "max_hold_bars": max_hold_bars,
        "entry_count": int(entries.sum()),
        "exit_count": int(exits.sum()),
        "native_metrics": native,
        "vectorbt_metrics": vector_metrics,
        "vectorbt_minus_native_total_return": gap,
        "absolute_total_return_gap": abs_gap,
        "parity_status": parity,
        "note": (
            "Execution-price parity improved to match Kalman max-hold close exits. "
            "Remaining gap can reflect vectorbt percent-sizing/accounting semantics. "
            "Kalman native ledger remains authoritative."
        ),
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _write_json(
        out_dir / f"{market.lower()}_validation.json",
        result,
    )
    return result


def run_vectorbt_validation_v32(
    *,
    v3_root: Path,
    matrix_dir: Path,
    spec: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for market in MARKETS:
        try:
            results[market] = validate_vectorbt_market_v32(
                market=market,
                v3_root=v3_root,
                matrix_dir=matrix_dir,
                spec=spec,
                output_root=output_root,
            )
        except Exception as exc:
            results[market] = {
                "status": "FAIL",
                "market": market,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "parity_status": "FAIL",
            }
            _write_json(
                output_root / "vectorbt" / f"{market.lower()}_validation.json",
                results[market],
            )

    ready = [m for m, item in results.items() if item.get("status") == "READY"]
    parity_fail = [
        m for m, item in results.items()
        if item.get("parity_status") == "FAIL"
    ]
    status = (
        "READY"
        if len(ready) == len(MARKETS) and not parity_fail
        else "DEGRADED"
        if ready
        else "FAIL"
    )
    summary = {
        "status": status,
        "ready_markets": ready,
        "parity_fail_markets": parity_fail,
        "markets": results,
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _write_json(
        output_root / "vectorbt" / "vectorbt_validation_summary.json",
        summary,
    )
    return summary


def select_champions(comparison: pd.DataFrame) -> dict[str, Any]:
    ready = comparison.loc[
        (comparison["status"] == "READY")
        & (comparison["champion_eligible"] == True)  # noqa: E712
    ].copy()
    if ready.empty:
        return {
            "overall_champion": None,
            "growth_champion": None,
            "balanced_champion": None,
            "defensive_champion": None,
        }

    for col in (
        "sharpe",
        "cagr",
        "max_drawdown",
        "annualized_volatility",
        "historical_cvar_95",
    ):
        ready[col] = pd.to_numeric(ready[col], errors="coerce")

    overall = (
        ready.sort_values(
            ["sharpe", "cagr", "max_drawdown"],
            ascending=[False, False, False],
        )
        .iloc[0]
        .to_dict()
    )

    growth = (
        ready.sort_values(
            ["cagr", "sharpe", "max_drawdown"],
            ascending=[False, False, False],
        )
        .iloc[0]
        .to_dict()
    )

    best_sharpe = float(ready["sharpe"].max())
    balanced_pool = ready.loc[
        ready["sharpe"] >= best_sharpe * 0.95
    ].copy()
    balanced = (
        balanced_pool.sort_values(
            ["annualized_volatility", "max_drawdown", "cagr"],
            ascending=[True, False, False],
        )
        .iloc[0]
        .to_dict()
    )

    defensive = (
        ready.sort_values(
            ["max_drawdown", "historical_cvar_95", "annualized_volatility"],
            ascending=[False, True, True],
        )
        .iloc[0]
        .to_dict()
    )

    return {
        "overall_champion": overall,
        "growth_champion": growth,
        "balanced_champion": balanced,
        "defensive_champion": defensive,
        "balanced_rule": (
            "Among methods with Sharpe >= 95% of best eligible Sharpe, "
            "choose lowest annualized volatility, then shallower max drawdown, "
            "then higher CAGR."
        ),
        "defensive_rule": (
            "Choose shallowest max drawdown, then lowest historical CVaR95, "
            "then lowest annualized volatility."
        ),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Kalman V3.2 corrected portfolio/risk validation"
    )
    p.add_argument("--v3-root", required=True)
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--code-sha", required=True)
    p.add_argument("--lookback-days", type=int, default=180)
    p.add_argument("--min-observations", type=int, default=90)
    p.add_argument("--rebalance", choices=["M", "Q"], default="M")
    p.add_argument("--annualization-days", type=int, default=365)
    p.add_argument("--rebalance-cost-bps", type=float, default=10.0)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    v3_root = Path(args.v3_root).expanduser()
    matrix_dir = Path(args.matrix_dir).expanduser()
    output_root = Path(args.output_dir).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)

    final_v3 = _load_json(v3_root / "historical_v3_candidate_summary.json")
    if final_v3.get("status") != "COMPLETE":
        raise RuntimeError(
            f"V3 source is not COMPLETE: {final_v3.get('status')}"
        )

    candidate = _load_json(v3_root / "candidate_run_status.json")
    ready_markets = [
        market
        for market in MARKETS
        if candidate.get("markets", {}).get(market, {}).get("status") == "READY"
    ]
    if len(ready_markets) < 2:
        raise RuntimeError(f"fewer than two READY V3 markets: {ready_markets}")

    spec = _load_json(Path(args.spec).expanduser())
    returns = _load_v3_sleeve_returns(v3_root, ready_markets)

    rows = run_portfolio_tournament(
        returns,
        output_root,
        lookback_days=args.lookback_days,
        min_observations=args.min_observations,
        rebalance_frequency=args.rebalance,
        annualization_days=args.annualization_days,
        rebalance_cost_bps=args.rebalance_cost_bps,
    )
    comparison = pd.DataFrame(rows)
    comparison.to_csv(
        output_root / "v3_2_tournament_comparison.csv",
        index=False,
    )

    eligible = comparison.loc[
        (comparison["status"] == "READY")
        & (comparison["champion_eligible"] == True)  # noqa: E712
    ].copy()
    if not eligible.empty:
        eligible = eligible.sort_values(
            ["sharpe", "cagr", "max_drawdown"],
            ascending=[False, False, False],
        ).reset_index(drop=True)
        eligible.insert(0, "rank", np.arange(1, len(eligible) + 1))
    eligible.to_csv(
        output_root / "v3_2_eligible_ranking.csv",
        index=False,
    )

    champions = select_champions(comparison)
    vectorbt = run_vectorbt_validation_v32(
        v3_root=v3_root,
        matrix_dir=matrix_dir,
        spec=spec,
        output_root=output_root,
    )

    method_failures = comparison.loc[
        comparison["status"] != "READY", "method"
    ].astype(str).tolist()
    ineligible = comparison.loc[
        ~comparison["champion_eligible"].astype(bool), "method"
    ].astype(str).tolist()

    experiment_status = (
        "READY"
        if not method_failures and vectorbt.get("status") == "READY"
        else "DEGRADED"
    )
    summary = {
        "status": "COMPLETE",
        "experiment_status": experiment_status,
        "experiment": "V3_2_PORTFOLIO_VALIDATION",
        "code_sha": args.code_sha,
        "source_v3_root": str(v3_root),
        "ready_markets": ready_markets,
        "configuration": {
            "lookback_days": args.lookback_days,
            "min_observations": args.min_observations,
            "rebalance_frequency": args.rebalance,
            "annualization_days": args.annualization_days,
            "rebalance_cost_bps_per_traded_notional": args.rebalance_cost_bps,
            "charge_initial_allocation": True,
            "position_source": "V3 strategy_100pct_equity",
        },
        "corrections_vs_v3_1": [
            "initial equity fixed at 1,000,000 for return/CAGR/drawdown metrics",
            "portfolio overlay rebalance turnover and transaction cost applied",
            "365-day annualization used consistently for calendar-daily US/KR/BTC panel",
            "Max Sharpe uses 365-day expected return/covariance and per-rebalance fallback",
            "vectorbt replay uses next-open signal fills and close max-hold exits",
            "champions split into overall/growth/balanced/defensive roles",
            "experiment_status reports DEGRADED when method or parity checks fail",
        ],
        "method_failures": method_failures,
        "champion_ineligible_methods": ineligible,
        "champions": champions,
        "vectorbt": vectorbt,
        "research_only": True,
        "promotion_recommendation": "RESEARCH_ONLY",
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _write_json(
        output_root / "v3_2_validation_summary.json",
        summary,
    )

    print("\nKALMAN V3.2 PORTFOLIO VALIDATION COMPLETE")
    print(output_root / "v3_2_validation_summary.json")
    print("\nEXPERIMENT STATUS:", experiment_status)
    print("\nCHAMPIONS")
    print(json.dumps(champions, ensure_ascii=False, indent=2, default=str))
    print("\nELIGIBLE RANKING")
    if not eligible.empty:
        print(eligible.to_string(index=False))
    else:
        print("No eligible methods")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
