from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .portfolio_targets import (
    load_sleeve_returns,
    portfolio_equity_from_targets,
    portfolio_metrics,
)


RISKFOLIO_METHODS = (
    "cvar_minrisk",
    "risk_parity",
    "cdar_minrisk",
)


@dataclass(frozen=True)
class RiskfolioBenchmarkResult:
    comparison: pd.DataFrame
    summaries: dict[str, Any]


def _normalize(weights: pd.Series, columns: list[str]) -> pd.Series:
    out = (
        pd.to_numeric(weights, errors="coerce")
        .reindex(columns)
        .fillna(0.0)
        .clip(lower=0.0)
    )
    total = float(out.sum())
    if total <= 0:
        raise RuntimeError("Riskfolio returned zero total weight")
    return out / total


def _weight_series(raw: Any, columns: list[str]) -> pd.Series:
    if raw is None:
        raise RuntimeError("Riskfolio optimization returned None")

    if isinstance(raw, pd.Series):
        return _normalize(raw, columns)

    if isinstance(raw, pd.DataFrame):
        if raw.empty:
            raise RuntimeError("Riskfolio optimization returned an empty DataFrame")
        if "weights" in raw.columns:
            series = raw["weights"]
        elif raw.shape[1] == 1:
            series = raw.iloc[:, 0]
        else:
            raise RuntimeError(
                f"Riskfolio returned unexpected weight columns: {list(raw.columns)}"
            )
        return _normalize(series, columns)

    raise RuntimeError(
        f"Riskfolio returned unsupported weights type: {type(raw).__name__}"
    )


def riskfolio_weights(
    returns: pd.DataFrame,
    *,
    method: str,
) -> pd.Series:
    """Calculate one long-only Riskfolio allocation for Kalman sleeves."""
    try:
        import riskfolio as rp
    except ImportError as exc:
        raise RuntimeError(
            "riskfolio-lib is not installed. "
            "Install research/quant_stack/requirements-riskfolio.txt "
            "in the isolated Riskfolio venv."
        ) from exc

    clean = (
        returns.copy()
        .replace([np.inf, -np.inf], np.nan)
        .dropna(how="any")
        .astype(float)
    )
    if clean.empty:
        raise ValueError("returns are empty after cleaning")
    if clean.shape[1] < 2:
        raise ValueError("Riskfolio benchmark requires at least two sleeves")

    port = rp.Portfolio(returns=clean)
    port.assets_stats(method_mu="hist", method_cov="hist", d=0.94)

    method = method.strip().lower()
    if method == "cvar_minrisk":
        raw = port.optimization(
            model="Classic",
            rm="CVaR",
            obj="MinRisk",
            rf=0,
            l=0,
            hist=True,
        )
    elif method == "risk_parity":
        raw = port.rp_optimization(
            model="Classic",
            rm="MV",
            rf=0,
            b=None,
            hist=True,
        )
    elif method == "cdar_minrisk":
        raw = port.optimization(
            model="Classic",
            rm="CDaR",
            obj="MinRisk",
            rf=0,
            l=0,
            hist=True,
        )
    else:
        raise ValueError(f"unsupported Riskfolio method: {method}")

    weights = _weight_series(raw, list(clean.columns))
    if not np.isclose(float(weights.sum()), 1.0, atol=1e-7):
        raise RuntimeError("Riskfolio weights do not sum to 1")
    if (weights < -1e-10).any():
        raise RuntimeError("Riskfolio long-only benchmark produced negative weights")
    return weights


def _rebalance_dates(index: pd.DatetimeIndex, frequency: str) -> list[pd.Timestamp]:
    naive = index.tz_convert(None) if index.tz is not None else index
    freq = frequency.upper()
    if freq == "M":
        periods = naive.to_period("M")
    elif freq == "Q":
        periods = naive.to_period("Q")
    else:
        raise ValueError("rebalance_frequency must be M or Q")
    return [pd.Timestamp(x) for x in index[~periods.duplicated()]]


def build_riskfolio_targets(
    returns: pd.DataFrame,
    *,
    method: str,
    lookback_days: int = 180,
    min_observations: int = 90,
    rebalance_frequency: str = "M",
) -> pd.DataFrame:
    frame = returns.copy().sort_index()
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index, utc=True, errors="raise"))
    frame = frame.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    if lookback_days <= 0:
        raise ValueError("lookback_days must be > 0")
    if min_observations < 20:
        raise ValueError("min_observations must be >= 20")

    rows: list[dict[str, Any]] = []
    for effective_ts in _rebalance_dates(frame.index, rebalance_frequency):
        history = frame.loc[frame.index < effective_ts].tail(lookback_days)
        if len(history) < min_observations:
            continue

        weights = riskfolio_weights(history, method=method)
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
                    "source": "RISKFOLIO",
                }
            )

    result = pd.DataFrame(rows)
    if result.empty:
        raise RuntimeError(f"no Riskfolio targets generated for {method}")
    return result.sort_values(["effective_ts", "sleeve"]).reset_index(drop=True)


def _historical_cvar_95(portfolio_return: pd.Series) -> float | None:
    values = pd.to_numeric(portfolio_return, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) < 20:
        return None
    cutoff = np.quantile(values, 0.05)
    tail = values[values <= cutoff]
    if not len(tail):
        return None
    return float(-np.mean(tail))


def run_riskfolio_benchmarks(
    output_root: Path,
    *,
    markets: list[str],
    methods: tuple[str, ...] = RISKFOLIO_METHODS,
    lookback_days: int = 180,
    min_observations: int = 90,
    rebalance_frequency: str = "M",
    initial_equity: float = 1_000_000.0,
) -> RiskfolioBenchmarkResult:
    returns = load_sleeve_returns(output_root, markets)
    benchmark_dir = output_root / "riskfolio"
    benchmark_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}

    for method in methods:
        targets = build_riskfolio_targets(
            returns,
            method=method,
            lookback_days=lookback_days,
            min_observations=min_observations,
            rebalance_frequency=rebalance_frequency,
        )
        equity = portfolio_equity_from_targets(
            returns,
            targets,
            initial_equity=initial_equity,
        )
        metrics = portfolio_metrics(equity)
        metrics["historical_cvar_95"] = _historical_cvar_95(
            equity["portfolio_return"]
        )

        targets.to_parquet(
            benchmark_dir / f"portfolio_target_{method}.parquet",
            index=False,
        )
        equity.to_parquet(
            benchmark_dir / f"portfolio_equity_{method}.parquet",
            index=False,
        )
        (benchmark_dir / f"portfolio_performance_{method}.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

        summary = {
            "method": method,
            "source": "RISKFOLIO",
            "markets": markets,
            "rebalance_count": int(targets["effective_ts"].nunique()),
            "target_rows": int(len(targets)),
            "performance": metrics,
            "live_execution": False,
            "neon_write": False,
            "toss_execution": False,
        }
        summaries[method] = summary
        rows.append(
            {
                "method": method,
                "source": "RISKFOLIO",
                "total_return": metrics.get("total_return"),
                "cagr": metrics.get("cagr"),
                "sharpe": metrics.get("sharpe"),
                "max_drawdown": metrics.get("max_drawdown"),
                "annualized_volatility": metrics.get("annualized_volatility"),
                "historical_cvar_95": metrics.get("historical_cvar_95"),
                "rebalance_count": summary["rebalance_count"],
            }
        )

    baseline_path = output_root / "portfolio" / "portfolio_performance.json"
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        rows.append(
            {
                "method": "hrp",
                "source": "PYPFOPT",
                "total_return": baseline.get("total_return"),
                "cagr": baseline.get("cagr"),
                "sharpe": baseline.get("sharpe"),
                "max_drawdown": baseline.get("max_drawdown"),
                "annualized_volatility": baseline.get("annualized_volatility"),
                "historical_cvar_95": None,
                "rebalance_count": None,
            }
        )

    comparison = pd.DataFrame(rows)
    comparison.to_csv(benchmark_dir / "riskfolio_comparison.csv", index=False)
    (benchmark_dir / "riskfolio_summary.json").write_text(
        json.dumps(
            {
                "status": "READY",
                "research_only": True,
                "methods": summaries,
                "baseline_included": baseline_path.exists(),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ) + "\n",
        encoding="utf-8",
    )

    return RiskfolioBenchmarkResult(
        comparison=comparison,
        summaries=summaries,
    )
