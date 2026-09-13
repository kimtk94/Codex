from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .historical_v3_2_portfolio_validation import (
    build_pypfopt_targets_v32,
    corrected_portfolio_metrics,
    portfolio_equity_with_costs,
)

MARKETS = ("US", "KR", "BTC")
SOURCE_SETS = {
    "ALL_V2": {"US": "V2", "KR": "V2", "BTC": "V2"},
    "ALL_V3": {"US": "V3", "KR": "V3", "BTC": "V3"},
    "HYBRID_USV2_KRV3_BTCV2": {"US": "V2", "KR": "V3", "BTC": "V2"},
}
METHODS = ("equal_weight", "max_sharpe")
LOOKBACKS = (90, 180, 365)
MIN_OBSERVATIONS = {90: 60, 180: 90, 365: 180}
COST_BPS = (5.0, 10.0, 20.0, 30.0)
REBALANCE_FREQUENCIES = ("M", "Q")
BASE_CONFIG = {
    "lookback_days": 180,
    "min_observations": 90,
    "rebalance_frequency": "M",
    "rebalance_cost_bps": 10.0,
}
ANNUALIZATION_DAYS = 365
INITIAL_EQUITY = 1_000_000.0


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


def _require_preconditions(
    *,
    v2_root: Path,
    v3_root: Path,
    parity_status_path: Path,
) -> dict[str, Any]:
    v2 = _load_json(v2_root / "historical_v2_candidate_summary.json")
    v3 = _load_json(v3_root / "historical_v3_candidate_summary.json")
    parity = _load_json(parity_status_path)

    if v2.get("status") != "COMPLETE":
        raise RuntimeError(f"V2 source not COMPLETE: {v2.get('status')}")
    if v3.get("status") != "COMPLETE":
        raise RuntimeError(f"V3 source not COMPLETE: {v3.get('status')}")
    if parity.get("status") != "COMPLETE" or parity.get("parity_status") != "READY":
        raise RuntimeError(
            "V3.2 vectorbt parity is not COMPLETE/READY: "
            f"{parity.get('status')}/{parity.get('parity_status')}"
        )

    return {
        "v2_status": v2.get("status"),
        "v3_status": v3.get("status"),
        "parity_status": parity.get("parity_status"),
        "parity_sha": parity.get("pinned_sha"),
    }


def _load_market_return(root: Path, market: str) -> pd.Series:
    path = root / market.lower() / "strategy_100pct_equity.parquet"
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
    ret = daily.pct_change().replace([np.inf, -np.inf], np.nan)
    return ret.rename(market)


def _build_source_set_returns(
    *,
    v2_root: Path,
    v3_root: Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    cache: dict[tuple[str, str], pd.Series] = {}
    roots = {"V2": v2_root, "V3": v3_root}

    for version, root in roots.items():
        for market in MARKETS:
            cache[(version, market)] = _load_market_return(root, market)

    raw: dict[str, pd.DataFrame] = {}
    for source_name, mapping in SOURCE_SETS.items():
        frame = pd.concat(
            {
                market: cache[(mapping[market], market)]
                for market in MARKETS
            },
            axis=1,
        ).sort_index()
        frame = frame.dropna(how="any")
        if frame.empty:
            raise RuntimeError(f"{source_name}: no common market returns")
        raw[source_name] = frame

    shared_start = max(frame.index.min() for frame in raw.values())
    shared_end = min(frame.index.max() for frame in raw.values())
    if shared_start >= shared_end:
        raise RuntimeError("source sets do not share a usable time range")

    common: dict[str, pd.DataFrame] = {}
    for source_name, frame in raw.items():
        sliced = frame.loc[(frame.index >= shared_start) & (frame.index <= shared_end)].copy()
        if sliced.empty:
            raise RuntimeError(f"{source_name}: empty after shared-window alignment")
        sliced = sliced.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        sliced.attrs["annualization_days"] = ANNUALIZATION_DAYS
        common[source_name] = sliced

    metadata = {
        "shared_return_start": shared_start,
        "shared_return_end": shared_end,
        "shared_return_observations": int(
            min(len(frame) for frame in common.values())
        ),
        "source_sets": SOURCE_SETS,
    }
    return common, metadata


def _rebase_window(
    equity: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    frame = equity.copy()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="raise")
    frame = frame.loc[(frame["ts"] >= start) & (frame["ts"] <= end)].copy()
    if frame.empty:
        return frame

    net = pd.to_numeric(frame["net_portfolio_return"], errors="coerce").fillna(0.0)
    frame["equity"] = INITIAL_EQUITY * (1.0 + net).cumprod()
    return frame.reset_index(drop=True)


def _window_metrics(
    equity: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    min_rows: int = 20,
) -> dict[str, Any] | None:
    frame = _rebase_window(equity, start=start, end=end)
    if len(frame) < min_rows:
        return None
    return corrected_portfolio_metrics(
        frame,
        initial_equity=INITIAL_EQUITY,
        annualization_days=ANNUALIZATION_DAYS,
    )


def _worst_126d_window(base_returns: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp]:
    clean = pd.to_numeric(base_returns, errors="coerce").fillna(0.0)
    if len(clean) < 126:
        raise RuntimeError("not enough observations for 126-day stress window")

    roll = (1.0 + clean).rolling(126).apply(np.prod, raw=True) - 1.0
    end = pd.Timestamp(roll.idxmin())
    end_pos = clean.index.get_loc(end)
    start_pos = max(0, end_pos - 125)
    start = pd.Timestamp(clean.index[start_pos])
    return start, end


def _fallback_stats(targets: pd.DataFrame) -> tuple[int, int, float]:
    rebalances = int(targets["effective_ts"].nunique())
    fallback = int(
        targets.loc[
            targets["optimization_status"] != "READY",
            "effective_ts",
        ].nunique()
    )
    ratio = fallback / rebalances if rebalances else 0.0
    return fallback, rebalances, float(ratio)


def _grid_key(
    source_set: str,
    method: str,
    lookback_days: int,
    rebalance_frequency: str,
    cost_bps: float,
) -> tuple[str, str, int, str, float]:
    return (
        source_set,
        method,
        int(lookback_days),
        str(rebalance_frequency),
        float(cost_bps),
    )


def _is_base(
    *,
    lookback_days: int,
    rebalance_frequency: str,
    cost_bps: float,
) -> bool:
    return (
        int(lookback_days) == BASE_CONFIG["lookback_days"]
        and str(rebalance_frequency) == BASE_CONFIG["rebalance_frequency"]
        and float(cost_bps) == BASE_CONFIG["rebalance_cost_bps"]
    )


def _grid_row(
    *,
    source_set: str,
    method: str,
    lookback_days: int,
    min_observations: int,
    rebalance_frequency: str,
    cost_bps: float,
    targets: pd.DataFrame,
    equity: pd.DataFrame,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    fallback_count, rebalance_count, fallback_ratio = _fallback_stats(targets)
    return {
        "status": "READY",
        "source_set": source_set,
        "method": method,
        "lookback_days": int(lookback_days),
        "min_observations": int(min_observations),
        "rebalance_frequency": rebalance_frequency,
        "rebalance_cost_bps": float(cost_bps),
        "start": metrics.get("start"),
        "end": metrics.get("end"),
        "total_return": metrics.get("total_return"),
        "gross_total_return": metrics.get("gross_total_return"),
        "cagr": metrics.get("cagr"),
        "sharpe": metrics.get("sharpe"),
        "max_drawdown": metrics.get("max_drawdown"),
        "annualized_volatility": metrics.get("annualized_volatility"),
        "historical_cvar_95": metrics.get("historical_cvar_95"),
        "half_l1_turnover_total": metrics.get("half_l1_turnover_total"),
        "traded_notional_ratio_total": metrics.get("traded_notional_ratio_total"),
        "rebalance_cost_rate_total": metrics.get("rebalance_cost_rate_total"),
        "fallback_rebalance_count": fallback_count,
        "target_rebalance_count": rebalance_count,
        "fallback_ratio": fallback_ratio,
        "observations": int(len(equity)),
    }


def run_grid(
    source_returns: dict[str, pd.DataFrame],
    output_root: Path,
) -> tuple[pd.DataFrame, dict[tuple[str, str, int, str, float], pd.DataFrame], dict[str, pd.DataFrame]]:
    rows: list[dict[str, Any]] = []
    equity_cache: dict[
        tuple[str, str, int, str, float],
        pd.DataFrame,
    ] = {}
    base_equities: dict[str, pd.DataFrame] = {}

    for source_set, returns in source_returns.items():
        for method in METHODS:
            for lookback in LOOKBACKS:
                min_obs = MIN_OBSERVATIONS[lookback]
                for rebalance in REBALANCE_FREQUENCIES:
                    try:
                        targets = build_pypfopt_targets_v32(
                            returns,
                            method=method,
                            lookback_days=lookback,
                            min_observations=min_obs,
                            rebalance_frequency=rebalance,
                            annualization_days=ANNUALIZATION_DAYS,
                        )
                    except Exception as exc:
                        for cost in COST_BPS:
                            rows.append(
                                {
                                    "status": "FAIL",
                                    "source_set": source_set,
                                    "method": method,
                                    "lookback_days": lookback,
                                    "min_observations": min_obs,
                                    "rebalance_frequency": rebalance,
                                    "rebalance_cost_bps": cost,
                                    "error_type": type(exc).__name__,
                                    "error": str(exc),
                                }
                            )
                        continue

                    for cost in COST_BPS:
                        key = _grid_key(
                            source_set,
                            method,
                            lookback,
                            rebalance,
                            cost,
                        )
                        try:
                            equity = portfolio_equity_with_costs(
                                returns,
                                targets,
                                initial_equity=INITIAL_EQUITY,
                                rebalance_cost_bps=cost,
                                charge_initial_allocation=True,
                            )
                            metrics = corrected_portfolio_metrics(
                                equity,
                                initial_equity=INITIAL_EQUITY,
                                annualization_days=ANNUALIZATION_DAYS,
                            )
                            rows.append(
                                _grid_row(
                                    source_set=source_set,
                                    method=method,
                                    lookback_days=lookback,
                                    min_observations=min_obs,
                                    rebalance_frequency=rebalance,
                                    cost_bps=cost,
                                    targets=targets,
                                    equity=equity,
                                    metrics=metrics,
                                )
                            )
                            equity_cache[key] = equity

                            if _is_base(
                                lookback_days=lookback,
                                rebalance_frequency=rebalance,
                                cost_bps=cost,
                            ):
                                base_root = (
                                    output_root
                                    / "base"
                                    / source_set.lower()
                                    / method
                                )
                                base_root.mkdir(parents=True, exist_ok=True)
                                targets.to_parquet(
                                    base_root / "portfolio_target.parquet",
                                    index=False,
                                )
                                equity.to_parquet(
                                    base_root / "portfolio_equity.parquet",
                                    index=False,
                                )
                                _write_json(
                                    base_root / "portfolio_performance.json",
                                    {
                                        **metrics,
                                        "source_set": source_set,
                                        "method": method,
                                        "configuration": BASE_CONFIG,
                                        "fallback_rebalance_count": _fallback_stats(targets)[0],
                                        "target_rebalance_count": _fallback_stats(targets)[1],
                                        "fallback_ratio": _fallback_stats(targets)[2],
                                    },
                                )
                                if method == "equal_weight":
                                    base_equities[source_set] = equity
                        except Exception as exc:
                            rows.append(
                                {
                                    "status": "FAIL",
                                    "source_set": source_set,
                                    "method": method,
                                    "lookback_days": lookback,
                                    "min_observations": min_obs,
                                    "rebalance_frequency": rebalance,
                                    "rebalance_cost_bps": cost,
                                    "error_type": type(exc).__name__,
                                    "error": str(exc),
                                }
                            )

    grid = pd.DataFrame(rows)
    return grid, equity_cache, base_equities


def build_period_windows(
    equity_cache: dict[tuple[str, str, int, str, float], pd.DataFrame],
    base_equities: dict[str, pd.DataFrame],
) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    if not equity_cache:
        raise RuntimeError("no READY grid equity to construct period windows")

    starts: list[pd.Timestamp] = []
    ends: list[pd.Timestamp] = []
    for equity in equity_cache.values():
        ts = pd.to_datetime(equity["ts"], utc=True, errors="raise")
        starts.append(pd.Timestamp(ts.min()))
        ends.append(pd.Timestamp(ts.max()))

    common_start = max(starts)
    common_end = min(ends)
    if common_start >= common_end:
        raise RuntimeError("grid runs do not share a common evaluation window")

    midpoint = common_start + (common_end - common_start) / 2
    recent_start = midpoint + pd.Timedelta(days=1)

    baseline_returns: list[pd.Series] = []
    for source_set in SOURCE_SETS:
        equity = base_equities.get(source_set)
        if equity is None:
            continue
        frame = equity.copy()
        frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="raise")
        series = pd.Series(
            pd.to_numeric(
                frame["net_portfolio_return"], errors="coerce"
            ).fillna(0.0).to_numpy(dtype=float),
            index=pd.DatetimeIndex(frame["ts"]),
            name=source_set,
        )
        baseline_returns.append(series)

    if not baseline_returns:
        raise RuntimeError("base equal-weight equities are missing")

    baseline_panel = pd.concat(baseline_returns, axis=1).sort_index()
    baseline_panel = baseline_panel.loc[
        (baseline_panel.index >= common_start)
        & (baseline_panel.index <= common_end)
    ].dropna(how="any")
    cross_source_baseline = baseline_panel.mean(axis=1)
    stress_start, stress_end = _worst_126d_window(cross_source_baseline)

    windows = {
        "FULL_COMMON": (common_start, common_end),
        "EARLY": (common_start, midpoint),
        "RECENT": (recent_start, common_end),
        "RISK_OFF_2022": (
            max(common_start, pd.Timestamp("2022-01-01", tz="UTC")),
            min(common_end, pd.Timestamp("2022-12-31", tz="UTC")),
        ),
        "WORST_126D": (stress_start, stress_end),
    }
    return windows


def build_period_results(
    *,
    grid: pd.DataFrame,
    equity_cache: dict[tuple[str, str, int, str, float], pd.DataFrame],
    windows: dict[str, tuple[pd.Timestamp, pd.Timestamp]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    ready = grid.loc[grid["status"] == "READY"].copy()
    for item in ready.itertuples(index=False):
        key = _grid_key(
            item.source_set,
            item.method,
            item.lookback_days,
            item.rebalance_frequency,
            item.rebalance_cost_bps,
        )
        equity = equity_cache[key]
        for period, (start, end) in windows.items():
            metrics = _window_metrics(
                equity,
                start=start,
                end=end,
            )
            if metrics is None:
                continue
            rows.append(
                {
                    "source_set": item.source_set,
                    "method": item.method,
                    "lookback_days": int(item.lookback_days),
                    "rebalance_frequency": item.rebalance_frequency,
                    "rebalance_cost_bps": float(item.rebalance_cost_bps),
                    "period": period,
                    "window_start": start,
                    "window_end": end,
                    "actual_start": metrics.get("start"),
                    "actual_end": metrics.get("end"),
                    "total_return": metrics.get("total_return"),
                    "cagr": metrics.get("cagr"),
                    "sharpe": metrics.get("sharpe"),
                    "max_drawdown": metrics.get("max_drawdown"),
                    "annualized_volatility": metrics.get("annualized_volatility"),
                    "historical_cvar_95": metrics.get("historical_cvar_95"),
                    "observations": metrics.get("observations"),
                    "fallback_ratio": float(item.fallback_ratio),
                }
            )

    return pd.DataFrame(rows)


def build_pairwise_comparison(period_results: pd.DataFrame) -> pd.DataFrame:
    keys = [
        "source_set",
        "lookback_days",
        "rebalance_frequency",
        "rebalance_cost_bps",
        "period",
    ]
    metric_cols = [
        "total_return",
        "cagr",
        "sharpe",
        "max_drawdown",
        "annualized_volatility",
        "historical_cvar_95",
        "fallback_ratio",
    ]

    ew = period_results.loc[
        period_results["method"] == "equal_weight",
        keys + metric_cols,
    ].copy()
    ms = period_results.loc[
        period_results["method"] == "max_sharpe",
        keys + metric_cols,
    ].copy()

    merged = ms.merge(
        ew,
        on=keys,
        suffixes=("_max_sharpe", "_equal_weight"),
        how="inner",
    )
    if merged.empty:
        return merged

    merged["return_delta"] = (
        merged["total_return_max_sharpe"]
        - merged["total_return_equal_weight"]
    )
    merged["cagr_delta"] = (
        merged["cagr_max_sharpe"]
        - merged["cagr_equal_weight"]
    )
    merged["sharpe_delta"] = (
        merged["sharpe_max_sharpe"]
        - merged["sharpe_equal_weight"]
    )
    merged["mdd_improvement"] = (
        merged["max_drawdown_max_sharpe"]
        - merged["max_drawdown_equal_weight"]
    )
    merged["vol_delta"] = (
        merged["annualized_volatility_max_sharpe"]
        - merged["annualized_volatility_equal_weight"]
    )
    merged["cvar_improvement"] = (
        merged["historical_cvar_95_equal_weight"]
        - merged["historical_cvar_95_max_sharpe"]
    )
    merged["max_sharpe_return_win"] = merged["return_delta"] > 0
    merged["max_sharpe_sharpe_win"] = merged["sharpe_delta"] > 0
    merged["max_sharpe_mdd_win"] = merged["mdd_improvement"] > 0
    return merged


def _rate(series: pd.Series) -> float | None:
    if series.empty:
        return None
    return float(pd.to_numeric(series, errors="coerce").fillna(0.0).mean())


def summarize_robustness(
    pairwise: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for source_set in SOURCE_SETS:
        source = pairwise.loc[pairwise["source_set"] == source_set].copy()
        full = source.loc[source["period"] == "FULL_COMMON"]
        recent = source.loc[source["period"] == "RECENT"]
        stress = source.loc[source["period"] == "WORST_126D"]
        risk_off = source.loc[source["period"] == "RISK_OFF_2022"]

        full_sharpe = _rate(full["max_sharpe_sharpe_win"])
        full_return = _rate(full["max_sharpe_return_win"])
        full_mdd = _rate(full["max_sharpe_mdd_win"])
        recent_sharpe = _rate(recent["max_sharpe_sharpe_win"])
        stress_sharpe = _rate(stress["max_sharpe_sharpe_win"])
        risk_off_sharpe = _rate(risk_off["max_sharpe_sharpe_win"])

        fallback = pd.to_numeric(
            full["fallback_ratio_max_sharpe"],
            errors="coerce",
        ).dropna()
        fallback_median = float(fallback.median()) if len(fallback) else None
        fallback_max = float(fallback.max()) if len(fallback) else None

        robust = (
            full_sharpe is not None
            and full_return is not None
            and recent_sharpe is not None
            and stress_sharpe is not None
            and fallback_median is not None
            and full_sharpe >= (2.0 / 3.0)
            and full_return >= 0.60
            and recent_sharpe >= 0.60
            and stress_sharpe >= 0.50
            and fallback_median <= 0.25
        )
        mixed = (
            not robust
            and full_sharpe is not None
            and full_sharpe >= 0.50
        )
        status = "ROBUST" if robust else "MIXED" if mixed else "WEAK"

        ms_full = full[
            [
                "sharpe_max_sharpe",
                "total_return_max_sharpe",
                "max_drawdown_max_sharpe",
            ]
        ].apply(pd.to_numeric, errors="coerce")

        rows.append(
            {
                "source_set": source_set,
                "robustness_status": status,
                "matched_full_configs": int(len(full)),
                "full_sharpe_win_rate": full_sharpe,
                "full_return_win_rate": full_return,
                "full_mdd_win_rate": full_mdd,
                "recent_sharpe_win_rate": recent_sharpe,
                "worst_126d_sharpe_win_rate": stress_sharpe,
                "risk_off_2022_sharpe_win_rate": risk_off_sharpe,
                "median_max_sharpe_fallback_ratio": fallback_median,
                "max_max_sharpe_fallback_ratio": fallback_max,
                "median_max_sharpe_sharpe": _safe_float(
                    ms_full["sharpe_max_sharpe"].median()
                ),
                "p10_max_sharpe_sharpe": _safe_float(
                    ms_full["sharpe_max_sharpe"].quantile(0.10)
                ),
                "median_max_sharpe_return": _safe_float(
                    ms_full["total_return_max_sharpe"].median()
                ),
                "median_max_sharpe_mdd": _safe_float(
                    ms_full["max_drawdown_max_sharpe"].median()
                ),
            }
        )

    return pd.DataFrame(rows)


def build_base_ranking(grid: pd.DataFrame) -> pd.DataFrame:
    base = grid.loc[
        (grid["status"] == "READY")
        & (grid["lookback_days"] == BASE_CONFIG["lookback_days"])
        & (grid["rebalance_frequency"] == BASE_CONFIG["rebalance_frequency"])
        & (grid["rebalance_cost_bps"] == BASE_CONFIG["rebalance_cost_bps"])
    ].copy()

    base = base.sort_values(
        ["method", "sharpe", "total_return", "max_drawdown"],
        ascending=[True, False, False, False],
    )
    return base.reset_index(drop=True)


def choose_recommendation(
    *,
    robustness: pd.DataFrame,
    base_ranking: pd.DataFrame,
) -> dict[str, Any]:
    score_map = {"ROBUST": 2, "MIXED": 1, "WEAK": 0}
    candidates = robustness.copy()
    candidates["status_score"] = candidates["robustness_status"].map(score_map).fillna(0)

    base_ms = base_ranking.loc[
        base_ranking["method"] == "max_sharpe",
        ["source_set", "sharpe", "total_return", "max_drawdown", "fallback_ratio"],
    ].copy()
    base_ms = base_ms.rename(
        columns={
            "sharpe": "base_sharpe",
            "total_return": "base_total_return",
            "max_drawdown": "base_max_drawdown",
            "fallback_ratio": "base_fallback_ratio",
        }
    )
    candidates = candidates.merge(base_ms, on="source_set", how="left")

    ranked = candidates.sort_values(
        [
            "status_score",
            "median_max_sharpe_sharpe",
            "p10_max_sharpe_sharpe",
            "base_sharpe",
            "base_total_return",
            "base_max_drawdown",
        ],
        ascending=[False, False, False, False, False, False],
    ).reset_index(drop=True)

    if ranked.empty:
        return {
            "status": "NO_CANDIDATE",
            "recommended_source_set": None,
            "recommended_allocator": None,
            "shadow_gate": "FAIL",
        }

    winner = ranked.iloc[0].to_dict()
    shadow_gate = (
        "PASS"
        if winner.get("robustness_status") == "ROBUST"
        and _safe_float(winner.get("base_fallback_ratio")) is not None
        and float(winner["base_fallback_ratio"]) <= 0.25
        else "HOLD"
    )

    return {
        "status": "READY",
        "recommended_source_set": winner.get("source_set"),
        "recommended_allocator": "max_sharpe",
        "shadow_gate": shadow_gate,
        "winner": winner,
        "ranking": ranked.to_dict(orient="records"),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Kalman V3.3 robustness + hybrid sleeve tournament"
    )
    p.add_argument("--v2-root", required=True)
    p.add_argument("--v3-root", required=True)
    p.add_argument("--parity-status", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--code-sha", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()

    v2_root = Path(args.v2_root).expanduser()
    v3_root = Path(args.v3_root).expanduser()
    parity_status_path = Path(args.parity_status).expanduser()
    output_root = Path(args.output_dir).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)

    preconditions = _require_preconditions(
        v2_root=v2_root,
        v3_root=v3_root,
        parity_status_path=parity_status_path,
    )

    source_returns, source_metadata = _build_source_set_returns(
        v2_root=v2_root,
        v3_root=v3_root,
    )

    grid, equity_cache, base_equities = run_grid(
        source_returns,
        output_root,
    )
    grid.to_csv(output_root / "v3_3_grid_results.csv", index=False)

    failures = grid.loc[grid["status"] != "READY"].copy()
    failures.to_csv(output_root / "v3_3_grid_failures.csv", index=False)

    windows = build_period_windows(
        equity_cache,
        base_equities,
    )
    period_results = build_period_results(
        grid=grid,
        equity_cache=equity_cache,
        windows=windows,
    )
    period_results.to_csv(
        output_root / "v3_3_period_results.csv",
        index=False,
    )

    pairwise = build_pairwise_comparison(period_results)
    pairwise.to_csv(
        output_root / "v3_3_max_sharpe_vs_equal.csv",
        index=False,
    )

    robustness = summarize_robustness(pairwise)
    robustness.to_csv(
        output_root / "v3_3_source_robustness.csv",
        index=False,
    )

    base_ranking = build_base_ranking(grid)
    base_ranking.to_csv(
        output_root / "v3_3_base_ranking.csv",
        index=False,
    )

    recommendation = choose_recommendation(
        robustness=robustness,
        base_ranking=base_ranking,
    )

    experiment_status = (
        "READY"
        if failures.empty
        and recommendation.get("status") == "READY"
        else "DEGRADED"
    )
    promotion = (
        "SHADOW_CANDIDATE"
        if experiment_status == "READY"
        and recommendation.get("shadow_gate") == "PASS"
        else "RESEARCH_ONLY"
    )

    summary = {
        "status": "COMPLETE",
        "experiment_status": experiment_status,
        "experiment": "V3_3_ROBUSTNESS_HYBRID_TOURNAMENT",
        "code_sha": args.code_sha,
        "preconditions": preconditions,
        "source_metadata": source_metadata,
        "source_sets": SOURCE_SETS,
        "methods": METHODS,
        "grid": {
            "lookbacks": LOOKBACKS,
            "min_observations": MIN_OBSERVATIONS,
            "rebalance_cost_bps": COST_BPS,
            "rebalance_frequencies": REBALANCE_FREQUENCIES,
            "annualization_days": ANNUALIZATION_DAYS,
            "expected_runs": (
                len(SOURCE_SETS)
                * len(METHODS)
                * len(LOOKBACKS)
                * len(COST_BPS)
                * len(REBALANCE_FREQUENCIES)
            ),
            "ready_runs": int((grid["status"] == "READY").sum()),
            "failed_runs": int((grid["status"] != "READY").sum()),
        },
        "period_windows": {
            name: {"start": start, "end": end}
            for name, (start, end) in windows.items()
        },
        "robustness_rules": {
            "full_sharpe_win_rate_min": 2.0 / 3.0,
            "full_return_win_rate_min": 0.60,
            "recent_sharpe_win_rate_min": 0.60,
            "worst_126d_sharpe_win_rate_min": 0.50,
            "median_fallback_ratio_max": 0.25,
        },
        "robustness": robustness.to_dict(orient="records"),
        "base_ranking": base_ranking.to_dict(orient="records"),
        "recommendation": recommendation,
        "promotion_recommendation": promotion,
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _write_json(
        output_root / "v3_3_summary.json",
        summary,
    )

    print("\n" + "=" * 92)
    print("KALMAN V3.3 ROBUSTNESS + HYBRID TOURNAMENT COMPLETE")
    print("=" * 92)
    print("experiment_status:", experiment_status)
    print("promotion_recommendation:", promotion)
    print("\nROBUSTNESS")
    print(robustness.to_string(index=False))
    print("\nBASE RANKING")
    print(base_ranking.to_string(index=False))
    print("\nRECOMMENDATION")
    print(json.dumps(recommendation, ensure_ascii=False, indent=2, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
