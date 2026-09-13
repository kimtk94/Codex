from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .historical_v2_candidate import _load_prices
from .portfolio_targets import (
    build_rolling_portfolio_targets,
    portfolio_equity_from_targets,
    portfolio_metrics,
)
from .riskfolio_benchmarks import build_riskfolio_targets

MARKETS = ("US", "KR", "BTC")
PYPFOPT_METHODS = ("equal_weight", "inverse_volatility", "hrp", "max_sharpe")
RISKFOLIO_METHODS = ("cvar_minrisk", "risk_parity", "cdar_minrisk")


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


def _historical_cvar_95(portfolio_return: pd.Series) -> float | None:
    values = pd.to_numeric(portfolio_return, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) < 20:
        return None
    cutoff = np.quantile(values, 0.05)
    tail = values[values <= cutoff]
    if not len(tail):
        return None
    return float(-np.mean(tail))


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
        raise RuntimeError("V3.1 tournament requires at least two common sleeves")
    returns = panel.pct_change().fillna(0.0)
    return returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _performance_row(
    *,
    method: str,
    source: str,
    metrics: dict[str, Any],
    rebalance_count: int | None,
    status: str = "READY",
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "method": method,
        "source": source,
        "total_return": metrics.get("total_return"),
        "cagr": metrics.get("cagr"),
        "sharpe": metrics.get("sharpe"),
        "max_drawdown": metrics.get("max_drawdown"),
        "annualized_volatility": metrics.get("annualized_volatility"),
        "historical_cvar_95": metrics.get("historical_cvar_95"),
        "rebalance_count": rebalance_count,
        "note": note,
    }


def run_pypfopt_tournament(
    returns: pd.DataFrame,
    output_root: Path,
    *,
    lookback_days: int,
    min_observations: int,
    rebalance_frequency: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = output_root / "portfolio"
    root.mkdir(parents=True, exist_ok=True)

    for method in PYPFOPT_METHODS:
        method_root = root / method
        method_root.mkdir(parents=True, exist_ok=True)
        try:
            targets = build_rolling_portfolio_targets(
                returns,
                method=method,
                lookback_days=lookback_days,
                min_observations=min_observations,
                rebalance_frequency=rebalance_frequency,
            )
            equity = portfolio_equity_from_targets(returns, targets)
            metrics = portfolio_metrics(equity)
            metrics["historical_cvar_95"] = _historical_cvar_95(
                equity["portfolio_return"]
            )

            targets.to_parquet(method_root / "portfolio_target.parquet", index=False)
            equity.to_parquet(method_root / "portfolio_equity.parquet", index=False)
            _write_json(method_root / "portfolio_performance.json", metrics)
            rows.append(
                _performance_row(
                    method=method,
                    source=("PYPFOPT" if method in {"hrp", "max_sharpe"} else "KALMAN"),
                    metrics=metrics,
                    rebalance_count=int(targets["effective_ts"].nunique()),
                )
            )
        except Exception as exc:
            payload = {
                "status": "FAIL",
                "method": method,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            _write_json(method_root / "failure.json", payload)
            rows.append(
                _performance_row(
                    method=method,
                    source=("PYPFOPT" if method in {"hrp", "max_sharpe"} else "KALMAN"),
                    metrics={},
                    rebalance_count=None,
                    status="FAIL",
                    note=f"{type(exc).__name__}: {exc}",
                )
            )
    return rows


def run_riskfolio_tournament(
    returns: pd.DataFrame,
    output_root: Path,
    *,
    lookback_days: int,
    min_observations: int,
    rebalance_frequency: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = output_root / "riskfolio"
    root.mkdir(parents=True, exist_ok=True)

    for method in RISKFOLIO_METHODS:
        method_root = root / method
        method_root.mkdir(parents=True, exist_ok=True)
        try:
            targets = build_riskfolio_targets(
                returns,
                method=method,
                lookback_days=lookback_days,
                min_observations=min_observations,
                rebalance_frequency=rebalance_frequency,
            )
            equity = portfolio_equity_from_targets(returns, targets)
            metrics = portfolio_metrics(equity)
            metrics["historical_cvar_95"] = _historical_cvar_95(
                equity["portfolio_return"]
            )
            fallback_count = int(
                targets.loc[
                    targets["optimization_status"] == "FALLBACK", "effective_ts"
                ].nunique()
            )

            targets.to_parquet(method_root / "portfolio_target.parquet", index=False)
            equity.to_parquet(method_root / "portfolio_equity.parquet", index=False)
            _write_json(
                method_root / "portfolio_performance.json",
                {
                    **metrics,
                    "fallback_rebalance_count": fallback_count,
                },
            )
            rows.append(
                _performance_row(
                    method=method,
                    source="RISKFOLIO",
                    metrics=metrics,
                    rebalance_count=int(targets["effective_ts"].nunique()),
                    note=(
                        f"fallback_rebalances={fallback_count}"
                        if fallback_count
                        else None
                    ),
                )
            )
        except Exception as exc:
            payload = {
                "status": "FAIL",
                "method": method,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            _write_json(method_root / "failure.json", payload)
            rows.append(
                _performance_row(
                    method=method,
                    source="RISKFOLIO",
                    metrics={},
                    rebalance_count=None,
                    status="FAIL",
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


def _stateful_entry_exit_arrays(
    event_map: dict[int, list[str]],
    n: int,
    *,
    max_hold_bars: int,
) -> tuple[np.ndarray, np.ndarray]:
    entries = np.zeros(n, dtype=bool)
    exits = np.zeros(n, dtype=bool)
    in_position = False
    bars_held = 0

    for i in range(n):
        actions = event_map.get(i, [])

        if in_position and any(action == "SELL" for action in actions):
            exits[i] = True
            in_position = False
            bars_held = 0

        if (not in_position) and any(action == "BUY" for action in actions):
            entries[i] = True
            in_position = True
            bars_held = 0

        if in_position:
            bars_held += 1
            if bars_held >= max_hold_bars:
                exits[i] = True
                in_position = False
                bars_held = 0

    return entries, exits


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


def validate_vectorbt_market(
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
    prices = prices.sort_values("ts").drop_duplicates("ts", keep="last").reset_index(drop=True)
    if prices.empty:
        raise RuntimeError(f"{market}: no prices for vectorbt validation")

    event_map = _map_signals_to_next_bar(signals, prices)
    entries, exits = _stateful_entry_exit_arrays(
        event_map,
        len(prices),
        max_hold_bars=max_hold_bars,
    )

    index = pd.DatetimeIndex(prices["ts"])
    execution_price = pd.Series(
        pd.to_numeric(prices["open"], errors="coerce").to_numpy(dtype=float),
        index=index,
    )

    pf = vbt.Portfolio.from_signals(
        execution_price,
        pd.Series(entries, index=index),
        pd.Series(exits, index=index),
        init_cash=1_000_000.0,
        size=0.10,
        size_type="percent",
        fees=0.0005,
        slippage=0.0005,
        freq="1D",
    )
    benchmark = vbt.Portfolio.from_holding(
        execution_price,
        init_cash=1_000_000.0,
        fees=0.0005,
        slippage=0.0005,
        freq="1D",
    )

    native_summary = _load_json(v3_root / market.lower() / "candidate_summary.json")
    native = native_summary.get("backtests", {}).get("10pct", {}).get("strategy", {})
    vector_metrics = _vectorbt_metrics(pf)
    benchmark_metrics = _vectorbt_metrics(benchmark)

    native_return = _safe_float(native.get("total_return"))
    vector_return = _safe_float(vector_metrics.get("total_return"))
    gap = (
        float(vector_return - native_return)
        if native_return is not None and vector_return is not None
        else None
    )

    result = {
        "status": "READY",
        "market": market,
        "validator": "VECTORBT_1_1_0",
        "scope": "V3_SIGNAL_NEXT_BAR_10PCT_REPLAY",
        "execution_price": "NEXT_BAR_OPEN",
        "position_fraction": 0.10,
        "commission_bps": 5.0,
        "slippage_bps": 5.0,
        "max_hold_bars": max_hold_bars,
        "entry_count": int(entries.sum()),
        "exit_count": int(exits.sum()),
        "mapped_event_bars": int(len(event_map)),
        "native_metrics": native,
        "vectorbt_metrics": vector_metrics,
        "buy_hold_metrics": benchmark_metrics,
        "vectorbt_minus_native_total_return": gap,
        "note": (
            "Independent cross-check only. Kalman native ledger remains authoritative; "
            "vectorbt percent sizing semantics can differ slightly."
        ),
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _write_json(output_root / "vectorbt" / f"{market.lower()}_validation.json", result)
    return result


def run_vectorbt_validation(
    *,
    v3_root: Path,
    matrix_dir: Path,
    spec: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for market in MARKETS:
        try:
            results[market] = validate_vectorbt_market(
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
            }
            _write_json(
                output_root / "vectorbt" / f"{market.lower()}_validation.json",
                results[market],
            )

    ready = [m for m, item in results.items() if item.get("status") == "READY"]
    summary = {
        "status": "READY" if len(ready) == len(MARKETS) else "DEGRADED",
        "ready_markets": ready,
        "markets": results,
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _write_json(output_root / "vectorbt" / "vectorbt_validation_summary.json", summary)
    return summary


def _rank_methods(comparison: pd.DataFrame) -> pd.DataFrame:
    ready = comparison.loc[comparison["status"] == "READY"].copy()
    if ready.empty:
        return ready
    ready["sharpe_sort"] = pd.to_numeric(ready["sharpe"], errors="coerce").fillna(-999.0)
    ready["drawdown_sort"] = pd.to_numeric(
        ready["max_drawdown"], errors="coerce"
    ).fillna(-999.0)
    ready["cagr_sort"] = pd.to_numeric(ready["cagr"], errors="coerce").fillna(-999.0)
    ready = ready.sort_values(
        ["sharpe_sort", "drawdown_sort", "cagr_sort"],
        ascending=[False, False, False],
    ).drop(columns=["sharpe_sort", "drawdown_sort", "cagr_sort"])
    ready.insert(0, "rank", np.arange(1, len(ready) + 1))
    return ready.reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Kalman V3.1 portfolio/risk tournament on completed V3 artifacts"
    )
    p.add_argument("--v3-root", required=True)
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--code-sha", required=True)
    p.add_argument("--lookback-days", type=int, default=180)
    p.add_argument("--min-observations", type=int, default=90)
    p.add_argument("--rebalance", choices=["M", "Q"], default="M")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    v3_root = Path(args.v3_root).expanduser()
    matrix_dir = Path(args.matrix_dir).expanduser()
    output_root = Path(args.output_dir).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)

    final_v3 = _load_json(v3_root / "historical_v3_candidate_summary.json")
    if final_v3.get("status") != "COMPLETE":
        raise RuntimeError(f"V3 source is not COMPLETE: {final_v3.get('status')}")
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

    pypfopt_rows = run_pypfopt_tournament(
        returns,
        output_root,
        lookback_days=args.lookback_days,
        min_observations=args.min_observations,
        rebalance_frequency=args.rebalance,
    )
    riskfolio_rows = run_riskfolio_tournament(
        returns,
        output_root,
        lookback_days=args.lookback_days,
        min_observations=args.min_observations,
        rebalance_frequency=args.rebalance,
    )
    vectorbt_summary = run_vectorbt_validation(
        v3_root=v3_root,
        matrix_dir=matrix_dir,
        spec=spec,
        output_root=output_root,
    )

    comparison = pd.DataFrame([*pypfopt_rows, *riskfolio_rows])
    comparison.to_csv(output_root / "tournament_comparison.csv", index=False)
    ranking = _rank_methods(comparison)
    ranking.to_csv(output_root / "tournament_ranking.csv", index=False)

    conservative_methods = {
        "equal_weight",
        "inverse_volatility",
        "hrp",
        "cvar_minrisk",
        "risk_parity",
        "cdar_minrisk",
    }
    conservative = ranking.loc[ranking["method"].isin(conservative_methods)]
    conservative_pick = (
        conservative.iloc[0].to_dict() if not conservative.empty else None
    )
    overall_pick = ranking.iloc[0].to_dict() if not ranking.empty else None

    original_equal = candidate.get("portfolio", {}).get("metrics")
    recomputed_equal_row = next(
        (
            row
            for row in pypfopt_rows
            if row.get("method") == "equal_weight" and row.get("status") == "READY"
        ),
        None,
    )
    equal_return_gap = None
    if original_equal and recomputed_equal_row:
        a = _safe_float(original_equal.get("total_return"))
        b = _safe_float(recomputed_equal_row.get("total_return"))
        if a is not None and b is not None:
            equal_return_gap = float(b - a)

    summary = {
        "status": "COMPLETE",
        "experiment": "V3_1_PORTFOLIO_RISK_TOURNAMENT",
        "code_sha": args.code_sha,
        "source_v3_root": str(v3_root),
        "ready_markets": ready_markets,
        "configuration": {
            "lookback_days": args.lookback_days,
            "min_observations": args.min_observations,
            "rebalance_frequency": args.rebalance,
            "position_source": "V3 strategy_100pct_equity",
        },
        "methods": {
            "pypfopt_and_native": list(PYPFOPT_METHODS),
            "riskfolio": list(RISKFOLIO_METHODS),
            "vectorbt": "10pct independent replay",
        },
        "original_v3_equal_weight": original_equal,
        "equal_weight_recompute_total_return_gap": equal_return_gap,
        "overall_sharpe_rank_winner": overall_pick,
        "conservative_recommendation": conservative_pick,
        "vectorbt": vectorbt_summary,
        "research_only": True,
        "promotion_recommendation": "RESEARCH_ONLY",
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _write_json(output_root / "v3_1_tournament_summary.json", summary)

    print("\nKALMAN V3.1 PORTFOLIO/RISK TOURNAMENT COMPLETE")
    print(output_root / "v3_1_tournament_summary.json")
    if not ranking.empty:
        print("\nRANKING")
        print(ranking.to_string(index=False))
    print("\nCONSERVATIVE RECOMMENDATION")
    print(json.dumps(conservative_pick, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
