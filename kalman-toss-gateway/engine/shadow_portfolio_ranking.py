from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


MARKETS = ("US", "KR", "BTC")
STRATEGIES = (
    "A_EQUAL_WEIGHT",
    "B_STATIC_MAX_SHARPE",
    "C_RISK_CAP_110",
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: config must be an object")
    return value


def _utc_ts(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _assert_wall_clock_freshness(
    last_raw: dict[str, pd.Timestamp],
    files: dict[str, Any],
    *,
    now: pd.Timestamp | None = None,
) -> None:
    reference = _utc_ts(now if now is not None else pd.Timestamp.now(tz="UTC")).normalize()
    for market in MARKETS:
        spec = files.get(market) or {}
        max_age = spec.get("max_wall_clock_age_days")
        if max_age is None:
            continue
        latest = _utc_ts(last_raw[market]).normalize()
        age_days = max((reference - latest).days, 0)
        if age_days > int(max_age):
            raise RuntimeError(
                f"{market}: stale market source by wall clock; "
                f"last={latest.isoformat()} now={reference.isoformat()} "
                f"age_days={age_days} max={int(max_age)}"
            )


def _load_close(path: Path, market: str) -> pd.Series:
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_parquet(path)
    ts_col = "timestamp" if "timestamp" in frame.columns else ("ts" if "ts" in frame.columns else None)
    if ts_col is None or "close" not in frame.columns:
        raise ValueError(
            f"{path}: required columns are timestamp (or legacy ts), close; "
            f"available={list(frame.columns)}"
        )
    out = frame[[ts_col, "close"]].copy().rename(columns={ts_col: "timestamp"})
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="raise")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out = (
        out.dropna(subset=["timestamp", "close"])
        .loc[lambda x: x["close"] > 0]
        .sort_values("timestamp")
        .drop_duplicates("timestamp", keep="last")
    )
    if len(out) < 90:
        raise RuntimeError(f"{market}: insufficient market rows ({len(out)})")
    series = out.set_index("timestamp")["close"]
    series.name = market
    return series


def build_return_panel(
    market_root: Path,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, str], pd.Timestamp]:
    files = config.get("market_files") or {}
    closes: dict[str, pd.Series] = {}
    last_raw: dict[str, pd.Timestamp] = {}

    for market in MARKETS:
        spec = files.get(market) or {}
        rel = spec.get("path")
        if not rel:
            raise ValueError(f"{market}: missing path in market_files")
        series = _load_close(market_root / str(rel), market)
        closes[market] = series
        last_raw[market] = pd.Timestamp(series.index.max())

    data_end = max(last_raw.values())
    for market in MARKETS:
        max_lag = int((files.get(market) or {}).get("max_lag_days", 4))
        lag = (data_end.normalize() - last_raw[market].normalize()).days
        if lag > max_lag:
            raise RuntimeError(
                f"{market}: stale market source; last={last_raw[market].isoformat()} "
                f"data_end={data_end.isoformat()} lag_days={lag} max={max_lag}"
            )

    # Relative cross-market lag cannot detect the case where every source stopped
    # together. Guard against that with an absolute wall-clock age as well.
    _assert_wall_clock_freshness(last_raw, files)

    panel = pd.concat(closes, axis=1).sort_index()
    panel = panel.resample("1D").last().ffill()
    panel = panel.dropna(how="any")
    if panel.empty:
        raise RuntimeError("common close panel is empty")

    returns = panel.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    returns = returns.loc[returns.index <= data_end.normalize()]
    returns.attrs["annualization_days"] = int(config.get("annualization_days", 365))

    if len(returns) < int(config.get("min_observations", 90)) + 2:
        raise RuntimeError("return panel is too short")

    as_of = {market: last_raw[market].isoformat() for market in MARKETS}
    return returns, as_of, data_end


@lru_cache(maxsize=16)
def _simplex_grid(step: float) -> np.ndarray:
    if not (0.0 < step <= 0.1):
        raise ValueError("simplex_step must be in (0, 0.1]")
    intervals = int(round(1.0 / step))
    if not math.isclose(intervals * step, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("simplex_step must divide 1.0 exactly")
    rows: list[tuple[float, float, float]] = []
    for i in range(intervals + 1):
        for j in range(intervals - i + 1):
            k = intervals - i - j
            rows.append((i / intervals, j / intervals, k / intervals))
    return np.asarray(rows, dtype=float)


def _annual_expected_return(history: pd.DataFrame, annualization_days: int) -> np.ndarray:
    clean = history.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    wealth = (1.0 + clean).cumprod()
    if len(wealth) < 2:
        return np.zeros(clean.shape[1], dtype=float)
    days = max((clean.index[-1] - clean.index[0]).days, 1)
    years = days / 365.25
    start = wealth.iloc[0].to_numpy(dtype=float)
    end = wealth.iloc[-1].to_numpy(dtype=float)
    ratio = np.divide(end, start, out=np.ones_like(end), where=start > 0)
    mu = np.power(np.maximum(ratio, 1e-12), 1.0 / years) - 1.0
    return np.where(np.isfinite(mu), mu, 0.0)


def _annual_covariance(history: pd.DataFrame, annualization_days: int) -> np.ndarray:
    clean = history.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    matrix = clean.cov().to_numpy(dtype=float) * float(annualization_days)
    matrix = np.where(np.isfinite(matrix), matrix, 0.0)
    return matrix


def _portfolio_vol(weights: np.ndarray, cov: np.ndarray) -> float:
    variance = float(weights @ cov @ weights)
    return math.sqrt(max(variance, 0.0))


def _max_sharpe_weights(
    history: pd.DataFrame,
    *,
    annualization_days: int,
    step: float,
) -> tuple[np.ndarray, str, str | None]:
    grid = _simplex_grid(step)
    mu = _annual_expected_return(history, annualization_days)
    cov = _annual_covariance(history, annualization_days)

    variances = np.einsum("ij,jk,ik->i", grid, cov, grid)
    vols = np.sqrt(np.maximum(variances, 0.0))
    expected = grid @ mu
    valid = vols > 1e-12

    if np.any(valid) and float(np.max(mu)) > 0.0:
        scores = np.full(len(grid), -np.inf, dtype=float)
        scores[valid] = expected[valid] / vols[valid]
        idx = int(np.argmax(scores))
        if np.isfinite(scores[idx]):
            return grid[idx], "READY", None

    if np.any(valid):
        idx = int(np.argmin(np.where(valid, vols, np.inf)))
        return grid[idx], "FALLBACK_MIN_VOL", "no positive finite max-Sharpe solution"

    return np.asarray([1 / 3, 1 / 3, 1 / 3], dtype=float), "FALLBACK_EQUAL_WEIGHT", "degenerate covariance"


def _risk_cap_weights(
    ew: np.ndarray,
    ms: np.ndarray,
    cov: np.ndarray,
    *,
    risk_cap_ratio: float,
    fallback: bool,
) -> tuple[np.ndarray, float, dict[str, Any]]:
    ew_vol = _portfolio_vol(ew, cov)
    ms_vol = _portfolio_vol(ms, cov)
    cap = ew_vol * float(risk_cap_ratio)
    if fallback:
        return ew.copy(), 0.0, {
            "equal_weight_vol": ew_vol,
            "max_sharpe_vol": ms_vol,
            "risk_cap_vol": cap,
            "blended_vol": ew_vol,
            "risk_cap_binding": False,
            "risk_cap_reason": "MAX_SHARPE_FALLBACK",
        }
    if ew_vol <= 0:
        return ms.copy(), 1.0, {
            "equal_weight_vol": ew_vol,
            "max_sharpe_vol": ms_vol,
            "risk_cap_vol": cap,
            "blended_vol": ms_vol,
            "risk_cap_binding": False,
            "risk_cap_reason": "DEGENERATE_EQUAL_WEIGHT_VOL",
        }

    if ms_vol <= cap + 1e-12:
        return ms.copy(), 1.0, {
            "equal_weight_vol": ew_vol,
            "max_sharpe_vol": ms_vol,
            "risk_cap_vol": cap,
            "blended_vol": ms_vol,
            "risk_cap_binding": False,
            "risk_cap_reason": "MAX_SHARPE_WITHIN_CAP",
        }

    best_alpha = 0.0
    best = ew.copy()
    best_vol = ew_vol
    for alpha in np.linspace(0.0, 1.0, 1001):
        candidate = (1.0 - alpha) * ew + alpha * ms
        vol = _portfolio_vol(candidate, cov)
        if vol <= cap + 1e-12:
            best_alpha = float(alpha)
            best = candidate
            best_vol = vol

    return best, best_alpha, {
        "equal_weight_vol": ew_vol,
        "max_sharpe_vol": ms_vol,
        "risk_cap_vol": cap,
        "blended_vol": best_vol,
        "risk_cap_binding": True,
        "risk_cap_reason": "MAX_SHARPE_EXCEEDED_CAP",
    }


def _rebalance_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    naive = index.tz_convert(None) if index.tz is not None else index
    periods = naive.to_period("M")
    return [pd.Timestamp(x) for x in index[~periods.duplicated()]]


def build_targets(
    returns: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    lookback = int(config.get("lookback_days", 180))
    min_obs = int(config.get("min_observations", 90))
    annualization_days = int(config.get("annualization_days", 365))
    step = float(config.get("simplex_step", 0.002))
    risk_cap_ratio = float(config.get("risk_cap_ratio", 1.10))
    cols = list(MARKETS)
    rows = {name: [] for name in STRATEGIES}
    audit: list[dict[str, Any]] = []

    for effective_ts in _rebalance_dates(returns.index):
        history = returns.loc[returns.index < effective_ts, cols].tail(lookback)
        if len(history) < min_obs:
            continue

        ew = np.asarray([1 / 3, 1 / 3, 1 / 3], dtype=float)
        ms, ms_status, fallback_reason = _max_sharpe_weights(
            history,
            annualization_days=annualization_days,
            step=step,
        )
        cov = _annual_covariance(history, annualization_days)
        gate, alpha, risk = _risk_cap_weights(
            ew,
            ms,
            cov,
            risk_cap_ratio=risk_cap_ratio,
            fallback=ms_status != "READY",
        )

        weights_by_strategy = {
            "A_EQUAL_WEIGHT": ew,
            "B_STATIC_MAX_SHARPE": ms,
            "C_RISK_CAP_110": gate,
        }
        for strategy, weights in weights_by_strategy.items():
            if not math.isclose(float(weights.sum()), 1.0, abs_tol=1e-8):
                raise RuntimeError(f"{strategy}: weights do not sum to one")
            if np.any(weights < -1e-12):
                raise RuntimeError(f"{strategy}: negative long-only weight")
            rows[strategy].append(
                {
                    "decision_ts": history.index[-1],
                    "effective_ts": effective_ts,
                    "US": float(weights[0]),
                    "KR": float(weights[1]),
                    "BTC": float(weights[2]),
                    "lookback_start": history.index[0],
                    "lookback_end": history.index[-1],
                    "observations": int(len(history)),
                    "optimization_status": ms_status if strategy != "A_EQUAL_WEIGHT" else "READY",
                    "fallback_reason": fallback_reason if strategy != "A_EQUAL_WEIGHT" else None,
                }
            )

        cap_vol = float(risk.get("risk_cap_vol") or 0.0)
        audit.append(
            {
                "decision_ts": history.index[-1],
                "effective_ts": effective_ts,
                "alpha_max_sharpe": alpha,
                "max_sharpe_status": ms_status,
                "fallback_reason": fallback_reason,
                "max_sharpe_to_cap_ratio": (
                    float(risk["max_sharpe_vol"]) / cap_vol if cap_vol > 0 else None
                ),
                **risk,
            }
        )

    frames = {name: pd.DataFrame(value) for name, value in rows.items()}
    if any(frame.empty for frame in frames.values()):
        raise RuntimeError("no portfolio targets generated")
    return frames, pd.DataFrame(audit)


def simulate_portfolio(
    returns: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    initial_equity: float,
    cost_bps: float,
) -> pd.DataFrame:
    target_map: dict[pd.Timestamp, np.ndarray] = {}
    for row in targets.itertuples(index=False):
        target_map[pd.Timestamp(row.effective_ts)] = np.asarray(
            [row.US, row.KR, row.BTC],
            dtype=float,
        )

    first_effective = min(target_map)
    frame = returns.loc[returns.index >= first_effective, list(MARKETS)].copy()
    values = np.zeros(3, dtype=float)
    cash = float(initial_equity)
    fee_rate = float(cost_bps) / 10_000.0
    out: list[dict[str, Any]] = []

    for ts, daily in frame.iterrows():
        daily_ret = daily.to_numpy(dtype=float)
        pre_equity = float(cash + values.sum())
        if pre_equity <= 0:
            raise RuntimeError("portfolio equity became non-positive")

        cost_rate = 0.0
        half_turnover = 0.0
        traded_ratio = 0.0
        is_rebalance = ts in target_map

        if is_rebalance:
            target = target_map[ts]
            invested = float(values.sum())
            prior = values / invested if invested > 0 else np.zeros(3, dtype=float)
            traded_ratio = float(np.abs(target - prior).sum())
            half_turnover = 0.5 * traded_ratio
            cost_rate = traded_ratio * fee_rate
            investable = pre_equity * (1.0 - cost_rate)
            if investable <= 0:
                raise RuntimeError("rebalance costs consumed portfolio equity")
            values = investable * target
            cash = 0.0

        invested_before = float(values.sum())
        gross_return = (
            float((values / invested_before * daily_ret).sum())
            if invested_before > 0
            else 0.0
        )
        values = values * (1.0 + daily_ret)
        end_equity = float(cash + values.sum())
        net_return = end_equity / pre_equity - 1.0

        out.append(
            {
                "ts": ts,
                "gross_portfolio_return": gross_return,
                "net_portfolio_return": net_return,
                "rebalance_cost_rate": cost_rate,
                "half_l1_turnover": half_turnover,
                "traded_notional_ratio": traded_ratio,
                "equity": end_equity,
                "is_rebalance": is_rebalance,
            }
        )

    return pd.DataFrame(out)


def forward_metrics(
    equity: pd.DataFrame,
    *,
    seed_end: pd.Timestamp,
    initial_equity: float,
    annualization_days: int,
) -> dict[str, Any] | None:
    frame = equity.copy()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="raise")
    frame = frame.loc[frame["ts"] > seed_end].copy().reset_index(drop=True)
    if len(frame) < 2:
        return None

    net = pd.to_numeric(frame["net_portfolio_return"], errors="coerce").fillna(0.0)
    gross = pd.to_numeric(frame["gross_portfolio_return"], errors="coerce").fillna(0.0)
    rebased = float(initial_equity) * (1.0 + net).cumprod()
    ending = float(rebased.iloc[-1])
    total_return = ending / float(initial_equity) - 1.0
    start_ts = pd.Timestamp(frame["ts"].iloc[0])
    end_ts = pd.Timestamp(frame["ts"].iloc[-1])
    days = max((end_ts - start_ts).days + 1, 1)
    years = days / 365.25
    cagr = (ending / float(initial_equity)) ** (1.0 / years) - 1.0
    sd = float(net.std(ddof=0))
    sharpe = float(net.mean() / sd * math.sqrt(annualization_days)) if sd > 0 else None

    equity_series = pd.concat(
        [pd.Series([float(initial_equity)]), rebased.reset_index(drop=True)],
        ignore_index=True,
    )
    drawdown = equity_series / equity_series.cummax() - 1.0
    values = net.to_numpy(dtype=float)
    cvar = None
    if len(values) >= 20:
        cutoff = float(np.quantile(values, 0.05))
        tail = values[values <= cutoff]
        if len(tail):
            cvar = float(-np.mean(tail))

    return {
        "start": start_ts,
        "end": end_ts,
        "initial_equity": float(initial_equity),
        "ending_equity": ending,
        "total_return": float(total_return),
        "cagr": float(cagr),
        "annualized_volatility": float(sd * math.sqrt(annualization_days)),
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()),
        "historical_cvar_95": cvar,
        "gross_total_return": float((1.0 + gross).prod() - 1.0),
        "net_total_return": float((1.0 + net).prod() - 1.0),
        "rebalance_count": int(frame["is_rebalance"].sum()),
        "half_l1_turnover_total": float(frame["half_l1_turnover"].sum()),
        "traded_notional_ratio_total": float(frame["traded_notional_ratio"].sum()),
        "rebalance_cost_rate_total": float(frame["rebalance_cost_rate"].sum()),
        "observations": int(len(frame)),
        "annualization_days": int(annualization_days),
    }


def _latest_target(targets: pd.DataFrame) -> dict[str, float]:
    row = targets.sort_values("effective_ts").iloc[-1]
    return {market: float(row[market]) for market in MARKETS}


def rank_strategies(
    returns: pd.DataFrame,
    targets: dict[str, pd.DataFrame],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    seed_end = _utc_ts(config["seed_end"])
    initial = float(config.get("initial_equity", 1_000_000.0))
    cost_bps = float(config.get("rebalance_cost_bps", 10.0))
    annualization_days = int(config.get("annualization_days", 365))

    rows: list[dict[str, Any]] = []
    for strategy in STRATEGIES:
        equity = simulate_portfolio(
            returns,
            targets[strategy],
            initial_equity=initial,
            cost_bps=cost_bps,
        )
        metrics = forward_metrics(
            equity,
            seed_end=seed_end,
            initial_equity=initial,
            annualization_days=annualization_days,
        )
        row: dict[str, Any] = {
            "strategy": strategy,
            "latest_target": _latest_target(targets[strategy]),
        }
        if metrics is None:
            row["status"] = "WAITING_FOR_FORWARD_DATA"
        else:
            row.update({"status": "READY", **metrics})
        rows.append(row)

    ready = [x for x in rows if x["status"] == "READY"]
    if not ready:
        return rows, "WAITING_FOR_FORWARD_DATA"

    min_forward_observations = int(
        config.get("min_forward_observations_for_rank", 60)
    )
    min_forward_rebalances = int(
        config.get("min_forward_rebalances_for_rank", 2)
    )
    for row in rows:
        observations = int(row.get("observations") or 0)
        rebalances = int(row.get("rebalance_count") or 0)
        eligible = (
            row.get("status") == "READY"
            and observations >= min_forward_observations
            and rebalances >= min_forward_rebalances
        )
        row["rank_eligible"] = bool(eligible)
        row["annualized_metrics_interpretable"] = bool(eligible)
        row["rank_gate"] = {
            "minimum_forward_observations": min_forward_observations,
            "minimum_forward_rebalances": min_forward_rebalances,
            "observations": observations,
            "rebalance_count": rebalances,
        }
        row["forward_rank"] = None

    if not all(bool(row.get("rank_eligible")) for row in ready):
        return rows, "TRACKING_INSUFFICIENT_FORWARD_HISTORY"

    def key(row: dict[str, Any]) -> tuple[float, float, float]:
        sharpe = row.get("sharpe")
        return (
            float(sharpe) if sharpe is not None else -999.0,
            float(row.get("max_drawdown") or -999.0),
            float(row.get("total_return") or -999.0),
        )

    ordered = sorted(ready, key=key, reverse=True)
    order = {row["strategy"]: i for i, row in enumerate(ordered)}
    for row in rows:
        row["forward_rank"] = order.get(row["strategy"])
    rows.sort(key=lambda x: x.get("forward_rank") if x.get("forward_rank") is not None else 999)
    return rows, "RANKING_ACTIVE"


def build_snapshot(
    *,
    market_root: Path,
    config_path: Path,
    code_sha: str,
) -> tuple[dict[str, Any], dict[str, pd.DataFrame], pd.DataFrame]:
    config = _load_json(config_path)
    returns, market_as_of, data_end = build_return_panel(market_root, config)
    targets, gate_audit = build_targets(returns, config)
    ranking, tracking_status = rank_strategies(returns, targets, config)
    latest_risk_cap_audit: dict[str, Any] | None = None
    if not gate_audit.empty:
        latest = gate_audit.sort_values("effective_ts").iloc[-1].to_dict()
        latest_risk_cap_audit = {
            key: (
                value.item()
                if isinstance(value, np.generic)
                else value
            )
            for key, value in latest.items()
        }
        for row in ranking:
            if row.get("strategy") == "C_RISK_CAP_110":
                row["risk_cap_audit"] = latest_risk_cap_audit
    seed_end = _utc_ts(config["seed_end"])
    post_seed_rows = int((returns.index > seed_end).sum())

    snapshot = {
        "schema_version": "kalman-shadow-portfolio-ranking-v2",
        "status": "READY",
        "tracking_status": tracking_status,
        "experiment": "FORWARD_SHADOW_PORTFOLIO_V2",
        "source_version": str(config.get("version") or "shadow_portfolio_ranking_v2"),
        "code_sha": code_sha,
        "seed_end": seed_end,
        "data_as_of": data_end,
        "market_data_as_of": market_as_of,
        "post_seed_return_rows": post_seed_rows,
        "strategies": {
            "A_EQUAL_WEIGHT": "monthly_equal_weight",
            "B_STATIC_MAX_SHARPE": "monthly_deterministic_long_only_max_sharpe",
            "C_RISK_CAP_110": "monthly_blend_max_sharpe_capped_at_110pct_equal_weight_vol",
        },
        "configuration": {
            "lookback_days": int(config.get("lookback_days", 180)),
            "min_observations": int(config.get("min_observations", 90)),
            "rebalance_frequency": "M",
            "rebalance_cost_bps": float(config.get("rebalance_cost_bps", 10.0)),
            "annualization_days": int(config.get("annualization_days", 365)),
            "initial_equity": float(config.get("initial_equity", 1_000_000.0)),
            "risk_cap_ratio": float(config.get("risk_cap_ratio", 1.10)),
            "simplex_step": float(config.get("simplex_step", 0.002)),
            "min_forward_observations_for_rank": int(
                config.get("min_forward_observations_for_rank", 60)
            ),
            "min_forward_rebalances_for_rank": int(
                config.get("min_forward_rebalances_for_rank", 2)
            ),
            "max_wall_clock_age_days": {
                market: (config.get("market_files") or {}).get(market, {}).get(
                    "max_wall_clock_age_days"
                )
                for market in MARKETS
            },
        },
        "forward_ranking": ranking,
        "risk_cap_audit_latest": latest_risk_cap_audit,
        "invariants": {
            "research_only": True,
            "entry_allowed_for_real_orders": False,
            "auto_trade_visible": False,
            "production_model_write": False,
            "strategy_signal_write": False,
            "dashboard_snapshot_write": False,
            "toss_execution": False,
            "live_execution": False,
            "trade_execution": False,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return snapshot, targets, gate_audit


def write_outputs(
    snapshot: dict[str, Any],
    targets: dict[str, pd.DataFrame],
    gate_audit: pd.DataFrame,
    output_dir: Path,
) -> None:
    latest = output_dir / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    _write_json(latest / "ranking.json", snapshot)

    for strategy, frame in targets.items():
        target_path = latest / f"{strategy.lower()}_targets.parquet"
        frame.to_parquet(target_path, index=False)
    gate_audit.to_csv(latest / "c_risk_cap_110_audit.csv", index=False)

    date_key = _utc_ts(snapshot["data_as_of"]).strftime("%Y-%m-%d")
    _write_json(output_dir / "history" / date_key / "ranking.json", snapshot)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kalman SHADOW A/B/C portfolio ranking V2")
    p.add_argument("--market-root", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--code-sha", default="unknown")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    snapshot, targets, audit = build_snapshot(
        market_root=Path(args.market_root).expanduser(),
        config_path=Path(args.config).expanduser(),
        code_sha=str(args.code_sha),
    )
    write_outputs(snapshot, targets, audit, Path(args.output_dir).expanduser())
    print(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
