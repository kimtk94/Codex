from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, brier_score_loss, roc_auc_score

from .contracts import BacktestConfig, stable_hash
from .historical_backfill import (
    NON_FEATURE_COLUMNS,
    _decision_signals,
    _fit_model,
    _predict_probability,
)
from .native_ledger import performance_metrics, run_backtest
from .portfolio_targets import (
    build_rolling_portfolio_targets,
    portfolio_equity_from_targets,
    portfolio_metrics,
)


MARKETS = ("US", "KR", "BTC")


@dataclass(frozen=True)
class OuterFold:
    fold_id: int
    development_start: str
    development_end: str
    test_start: str
    test_end: str
    purge_observations: int


@dataclass(frozen=True)
class InnerFold:
    fold_id: int
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    purge_observations: int


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _safe_metric(fn: Any, *args: Any, **kwargs: Any) -> float | None:
    try:
        value = float(fn(*args, **kwargs))
    except Exception:
        return None
    return value if math.isfinite(value) else None


def _feature_columns(frame: pd.DataFrame, spec: dict[str, Any]) -> list[str]:
    suffixes = tuple(str(x) for x in spec.get("excluded_feature_suffixes", []))
    out: list[str] = []
    for col in frame.columns:
        if col in NON_FEATURE_COLUMNS:
            continue
        if suffixes and str(col).endswith(suffixes):
            continue
        out.append(str(col))
    return out


def robust_select_features(
    train: pd.DataFrame,
    *,
    spec: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    y = pd.to_numeric(train["target_label"], errors="coerce")
    minimum_coverage = float(spec.get("minimum_feature_coverage", 0.80))
    maximum_features = int(spec.get("maximum_features", 32))
    variance_floor = float(spec.get("near_zero_variance_threshold", 1e-12))
    max_pair_corr = float(spec.get("max_pairwise_feature_correlation", 0.95))
    stability_blocks = max(2, int(spec.get("stability_blocks", 4)))

    ranked: list[dict[str, Any]] = []
    numeric_cache: dict[str, pd.Series] = {}

    block_indices = [
        np.asarray(x, dtype=int)
        for x in np.array_split(np.arange(len(train)), stability_blocks)
        if len(x) >= 20
    ]

    for col in _feature_columns(train, spec):
        x = pd.to_numeric(train[col], errors="coerce")
        coverage = float(x.notna().mean())
        if coverage < minimum_coverage:
            continue

        median = x.median()
        if pd.isna(median):
            continue
        filled = x.fillna(median).astype(float)
        if filled.nunique(dropna=True) <= 1:
            continue
        variance = float(np.nanvar(filled.to_numpy(dtype=float)))
        if not math.isfinite(variance) or variance <= variance_floor:
            continue

        corr = filled.corr(y)
        corr_value = float(corr) if corr is not None and np.isfinite(corr) else 0.0
        if corr_value == 0.0:
            continue

        block_corrs: list[float] = []
        for idx in block_indices:
            block_y = y.iloc[idx]
            block_x = filled.iloc[idx]
            if block_y.nunique(dropna=True) < 2 or block_x.nunique(dropna=True) < 2:
                continue
            block_corr = block_x.corr(block_y)
            if block_corr is not None and np.isfinite(block_corr):
                block_corrs.append(float(block_corr))

        if block_corrs:
            full_sign = 1.0 if corr_value > 0 else -1.0
            sign_agreement = float(
                np.mean([(1.0 if value > 0 else -1.0) == full_sign for value in block_corrs])
            )
            median_abs_block_corr = float(np.median(np.abs(block_corrs)))
        else:
            sign_agreement = 0.0
            median_abs_block_corr = 0.0

        score = abs(corr_value) * (0.50 + 0.50 * sign_agreement) + 0.25 * median_abs_block_corr
        ranked.append(
            {
                "feature": col,
                "coverage": coverage,
                "variance": variance,
                "train_corr": corr_value,
                "sign_agreement": sign_agreement,
                "median_abs_block_corr": median_abs_block_corr,
                "selector_score": float(score),
            }
        )
        numeric_cache[col] = filled

    ranked.sort(
        key=lambda row: (
            -float(row["selector_score"]),
            -float(row["sign_agreement"]),
            str(row["feature"]),
        )
    )

    selected: list[str] = []
    diagnostics: list[dict[str, Any]] = []
    for row in ranked:
        feature = str(row["feature"])
        redundant_with: str | None = None
        max_seen_corr = 0.0
        for chosen in selected:
            pair_corr = numeric_cache[feature].corr(numeric_cache[chosen])
            pair_abs = abs(float(pair_corr)) if pair_corr is not None and np.isfinite(pair_corr) else 0.0
            max_seen_corr = max(max_seen_corr, pair_abs)
            if pair_abs >= max_pair_corr:
                redundant_with = chosen
                break

        diagnostic = dict(row)
        diagnostic["max_pairwise_corr_to_selected"] = max_seen_corr
        diagnostic["redundant_with"] = redundant_with
        diagnostic["selected"] = redundant_with is None and len(selected) < maximum_features
        diagnostics.append(diagnostic)

        if redundant_with is not None:
            continue
        if len(selected) >= maximum_features:
            continue
        selected.append(feature)

    if len(selected) < 5:
        raise RuntimeError(f"too few V2 features selected: {len(selected)}")
    return selected, diagnostics


def generate_outer_folds(
    timestamps: pd.Series,
    *,
    development_observations: int,
    test_observations: int,
    purge_observations: int,
) -> list[OuterFold]:
    idx = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True, errors="raise"))
    idx = idx.drop_duplicates().sort_values()
    folds: list[OuterFold] = []
    cursor = int(development_observations)
    fold_id = 0

    while True:
        test_start_i = cursor + int(purge_observations)
        test_end_i = test_start_i + int(test_observations) - 1
        if test_end_i >= len(idx):
            break
        folds.append(
            OuterFold(
                fold_id=fold_id,
                development_start=idx[0].isoformat(),
                development_end=idx[cursor - 1].isoformat(),
                test_start=idx[test_start_i].isoformat(),
                test_end=idx[test_end_i].isoformat(),
                purge_observations=int(purge_observations),
            )
        )
        fold_id += 1
        cursor += int(test_observations)

    return folds


def generate_inner_folds(
    development: pd.DataFrame,
    *,
    train_observations: int,
    validation_observations: int,
    purge_observations: int,
) -> list[InnerFold]:
    idx = pd.DatetimeIndex(pd.to_datetime(development["as_of"], utc=True, errors="raise"))
    folds: list[InnerFold] = []
    cursor = int(train_observations)
    fold_id = 0

    while True:
        validation_start_i = cursor + int(purge_observations)
        validation_end_i = validation_start_i + int(validation_observations) - 1
        if validation_end_i >= len(idx):
            break
        folds.append(
            InnerFold(
                fold_id=fold_id,
                train_start=idx[0].isoformat(),
                train_end=idx[cursor - 1].isoformat(),
                validation_start=idx[validation_start_i].isoformat(),
                validation_end=idx[validation_end_i].isoformat(),
                purge_observations=int(purge_observations),
            )
        )
        fold_id += 1
        cursor += int(validation_observations)

    return folds


def _slice_inner(
    development: pd.DataFrame,
    fold: InnerFold,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = development.loc[
        (development["as_of"] >= pd.Timestamp(fold.train_start))
        & (development["as_of"] <= pd.Timestamp(fold.train_end))
    ].copy()
    validation = development.loc[
        (development["as_of"] >= pd.Timestamp(fold.validation_start))
        & (development["as_of"] <= pd.Timestamp(fold.validation_end))
    ].copy()
    return train, validation


def _nested_feature_consensus(
    development: pd.DataFrame,
    *,
    spec: dict[str, Any],
    purge_observations: int,
) -> tuple[list[str], list[dict[str, Any]], list[InnerFold]]:
    inner_folds = generate_inner_folds(
        development,
        train_observations=int(spec.get("inner_train_observations", 504)),
        validation_observations=int(spec.get("inner_validation_observations", 63)),
        purge_observations=purge_observations,
    )
    if not inner_folds:
        raise RuntimeError("no inner walk-forward folds")

    votes: dict[str, dict[str, Any]] = {}
    fold_diagnostics: list[dict[str, Any]] = []

    for fold in inner_folds:
        inner_train, inner_validation = _slice_inner(development, fold)
        if min(len(inner_train), len(inner_validation)) < 20:
            continue
        if inner_train["target_label"].nunique() < 2 or inner_validation["target_label"].nunique() < 2:
            continue

        features, diagnostics = robust_select_features(inner_train, spec=spec)
        diag_map = {str(row["feature"]): row for row in diagnostics}
        fold_diagnostics.append(
            {
                "fold": asdict(fold),
                "selected_features": features,
                "selector_diagnostics": diagnostics,
            }
        )

        for feature in features:
            bucket = votes.setdefault(
                feature,
                {"selected_count": 0, "scores": [], "sign_agreements": []},
            )
            bucket["selected_count"] += 1
            row = diag_map.get(feature, {})
            bucket["scores"].append(float(row.get("selector_score", 0.0)))
            bucket["sign_agreements"].append(float(row.get("sign_agreement", 0.0)))

    usable_fold_count = len(fold_diagnostics)
    if usable_fold_count == 0:
        raise RuntimeError("no usable inner folds")

    ranking: list[dict[str, Any]] = []
    for feature, bucket in votes.items():
        ranking.append(
            {
                "feature": feature,
                "selected_count": int(bucket["selected_count"]),
                "selection_frequency": float(bucket["selected_count"]) / usable_fold_count,
                "mean_selector_score": float(np.mean(bucket["scores"])),
                "mean_sign_agreement": float(np.mean(bucket["sign_agreements"])),
            }
        )

    ranking.sort(
        key=lambda row: (
            -float(row["selection_frequency"]),
            -float(row["mean_selector_score"]),
            -float(row["mean_sign_agreement"]),
            str(row["feature"]),
        )
    )

    maximum_features = int(spec.get("maximum_features", 32))
    stable = [row for row in ranking if float(row["selection_frequency"]) >= 0.50]
    chosen_rows = stable[:maximum_features]
    if len(chosen_rows) < 5:
        chosen_rows = ranking[:maximum_features]

    features = [str(row["feature"]) for row in chosen_rows]
    if len(features) < 5:
        raise RuntimeError(f"too few nested consensus features: {len(features)}")

    return features, ranking, inner_folds


def _tune_inner_model(
    development: pd.DataFrame,
    *,
    features: list[str],
    inner_folds: list[InnerFold],
    spec: dict[str, Any],
) -> tuple[float, float, list[dict[str, Any]], list[dict[str, Any]]]:
    candidate_c = [float(x) for x in spec.get("candidate_c", [0.1])]
    thresholds = [float(x) for x in spec.get("threshold_grid", [0.50, 0.55, 0.60])]
    c_rows: list[dict[str, Any]] = []

    for c_value in candidate_c:
        aucs: list[float] = []
        briers: list[float] = []
        for fold in inner_folds:
            inner_train, inner_validation = _slice_inner(development, fold)
            if min(len(inner_train), len(inner_validation)) < 20:
                continue
            if inner_train["target_label"].nunique() < 2 or inner_validation["target_label"].nunique() < 2:
                continue
            imputer, scaler, model = _fit_model(inner_train, features, c_value=c_value)
            prob = _predict_probability(inner_validation, features, imputer, scaler, model)
            y = pd.to_numeric(inner_validation["target_label"], errors="raise").astype(int)
            auc = _safe_metric(roc_auc_score, y, prob)
            brier = _safe_metric(brier_score_loss, y, prob)
            if auc is not None:
                aucs.append(auc)
            if brier is not None:
                briers.append(brier)

        c_rows.append(
            {
                "c": c_value,
                "mean_validation_roc_auc": float(np.mean(aucs)) if aucs else None,
                "mean_validation_brier": float(np.mean(briers)) if briers else None,
                "validation_fold_count": len(aucs),
            }
        )

    c_rows.sort(
        key=lambda row: (
            float(row["mean_validation_roc_auc"]) if row["mean_validation_roc_auc"] is not None else -1.0,
            -(float(row["mean_validation_brier"]) if row["mean_validation_brier"] is not None else 999.0),
            -float(row["c"]),
        ),
        reverse=True,
    )
    best_c = float(c_rows[0]["c"])

    pooled_y: list[int] = []
    pooled_prob: list[float] = []
    for fold in inner_folds:
        inner_train, inner_validation = _slice_inner(development, fold)
        if min(len(inner_train), len(inner_validation)) < 20:
            continue
        if inner_train["target_label"].nunique() < 2 or inner_validation["target_label"].nunique() < 2:
            continue
        imputer, scaler, model = _fit_model(inner_train, features, c_value=best_c)
        prob = _predict_probability(inner_validation, features, imputer, scaler, model)
        pooled_y.extend(
            pd.to_numeric(inner_validation["target_label"], errors="raise").astype(int).tolist()
        )
        pooled_prob.extend([float(x) for x in prob])

    y_array = np.asarray(pooled_y, dtype=int)
    p_array = np.asarray(pooled_prob, dtype=float)
    threshold_rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        pred = (p_array >= threshold).astype(int)
        threshold_rows.append(
            {
                "threshold": threshold,
                "balanced_accuracy": _safe_metric(balanced_accuracy_score, y_array, pred),
            }
        )
    threshold_rows.sort(
        key=lambda row: (
            float(row["balanced_accuracy"]) if row["balanced_accuracy"] is not None else -1.0,
            -abs(float(row["threshold"]) - 0.55),
        ),
        reverse=True,
    )
    best_threshold = float(threshold_rows[0]["threshold"])
    return best_c, best_threshold, c_rows, threshold_rows


def _test_metrics(
    test: pd.DataFrame,
    probability: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    y = pd.to_numeric(test["target_label"], errors="raise").astype(int)
    pred = (probability >= threshold).astype(int)
    ret = pd.to_numeric(test["target_forward_return"], errors="coerce").to_numpy(dtype=float)
    selected = ret[pred == 1]
    selected = selected[np.isfinite(selected)]
    return {
        "rows": int(len(test)),
        "positive_rate": float(np.mean(y)),
        "selection_rate": float(np.mean(pred)),
        "roc_auc": _safe_metric(roc_auc_score, y, probability),
        "brier": _safe_metric(brier_score_loss, y, probability),
        "balanced_accuracy": _safe_metric(balanced_accuracy_score, y, pred),
        "selected_forward_return_mean": float(np.mean(selected)) if len(selected) else None,
        "selected_forward_return_win_rate": float(np.mean(selected > 0)) if len(selected) else None,
    }


def _load_prices(matrix_dir: Path, market: str, symbol: str) -> pd.DataFrame:
    path = matrix_dir / f"{market.lower()}_anchor_prices.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    raw = pd.read_parquet(path)
    required = {"timestamp", "open", "close"}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"{path} missing columns: {sorted(missing)}")
    out = pd.DataFrame(
        {
            "symbol": symbol,
            "ts": pd.to_datetime(raw["timestamp"], utc=True, errors="raise"),
            "open": pd.to_numeric(raw["open"], errors="coerce"),
            "close": pd.to_numeric(raw["close"], errors="coerce"),
        }
    )
    return out.dropna().sort_values("ts").drop_duplicates("ts", keep="last")


def _buy_hold_equity(
    prices: pd.DataFrame,
    *,
    initial_cash: float,
    position_fraction: float,
    commission_bps: float,
    slippage_bps: float,
) -> pd.DataFrame:
    p = prices.sort_values("ts").reset_index(drop=True)
    if p.empty:
        raise RuntimeError("empty prices")
    fee_rate = commission_bps / 10_000.0
    entry_price = float(p.iloc[0]["open"]) * (1.0 + slippage_bps / 10_000.0)
    budget = initial_cash * float(position_fraction)
    qty = budget / (entry_price * (1.0 + fee_rate))
    entry_notional = qty * entry_price
    entry_fee = entry_notional * fee_rate
    cash = initial_cash - entry_notional - entry_fee

    rows: list[dict[str, Any]] = [
        {
            "ts": pd.Timestamp(p.iloc[0]["ts"]) - pd.Timedelta(days=1),
            "cash": initial_cash,
            "position_value": 0.0,
            "equity": initial_cash,
            "open_positions": 0,
        }
    ]
    for i, row in p.iterrows():
        close = float(row["close"])
        position_value = qty * close
        equity = cash + position_value
        if i == len(p) - 1:
            exit_price = close * (1.0 - slippage_bps / 10_000.0)
            exit_notional = qty * exit_price
            exit_fee = exit_notional * fee_rate
            equity = cash + exit_notional - exit_fee
        rows.append(
            {
                "ts": row["ts"],
                "cash": cash,
                "position_value": position_value,
                "equity": equity,
                "open_positions": 1,
            }
        )
    return pd.DataFrame(rows)


def _vol_matched_equity(
    prices: pd.DataFrame,
    *,
    initial_cash: float,
    target_volatility: float,
) -> tuple[pd.DataFrame, float]:
    p = prices.sort_values("ts").copy()
    close = pd.Series(
        pd.to_numeric(p["close"], errors="coerce").to_numpy(dtype=float),
        index=pd.DatetimeIndex(pd.to_datetime(p["ts"], utc=True)),
    ).dropna()
    daily = close.resample("1D").last().dropna()
    returns = daily.pct_change().fillna(0.0)
    benchmark_vol = float(returns.std(ddof=0) * np.sqrt(252)) if len(returns) > 1 else 0.0
    scale = 0.0 if benchmark_vol <= 0 else max(0.0, min(1.0, target_volatility / benchmark_vol))
    equity = initial_cash * (1.0 + returns * scale).cumprod()
    frame = pd.DataFrame(
        {
            "ts": equity.index,
            "cash": 0.0,
            "position_value": equity.to_numpy(dtype=float),
            "equity": equity.to_numpy(dtype=float),
            "open_positions": 1,
        }
    )
    return frame, scale


def _fold_metric_summary(fold_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    aucs = [
        float(row["test_metrics"]["roc_auc"])
        for row in fold_metrics
        if row["test_metrics"].get("roc_auc") is not None
    ]
    bals = [
        float(row["test_metrics"]["balanced_accuracy"])
        for row in fold_metrics
        if row["test_metrics"].get("balanced_accuracy") is not None
    ]
    return {
        "fold_count": len(fold_metrics),
        "mean_test_roc_auc": float(np.mean(aucs)) if aucs else None,
        "median_test_roc_auc": float(np.median(aucs)) if aucs else None,
        "test_auc_above_0_5_count": int(np.sum(np.asarray(aucs) > 0.5)) if aucs else 0,
        "mean_test_balanced_accuracy": float(np.mean(bals)) if bals else None,
    }


def run_market_candidate(
    *,
    market: str,
    matrix_dir: Path,
    output_root: Path,
    spec: dict[str, Any],
    git_sha: str,
) -> dict[str, Any]:
    market_spec = spec["markets"][market]
    symbol = str(market_spec["symbol"])
    horizon = int(market_spec["horizon_observations"])

    matrix_path = matrix_dir / f"{market.lower()}_matrix.parquet"
    frame = pd.read_parquet(matrix_path)
    frame["as_of"] = pd.to_datetime(frame["as_of"], utc=True, errors="raise")
    frame = (
        frame.sort_values("as_of")
        .drop_duplicates("as_of", keep="last")
        .loc[lambda x: x["target_label"].notna()]
        .reset_index(drop=True)
    )

    outer_folds = generate_outer_folds(
        frame["as_of"],
        development_observations=int(spec.get("outer_development_observations", 756)),
        test_observations=int(spec.get("outer_test_observations", 126)),
        purge_observations=horizon,
    )
    if not outer_folds:
        raise RuntimeError(f"{market}: no outer folds")

    model_outputs: list[pd.DataFrame] = []
    fold_metrics: list[dict[str, Any]] = []

    for outer in outer_folds:
        development = frame.loc[
            (frame["as_of"] >= pd.Timestamp(outer.development_start))
            & (frame["as_of"] <= pd.Timestamp(outer.development_end))
        ].copy()
        test = frame.loc[
            (frame["as_of"] >= pd.Timestamp(outer.test_start))
            & (frame["as_of"] <= pd.Timestamp(outer.test_end))
        ].copy()
        if min(len(development), len(test)) < 20:
            continue

        features, consensus_ranking, inner_folds = _nested_feature_consensus(
            development,
            spec=spec,
            purge_observations=horizon,
        )
        best_c, threshold, c_rows, threshold_rows = _tune_inner_model(
            development,
            features=features,
            inner_folds=inner_folds,
            spec=spec,
        )

        imputer, scaler, model = _fit_model(development, features, c_value=best_c)
        probability = _predict_probability(test, features, imputer, scaler, model)
        parameter_hash = stable_hash(
            {
                "version": spec["version"],
                "market": market,
                "outer_fold": asdict(outer),
                "features": features,
                "c": best_c,
                "threshold": threshold,
            }
        )
        run_id = f"{market.lower()}-v2-f{outer.fold_id:03d}-{parameter_hash[:12]}"
        model_outputs.append(
            pd.DataFrame(
                {
                    "run_id": run_id,
                    "market": market,
                    "symbol": symbol,
                    "as_of": test["as_of"].to_numpy(),
                    "fold_id": outer.fold_id,
                    "model_version": spec["version"],
                    "feature_version": spec["feature_set"],
                    "probability": probability,
                    "score": probability,
                    "probability_threshold": threshold,
                    "parameter_hash": parameter_hash,
                }
            )
        )

        fold_metrics.append(
            {
                "outer_fold": asdict(outer),
                "run_id": run_id,
                "selected_feature_count": len(features),
                "selected_features": features,
                "feature_consensus_ranking": consensus_ranking,
                "inner_fold_count": len(inner_folds),
                "best_c": best_c,
                "candidate_c_metrics": c_rows,
                "threshold": threshold,
                "threshold_metrics": threshold_rows,
                "test_metrics": _test_metrics(test, probability, threshold),
            }
        )

    if not model_outputs:
        raise RuntimeError(f"{market}: no completed V2 outer folds")

    model_output = (
        pd.concat(model_outputs, ignore_index=True)
        .sort_values("as_of")
        .drop_duplicates(["market", "symbol", "as_of"], keep="last")
        .reset_index(drop=True)
    )
    strategy_signal = _decision_signals(model_output, symbol=symbol)
    prices = _load_prices(matrix_dir, market, symbol)

    market_dir = output_root / market.lower()
    market_dir.mkdir(parents=True, exist_ok=True)
    model_output.to_parquet(market_dir / "historical_model_output.parquet", index=False)
    strategy_signal.to_parquet(market_dir / "historical_strategy_signal.parquet", index=False)
    _write_json(market_dir / "fold_metrics.json", fold_metrics)

    commission_bps = float(spec.get("commission_bps", 5.0))
    slippage_bps = float(spec.get("slippage_bps", 5.0))
    max_hold_bars = int(spec.get("max_hold_bars", 20))
    initial_cash = 1_000_000.0
    backtests: dict[str, Any] = {}

    for fraction in [float(x) for x in spec.get("position_fractions", [0.10, 1.00])]:
        key = f"{int(round(fraction * 100))}pct"
        result = run_backtest(
            strategy_signal[["symbol", "signal_ts", "signal", "entry_allowed"]],
            prices,
            BacktestConfig(
                initial_cash=initial_cash,
                position_fraction=fraction,
                max_open_positions=1,
                commission_bps=commission_bps,
                slippage_bps=slippage_bps,
                max_hold_bars=max_hold_bars,
                allow_fractional=True,
            ),
        )
        result.trades.to_parquet(market_dir / f"strategy_{key}_trades.parquet", index=False)
        result.equity.to_parquet(market_dir / f"strategy_{key}_equity.parquet", index=False)

        bh_equity = _buy_hold_equity(
            prices,
            initial_cash=initial_cash,
            position_fraction=fraction,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
        )
        bh_metrics = performance_metrics(pd.DataFrame(), bh_equity)
        bh_equity.to_parquet(market_dir / f"buy_hold_{key}_equity.parquet", index=False)

        backtests[key] = {
            "strategy": result.metrics,
            "buy_hold": bh_metrics,
        }

    strategy_100 = backtests.get("100pct", {}).get("strategy", {})
    target_vol = float(strategy_100.get("annualized_volatility") or 0.0)
    vol_equity, vol_scale = _vol_matched_equity(
        prices,
        initial_cash=initial_cash,
        target_volatility=target_vol,
    )
    vol_metrics = performance_metrics(pd.DataFrame(), vol_equity)
    vol_equity.to_parquet(market_dir / "buy_hold_vol_matched_equity.parquet", index=False)

    summary = {
        "status": "READY",
        "market": market,
        "symbol": symbol,
        "git_sha": git_sha,
        "model_version": spec["version"],
        "feature_version": spec["feature_set"],
        "outer_walk_forward": _fold_metric_summary(fold_metrics),
        "model_output_rows": int(len(model_output)),
        "signal_counts": strategy_signal["signal"].value_counts().to_dict(),
        "backtests": backtests,
        "vol_matched_buy_hold": {
            "scale": vol_scale,
            "metrics": vol_metrics,
        },
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _write_json(market_dir / "candidate_summary.json", summary)
    return summary


def run_candidate_portfolios(output_root: Path) -> dict[str, Any]:
    returns: dict[str, pd.Series] = {}
    for market in MARKETS:
        path = output_root / market.lower() / "strategy_100pct_equity.parquet"
        if not path.exists():
            continue
        equity = pd.read_parquet(path)
        ts = pd.to_datetime(equity["ts"], utc=True, errors="raise")
        values = pd.Series(pd.to_numeric(equity["equity"], errors="coerce").to_numpy(), index=ts)
        daily = values.resample("1D").last().dropna()
        returns[market] = daily.pct_change()

    if len(returns) < 2:
        raise RuntimeError("candidate portfolio layer requires at least two markets")

    return_frame = pd.DataFrame(returns).sort_index()
    root = output_root / "portfolio"
    rows: list[dict[str, Any]] = []
    for method in ("equal_weight", "inverse_volatility", "hrp"):
        targets = build_rolling_portfolio_targets(
            return_frame,
            method=method,
            lookback_days=180,
            min_observations=90,
            rebalance_frequency="M",
        )
        equity = portfolio_equity_from_targets(return_frame, targets)
        metrics = portfolio_metrics(equity)
        method_dir = root / method
        method_dir.mkdir(parents=True, exist_ok=True)
        targets.to_parquet(method_dir / "portfolio_target.parquet", index=False)
        equity.to_parquet(method_dir / "portfolio_equity.parquet", index=False)
        _write_json(method_dir / "portfolio_performance.json", metrics)
        rows.append({"method": method, **metrics})

    comparison = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    comparison.to_csv(root / "core_portfolio_comparison.csv", index=False)
    payload = {
        "status": "READY",
        "rows": comparison.to_dict("records"),
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _write_json(root / "core_portfolio_summary.json", payload)
    return payload


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Kalman Historical V2 nested candidate")
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--git-sha", required=True)
    p.add_argument("--market", action="append", choices=list(MARKETS))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    matrix_dir = Path(args.matrix_dir).expanduser()
    output_root = Path(args.output_dir).expanduser()
    spec = json.loads(Path(args.spec).expanduser().read_text(encoding="utf-8"))
    markets = args.market or list(MARKETS)

    status: dict[str, Any] = {
        "status": "READY",
        "version": spec["version"],
        "git_sha": args.git_sha,
        "markets": {},
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }

    for market in markets:
        try:
            status["markets"][market] = run_market_candidate(
                market=market,
                matrix_dir=matrix_dir,
                output_root=output_root,
                spec=spec,
                git_sha=args.git_sha,
            )
        except Exception as exc:
            status["status"] = "FAIL"
            status["markets"][market] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    ready = [m for m, row in status["markets"].items() if row.get("status") == "READY"]
    if len(ready) >= 2:
        try:
            status["portfolio"] = run_candidate_portfolios(output_root)
        except Exception as exc:
            status["status"] = "FAIL"
            status["portfolio"] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    _write_json(output_root / "candidate_run_status.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0 if status["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
