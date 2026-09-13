from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss, mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler

from .contracts import BacktestConfig, stable_hash
from .historical_backfill import NON_FEATURE_COLUMNS
from .historical_v2_candidate import (
    _buy_hold_equity,
    _load_prices,
    _slice_inner,
    _vol_matched_equity,
    generate_inner_folds,
    generate_outer_folds,
)
from .native_ledger import performance_metrics, run_backtest
from .portfolio_targets import (
    build_rolling_portfolio_targets,
    portfolio_equity_from_targets,
    portfolio_metrics,
)

MARKETS = ("US", "KR", "BTC")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def _corr(x: np.ndarray, y: np.ndarray) -> float | None:
    mask = np.isfinite(x) & np.isfinite(y)
    if int(mask.sum()) < 5:
        return None
    xx = x[mask]
    yy = y[mask]
    if np.std(xx) <= 0 or np.std(yy) <= 0:
        return None
    return _safe_float(np.corrcoef(xx, yy)[0, 1])


def _candidate_features(frame: pd.DataFrame, spec: dict[str, Any]) -> list[str]:
    suffixes = tuple(str(x) for x in spec.get("excluded_feature_suffixes", []))
    out: list[str] = []
    for col in frame.columns:
        if col in NON_FEATURE_COLUMNS:
            continue
        if suffixes and str(col).endswith(suffixes):
            continue
        out.append(str(col))
    return out


def select_return_features(
    train: pd.DataFrame,
    *,
    spec: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    target = pd.to_numeric(train["target_forward_return"], errors="coerce")
    minimum_coverage = float(spec.get("minimum_feature_coverage", 0.80))
    maximum_features = int(spec.get("maximum_features", 24))
    variance_floor = float(spec.get("near_zero_variance_threshold", 1e-12))
    max_pair_corr = float(spec.get("max_pairwise_feature_correlation", 0.90))
    stability_blocks = max(2, int(spec.get("stability_blocks", 4)))

    block_indices = [
        np.asarray(part, dtype=int)
        for part in np.array_split(np.arange(len(train)), stability_blocks)
        if len(part) >= 20
    ]
    ranked: list[dict[str, Any]] = []
    numeric_cache: dict[str, pd.Series] = {}

    for col in _candidate_features(train, spec):
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

        full_corr = filled.corr(target)
        corr_value = float(full_corr) if full_corr is not None and np.isfinite(full_corr) else 0.0
        if corr_value == 0.0:
            continue

        block_corrs: list[float] = []
        for idx in block_indices:
            block_x = filled.iloc[idx]
            block_y = target.iloc[idx]
            valid = block_x.notna() & block_y.notna()
            if int(valid.sum()) < 10:
                continue
            value = block_x.loc[valid].corr(block_y.loc[valid])
            if value is not None and np.isfinite(value):
                block_corrs.append(float(value))

        if block_corrs:
            full_sign = 1 if corr_value > 0 else -1
            sign_agreement = float(
                np.mean([(1 if value > 0 else -1) == full_sign for value in block_corrs])
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
                "train_return_corr": corr_value,
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
        max_seen = 0.0
        for chosen in selected:
            pair = numeric_cache[feature].corr(numeric_cache[chosen])
            pair_abs = abs(float(pair)) if pair is not None and np.isfinite(pair) else 0.0
            max_seen = max(max_seen, pair_abs)
            if pair_abs >= max_pair_corr:
                redundant_with = chosen
                break

        diag = dict(row)
        diag["max_pairwise_corr_to_selected"] = max_seen
        diag["redundant_with"] = redundant_with
        diag["selected"] = redundant_with is None and len(selected) < maximum_features
        diagnostics.append(diag)

        if redundant_with is None and len(selected) < maximum_features:
            selected.append(feature)

    if len(selected) < 5:
        raise RuntimeError(f"too few V3 return features selected: {len(selected)}")
    return selected, diagnostics


def nested_return_feature_consensus(
    development: pd.DataFrame,
    *,
    spec: dict[str, Any],
    purge_observations: int,
) -> tuple[list[str], list[dict[str, Any]], list[Any]]:
    inner_folds = generate_inner_folds(
        development,
        train_observations=int(spec.get("inner_train_observations", 504)),
        validation_observations=int(spec.get("inner_validation_observations", 63)),
        purge_observations=purge_observations,
    )
    if not inner_folds:
        raise RuntimeError("no V3 inner folds")

    votes: dict[str, dict[str, Any]] = {}
    usable: list[Any] = []
    for fold in inner_folds:
        train, validation = _slice_inner(development, fold)
        if min(len(train), len(validation)) < 20:
            continue
        features, diagnostics = select_return_features(train, spec=spec)
        diag_map = {str(row["feature"]): row for row in diagnostics}
        usable.append(fold)
        for feature in features:
            row = diag_map[feature]
            bucket = votes.setdefault(
                feature,
                {"selected_count": 0, "scores": [], "sign_agreements": []},
            )
            bucket["selected_count"] += 1
            bucket["scores"].append(float(row["selector_score"]))
            bucket["sign_agreements"].append(float(row["sign_agreement"]))

    if not usable:
        raise RuntimeError("no usable V3 inner folds")

    ranking: list[dict[str, Any]] = []
    for feature, bucket in votes.items():
        ranking.append(
            {
                "feature": feature,
                "selected_count": int(bucket["selected_count"]),
                "selection_frequency": float(bucket["selected_count"]) / len(usable),
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

    maximum = int(spec.get("maximum_features", 24))
    stable = [row for row in ranking if float(row["selection_frequency"]) >= 0.50]
    chosen = stable[:maximum] if len(stable) >= 5 else ranking[:maximum]
    features = [str(row["feature"]) for row in chosen]
    if len(features) < 5:
        raise RuntimeError("V3 consensus produced fewer than five features")
    return features, ranking, usable


def _fit_return_model(
    frame: pd.DataFrame,
    features: list[str],
    *,
    model_type: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    x = frame[features].apply(pd.to_numeric, errors="coerce")
    y = pd.to_numeric(frame["target_forward_return"], errors="raise").to_numpy(dtype=float)

    imputer = SimpleImputer(strategy="median")
    x_imp = imputer.fit_transform(x)
    model_type = model_type.upper()

    scaler: StandardScaler | None = None
    if model_type == "RIDGE":
        scaler = StandardScaler()
        x_fit = scaler.fit_transform(x_imp)
        model = Ridge(alpha=float(params["alpha"]))
    elif model_type == "ELASTIC_NET":
        scaler = StandardScaler()
        x_fit = scaler.fit_transform(x_imp)
        model = ElasticNet(
            alpha=float(params["alpha"]),
            l1_ratio=float(params["l1_ratio"]),
            max_iter=10000,
            random_state=42,
        )
    elif model_type == "HIST_GRADIENT_BOOSTING":
        x_fit = x_imp
        model = HistGradientBoostingRegressor(
            learning_rate=float(params["learning_rate"]),
            max_leaf_nodes=int(params["max_leaf_nodes"]),
            l2_regularization=float(params.get("l2_regularization", 1.0)),
            max_iter=200,
            min_samples_leaf=20,
            random_state=42,
        )
    else:
        raise ValueError(f"unsupported V3 model_type: {model_type}")

    model.fit(x_fit, y)
    return {
        "imputer": imputer,
        "scaler": scaler,
        "model": model,
        "model_type": model_type,
        "params": dict(params),
    }


def _predict_return(
    frame: pd.DataFrame,
    features: list[str],
    bundle: dict[str, Any],
) -> np.ndarray:
    x = frame[features].apply(pd.to_numeric, errors="coerce")
    x_imp = bundle["imputer"].transform(x)
    scaler = bundle.get("scaler")
    x_fit = scaler.transform(x_imp) if scaler is not None else x_imp
    return np.asarray(bundle["model"].predict(x_fit), dtype=float)


def _fit_regime_model(
    frame: pd.DataFrame,
    features: list[str],
    *,
    threshold: float,
    c_value: float,
) -> dict[str, Any]:
    x = frame[features].apply(pd.to_numeric, errors="coerce")
    y = (
        pd.to_numeric(frame["target_forward_return"], errors="raise").to_numpy(dtype=float)
        > float(threshold)
    ).astype(int)
    if len(np.unique(y)) < 2:
        raise RuntimeError("regime training fold has one class")

    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    x_std = scaler.fit_transform(imputer.fit_transform(x))
    model = LogisticRegression(
        C=float(c_value),
        penalty="l2",
        solver="lbfgs",
        class_weight="balanced",
        max_iter=3000,
        random_state=42,
    )
    model.fit(x_std, y)
    return {"imputer": imputer, "scaler": scaler, "model": model}


def _predict_regime(
    frame: pd.DataFrame,
    features: list[str],
    bundle: dict[str, Any],
) -> np.ndarray:
    x = frame[features].apply(pd.to_numeric, errors="coerce")
    x_std = bundle["scaler"].transform(bundle["imputer"].transform(x))
    return np.asarray(bundle["model"].predict_proba(x_std)[:, 1], dtype=float)


def tune_return_model(
    development: pd.DataFrame,
    *,
    features: list[str],
    inner_folds: list[Any],
    model_type: str,
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for params in candidates:
        ics: list[float] = []
        maes: list[float] = []
        for fold in inner_folds:
            train, validation = _slice_inner(development, fold)
            bundle = _fit_return_model(
                train,
                features,
                model_type=model_type,
                params=params,
            )
            pred = _predict_return(validation, features, bundle)
            actual = pd.to_numeric(
                validation["target_forward_return"], errors="coerce"
            ).to_numpy(dtype=float)
            ic = _corr(pred, actual)
            if ic is not None:
                ics.append(ic)
            mask = np.isfinite(pred) & np.isfinite(actual)
            if int(mask.sum()) > 0:
                maes.append(float(mean_absolute_error(actual[mask], pred[mask])))

        rows.append(
            {
                "params": dict(params),
                "mean_validation_return_ic": float(np.mean(ics)) if ics else None,
                "mean_validation_mae": float(np.mean(maes)) if maes else None,
                "fold_count": len(ics),
            }
        )

    rows.sort(
        key=lambda row: (
            float(row["mean_validation_return_ic"])
            if row["mean_validation_return_ic"] is not None
            else -999.0,
            -(float(row["mean_validation_mae"])
              if row["mean_validation_mae"] is not None
              else 999.0),
        ),
        reverse=True,
    )
    return dict(rows[0]["params"]), rows


def tune_regime_c(
    development: pd.DataFrame,
    *,
    features: list[str],
    inner_folds: list[Any],
    threshold: float,
    c_grid: list[float],
) -> tuple[float, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for c_value in c_grid:
        briers: list[float] = []
        for fold in inner_folds:
            train, validation = _slice_inner(development, fold)
            try:
                bundle = _fit_regime_model(
                    train,
                    features,
                    threshold=threshold,
                    c_value=c_value,
                )
            except RuntimeError:
                continue
            prob = _predict_regime(validation, features, bundle)
            y = (
                pd.to_numeric(
                    validation["target_forward_return"], errors="raise"
                ).to_numpy(dtype=float)
                > threshold
            ).astype(int)
            if len(np.unique(y)) < 2:
                continue
            briers.append(float(brier_score_loss(y, prob)))
        rows.append(
            {
                "c": float(c_value),
                "mean_validation_brier": float(np.mean(briers)) if briers else None,
                "fold_count": len(briers),
            }
        )

    rows.sort(
        key=lambda row: (
            -(float(row["mean_validation_brier"])
              if row["mean_validation_brier"] is not None
              else 999.0),
            -float(row["c"]),
        ),
        reverse=True,
    )
    return float(rows[0]["c"]), rows


def _validation_utility(
    actual: np.ndarray,
    active: np.ndarray,
    *,
    horizon: int,
    turnover_penalty: float,
    return_proxy_weight: float,
) -> dict[str, float | None]:
    actual = np.asarray(actual, dtype=float)
    active = np.asarray(active, dtype=bool)
    strategy = np.where(active, actual, 0.0)
    sd = float(np.std(strategy))
    scale = math.sqrt(252.0 / max(int(horizon), 1))
    sharpe_proxy = float(np.mean(strategy) / sd * scale) if sd > 0 else 0.0
    annual_return_proxy = float(np.mean(strategy) * 252.0 / max(int(horizon), 1))
    turnover = (
        float(np.mean(np.abs(np.diff(active.astype(float)))))
        if len(active) > 1
        else 0.0
    )
    selected = actual[active]
    selected_mean = float(np.mean(selected)) if len(selected) else None
    selected_win_rate = float(np.mean(selected > 0)) if len(selected) else None
    utility = (
        sharpe_proxy
        + return_proxy_weight * annual_return_proxy
        - turnover_penalty * turnover
    )
    return {
        "utility": float(utility),
        "sharpe_proxy": sharpe_proxy,
        "annual_return_proxy": annual_return_proxy,
        "turnover": turnover,
        "selection_rate": float(np.mean(active)),
        "selected_forward_return_mean": selected_mean,
        "selected_forward_return_win_rate": selected_win_rate,
    }


def tune_trading_gate(
    development: pd.DataFrame,
    *,
    features: list[str],
    inner_folds: list[Any],
    model_type: str,
    model_params: dict[str, Any],
    regime_return_threshold: float,
    regime_c: float,
    entry_quantiles: list[float],
    regime_probability_grid: list[float],
    horizon: int,
    turnover_penalty: float,
    return_proxy_weight: float,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    grid_rows: list[dict[str, Any]] = []
    cache: list[dict[str, Any]] = []

    for fold in inner_folds:
        train, validation = _slice_inner(development, fold)
        return_bundle = _fit_return_model(
            train,
            features,
            model_type=model_type,
            params=model_params,
        )
        try:
            regime_bundle = _fit_regime_model(
                train,
                features,
                threshold=regime_return_threshold,
                c_value=regime_c,
            )
        except RuntimeError:
            continue

        train_pred = _predict_return(train, features, return_bundle)
        valid_pred = _predict_return(validation, features, return_bundle)
        valid_regime = _predict_regime(validation, features, regime_bundle)
        actual = pd.to_numeric(
            validation["target_forward_return"], errors="coerce"
        ).to_numpy(dtype=float)

        cache.append(
            {
                "fold_id": int(fold.fold_id),
                "train_pred": train_pred,
                "valid_pred": valid_pred,
                "valid_regime": valid_regime,
                "actual": actual,
            }
        )

    if not cache:
        raise RuntimeError("no usable V3 inner folds for trading gate")

    for quantile in entry_quantiles:
        for regime_gate in regime_probability_grid:
            fold_rows: list[dict[str, Any]] = []
            for item in cache:
                threshold = float(np.quantile(item["train_pred"], quantile))
                active = (
                    (item["valid_pred"] >= threshold)
                    & (item["valid_regime"] >= float(regime_gate))
                )
                utility = _validation_utility(
                    item["actual"],
                    active,
                    horizon=horizon,
                    turnover_penalty=turnover_penalty,
                    return_proxy_weight=return_proxy_weight,
                )
                fold_rows.append(utility)

            grid_rows.append(
                {
                    "entry_quantile": float(quantile),
                    "regime_probability_gate": float(regime_gate),
                    "mean_utility": float(np.mean([row["utility"] for row in fold_rows])),
                    "mean_sharpe_proxy": float(
                        np.mean([row["sharpe_proxy"] for row in fold_rows])
                    ),
                    "mean_annual_return_proxy": float(
                        np.mean([row["annual_return_proxy"] for row in fold_rows])
                    ),
                    "mean_turnover": float(
                        np.mean([row["turnover"] for row in fold_rows])
                    ),
                    "mean_selection_rate": float(
                        np.mean([row["selection_rate"] for row in fold_rows])
                    ),
                    "fold_count": len(fold_rows),
                }
            )

    grid_rows.sort(
        key=lambda row: (
            float(row["mean_utility"]),
            float(row["mean_sharpe_proxy"]),
            -float(row["mean_turnover"]),
        ),
        reverse=True,
    )
    best = grid_rows[0]
    return {
        "entry_quantile": float(best["entry_quantile"]),
        "regime_probability_gate": float(best["regime_probability_gate"]),
    }, grid_rows


def build_signals(
    model_output: pd.DataFrame,
    *,
    symbol: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in model_output.sort_values("as_of").to_dict("records"):
        predicted_return = float(row["predicted_return"])
        regime_probability = float(row["regime_probability"])
        entry_threshold = float(row["entry_return_threshold"])
        regime_gate = float(row["regime_probability_gate"])
        exit_gate = max(0.40, regime_gate - 0.10)

        if predicted_return >= entry_threshold and regime_probability >= regime_gate:
            signal = "BUY"
            entry_allowed = True
        elif predicted_return <= 0.0 or regime_probability < exit_gate:
            signal = "SELL"
            entry_allowed = False
        else:
            signal = "HOLD"
            entry_allowed = False

        rows.append(
            {
                "symbol": symbol,
                "signal_ts": row["as_of"],
                "signal": signal,
                "entry_allowed": entry_allowed,
                "predicted_return": predicted_return,
                "regime_probability": regime_probability,
                "entry_return_threshold": entry_threshold,
                "regime_probability_gate": regime_gate,
                "fold_id": int(row["fold_id"]),
                "run_id": row["run_id"],
            }
        )
    return pd.DataFrame(rows)


def _outer_test_metrics(
    test: pd.DataFrame,
    predicted_return: np.ndarray,
    regime_probability: np.ndarray,
    *,
    regime_return_threshold: float,
    entry_threshold: float,
    regime_gate: float,
    horizon: int,
    turnover_penalty: float,
    return_proxy_weight: float,
) -> dict[str, Any]:
    actual = pd.to_numeric(
        test["target_forward_return"], errors="coerce"
    ).to_numpy(dtype=float)
    mask = np.isfinite(actual) & np.isfinite(predicted_return)
    ic = _corr(predicted_return, actual)
    mae = (
        float(mean_absolute_error(actual[mask], predicted_return[mask]))
        if int(mask.sum())
        else None
    )
    rmse = (
        float(math.sqrt(mean_squared_error(actual[mask], predicted_return[mask])))
        if int(mask.sum())
        else None
    )
    regime_y = (actual > regime_return_threshold).astype(int)
    brier = (
        float(brier_score_loss(regime_y, regime_probability))
        if len(np.unique(regime_y)) >= 2
        else None
    )
    active = (
        (predicted_return >= entry_threshold)
        & (regime_probability >= regime_gate)
    )
    utility = _validation_utility(
        actual,
        active,
        horizon=horizon,
        turnover_penalty=turnover_penalty,
        return_proxy_weight=return_proxy_weight,
    )
    return {
        "rows": int(len(test)),
        "return_ic": ic,
        "mae": mae,
        "rmse": rmse,
        "regime_brier": brier,
        **utility,
    }


def _summarize_outer(folds: list[dict[str, Any]]) -> dict[str, Any]:
    def values(key: str) -> list[float]:
        out: list[float] = []
        for row in folds:
            value = row["test_metrics"].get(key)
            if value is not None and math.isfinite(float(value)):
                out.append(float(value))
        return out

    ics = values("return_ic")
    sharpes = values("sharpe_proxy")
    selected = values("selected_forward_return_mean")
    return {
        "fold_count": len(folds),
        "mean_test_return_ic": float(np.mean(ics)) if ics else None,
        "median_test_return_ic": float(np.median(ics)) if ics else None,
        "positive_ic_fold_count": int(np.sum(np.asarray(ics) > 0)) if ics else 0,
        "mean_test_sharpe_proxy": float(np.mean(sharpes)) if sharpes else None,
        "mean_selected_forward_return": float(np.mean(selected)) if selected else None,
    }


def _evaluation_prices(
    prices: pd.DataFrame,
    signals: pd.DataFrame,
) -> pd.DataFrame:
    start = pd.to_datetime(signals["signal_ts"], utc=True, errors="raise").min()
    out = prices.loc[prices["ts"] >= start].copy()
    if out.empty:
        raise RuntimeError("no prices in OOS evaluation window")
    return out


def run_market_v3(
    *,
    market: str,
    matrix_dir: Path,
    output_root: Path,
    spec: dict[str, Any],
    code_sha: str,
) -> dict[str, Any]:
    market_spec = spec["markets"][market]
    symbol = str(market_spec["symbol"])
    horizon = int(market_spec["horizon_observations"])
    model_type = str(market_spec["model_type"])
    regime_return_threshold = float(market_spec.get("regime_return_threshold", 0.0))

    matrix = pd.read_parquet(matrix_dir / f"{market.lower()}_matrix.parquet")
    matrix["as_of"] = pd.to_datetime(matrix["as_of"], utc=True, errors="raise")
    frame = (
        matrix.sort_values("as_of")
        .drop_duplicates("as_of", keep="last")
        .loc[lambda x: x["target_forward_return"].notna()]
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

    outputs: list[pd.DataFrame] = []
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

        features, feature_ranking, inner_folds = nested_return_feature_consensus(
            development,
            spec=spec,
            purge_observations=horizon,
        )
        model_params, model_tuning = tune_return_model(
            development,
            features=features,
            inner_folds=inner_folds,
            model_type=model_type,
            candidates=[dict(x) for x in market_spec["model_candidates"]],
        )
        regime_c, regime_tuning = tune_regime_c(
            development,
            features=features,
            inner_folds=inner_folds,
            threshold=regime_return_threshold,
            c_grid=[float(x) for x in spec.get("regime_c_grid", [0.01, 0.1])],
        )
        trading_gate, trading_tuning = tune_trading_gate(
            development,
            features=features,
            inner_folds=inner_folds,
            model_type=model_type,
            model_params=model_params,
            regime_return_threshold=regime_return_threshold,
            regime_c=regime_c,
            entry_quantiles=[
                float(x) for x in spec.get("entry_quantile_grid", [0.6, 0.7, 0.8])
            ],
            regime_probability_grid=[
                float(x)
                for x in spec.get("regime_probability_grid", [0.5, 0.55, 0.6])
            ],
            horizon=horizon,
            turnover_penalty=float(spec.get("turnover_penalty", 0.25)),
            return_proxy_weight=float(spec.get("return_proxy_weight", 0.25)),
        )

        return_bundle = _fit_return_model(
            development,
            features,
            model_type=model_type,
            params=model_params,
        )
        regime_bundle = _fit_regime_model(
            development,
            features,
            threshold=regime_return_threshold,
            c_value=regime_c,
        )
        development_pred = _predict_return(development, features, return_bundle)
        entry_threshold = float(
            np.quantile(development_pred, trading_gate["entry_quantile"])
        )
        test_pred = _predict_return(test, features, return_bundle)
        test_regime = _predict_regime(test, features, regime_bundle)

        parameter_hash = stable_hash(
            {
                "version": spec["version"],
                "market": market,
                "outer_fold": asdict(outer),
                "features": features,
                "model_type": model_type,
                "model_params": model_params,
                "regime_c": regime_c,
                "trading_gate": trading_gate,
                "entry_threshold": entry_threshold,
            }
        )
        run_id = f"{market.lower()}-v3-f{outer.fold_id:03d}-{parameter_hash[:12]}"

        outputs.append(
            pd.DataFrame(
                {
                    "run_id": run_id,
                    "market": market,
                    "symbol": symbol,
                    "as_of": test["as_of"].to_numpy(),
                    "fold_id": int(outer.fold_id),
                    "model_version": spec["version"],
                    "feature_version": spec["feature_set"],
                    "predicted_return": test_pred,
                    "score": test_pred,
                    "regime_probability": test_regime,
                    "entry_return_threshold": entry_threshold,
                    "entry_quantile": float(trading_gate["entry_quantile"]),
                    "regime_probability_gate": float(
                        trading_gate["regime_probability_gate"]
                    ),
                    "parameter_hash": parameter_hash,
                }
            )
        )

        fold_metrics.append(
            {
                "outer_fold": asdict(outer),
                "run_id": run_id,
                "model_type": model_type,
                "selected_feature_count": len(features),
                "selected_features": features,
                "feature_consensus_ranking": feature_ranking,
                "best_model_params": model_params,
                "model_tuning": model_tuning,
                "regime_return_threshold": regime_return_threshold,
                "best_regime_c": regime_c,
                "regime_tuning": regime_tuning,
                "trading_gate": trading_gate,
                "trading_tuning": trading_tuning,
                "entry_return_threshold": entry_threshold,
                "test_metrics": _outer_test_metrics(
                    test,
                    test_pred,
                    test_regime,
                    regime_return_threshold=regime_return_threshold,
                    entry_threshold=entry_threshold,
                    regime_gate=float(trading_gate["regime_probability_gate"]),
                    horizon=horizon,
                    turnover_penalty=float(spec.get("turnover_penalty", 0.25)),
                    return_proxy_weight=float(spec.get("return_proxy_weight", 0.25)),
                ),
            }
        )

    if not outputs:
        raise RuntimeError(f"{market}: no completed V3 folds")

    model_output = (
        pd.concat(outputs, ignore_index=True)
        .sort_values("as_of")
        .drop_duplicates(["market", "symbol", "as_of"], keep="last")
        .reset_index(drop=True)
    )
    signals = build_signals(model_output, symbol=symbol)
    prices = _load_prices(matrix_dir, market, symbol)
    prices_eval = _evaluation_prices(prices, signals)

    market_dir = output_root / market.lower()
    market_dir.mkdir(parents=True, exist_ok=True)
    model_output.to_parquet(market_dir / "historical_model_output.parquet", index=False)
    signals.to_parquet(market_dir / "historical_strategy_signal.parquet", index=False)
    _write_json(market_dir / "fold_metrics.json", fold_metrics)

    backtests: dict[str, Any] = {}
    commission_bps = float(spec.get("commission_bps", 5.0))
    slippage_bps = float(spec.get("slippage_bps", 5.0))
    max_hold_bars = int(market_spec.get("max_hold_bars", 20))
    initial_cash = 1_000_000.0

    for fraction in [float(x) for x in spec.get("position_fractions", [0.1, 1.0])]:
        key = f"{int(round(fraction * 100))}pct"
        result = run_backtest(
            signals[["symbol", "signal_ts", "signal", "entry_allowed"]],
            prices_eval,
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
            prices_eval,
            initial_cash=initial_cash,
            position_fraction=fraction,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
        )
        bh_equity.to_parquet(market_dir / f"buy_hold_{key}_equity.parquet", index=False)
        backtests[key] = {
            "strategy": result.metrics,
            "buy_hold": performance_metrics(pd.DataFrame(), bh_equity),
        }

    strategy_100 = backtests["100pct"]["strategy"]
    vol_equity, vol_scale = _vol_matched_equity(
        prices_eval,
        initial_cash=initial_cash,
        target_volatility=float(strategy_100.get("annualized_volatility") or 0.0),
    )
    vol_equity.to_parquet(market_dir / "buy_hold_vol_matched_equity.parquet", index=False)
    vol_metrics = performance_metrics(pd.DataFrame(), vol_equity)

    summary = {
        "status": "READY",
        "market": market,
        "symbol": symbol,
        "code_sha": code_sha,
        "model_version": spec["version"],
        "feature_version": spec["feature_set"],
        "model_type": model_type,
        "evaluation_window": {
            "start": prices_eval["ts"].min(),
            "end": prices_eval["ts"].max(),
        },
        "outer_walk_forward": _summarize_outer(fold_metrics),
        "model_output_rows": int(len(model_output)),
        "signal_counts": signals["signal"].value_counts().to_dict(),
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


def replay_v2_common_window(
    *,
    market: str,
    matrix_dir: Path,
    v2_root: Path,
    v3_root: Path,
    spec: dict[str, Any],
) -> dict[str, Any]:
    market_spec = spec["markets"][market]
    symbol = str(market_spec["symbol"])
    v2_signal_path = v2_root / market.lower() / "historical_strategy_signal.parquet"
    v3_signal_path = v3_root / market.lower() / "historical_strategy_signal.parquet"
    if not v2_signal_path.exists() or not v3_signal_path.exists():
        return {"status": "SKIPPED", "reason": "signal artifact missing"}

    v2 = pd.read_parquet(v2_signal_path)
    v3 = pd.read_parquet(v3_signal_path)
    v2["signal_ts"] = pd.to_datetime(v2["signal_ts"], utc=True, errors="raise")
    v3["signal_ts"] = pd.to_datetime(v3["signal_ts"], utc=True, errors="raise")
    start = max(v2["signal_ts"].min(), v3["signal_ts"].min())
    end = min(v2["signal_ts"].max(), v3["signal_ts"].max())

    prices = _load_prices(matrix_dir, market, symbol)
    prices = prices.loc[(prices["ts"] >= start) & (prices["ts"] <= end)].copy()
    if prices.empty:
        return {"status": "SKIPPED", "reason": "no common-window prices"}

    config = BacktestConfig(
        initial_cash=1_000_000.0,
        position_fraction=1.0,
        max_open_positions=1,
        commission_bps=float(spec.get("commission_bps", 5.0)),
        slippage_bps=float(spec.get("slippage_bps", 5.0)),
        max_hold_bars=int(market_spec.get("max_hold_bars", 20)),
        allow_fractional=True,
    )
    out: dict[str, Any] = {
        "status": "READY",
        "start": start,
        "end": end,
    }
    for name, signal in (("V2", v2), ("V3", v3)):
        s = signal.loc[
            (signal["signal_ts"] >= start) & (signal["signal_ts"] <= end),
            ["symbol", "signal_ts", "signal", "entry_allowed"],
        ].copy()
        result = run_backtest(s, prices, config)
        out[name] = result.metrics

    bh = _buy_hold_equity(
        prices,
        initial_cash=1_000_000.0,
        position_fraction=1.0,
        commission_bps=float(spec.get("commission_bps", 5.0)),
        slippage_bps=float(spec.get("slippage_bps", 5.0)),
    )
    out["BUY_HOLD"] = performance_metrics(pd.DataFrame(), bh)
    return out


def run_equal_weight_portfolio(output_root: Path) -> dict[str, Any]:
    series: dict[str, pd.Series] = {}
    for market in MARKETS:
        path = output_root / market.lower() / "strategy_100pct_equity.parquet"
        if not path.exists():
            continue
        equity = pd.read_parquet(path)
        ts = pd.to_datetime(equity["ts"], utc=True, errors="raise")
        values = pd.Series(
            pd.to_numeric(equity["equity"], errors="coerce").to_numpy(dtype=float),
            index=ts,
            name=market,
        )
        daily = values.resample("1D").last().ffill()
        series[market] = daily

    if len(series) < 2:
        raise RuntimeError("V3 equal-weight portfolio needs at least two sleeves")
    panel = pd.concat(series, axis=1).dropna(how="any")
    returns = panel.pct_change().fillna(0.0)

    targets = build_rolling_portfolio_targets(
        returns,
        method="equal_weight",
        lookback_days=180,
        min_observations=90,
        rebalance_frequency="M",
    )
    equity = portfolio_equity_from_targets(returns, targets)
    metrics = portfolio_metrics(equity)

    root = output_root / "portfolio" / "equal_weight"
    root.mkdir(parents=True, exist_ok=True)
    targets.to_parquet(root / "portfolio_target.parquet", index=False)
    equity.to_parquet(root / "portfolio_equity.parquet", index=False)
    _write_json(root / "portfolio_performance.json", metrics)
    return {
        "status": "READY",
        "method": "equal_weight",
        "metrics": metrics,
        "research_only": True,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kalman Historical V3 return-regime candidate")
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--v2-root", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--code-sha", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    matrix_dir = Path(args.matrix_dir).expanduser()
    v2_root = Path(args.v2_root).expanduser()
    output_root = Path(args.output_dir).expanduser()
    spec = json.loads(Path(args.spec).expanduser().read_text(encoding="utf-8"))

    status: dict[str, Any] = {
        "status": "READY",
        "version": spec["version"],
        "code_sha": args.code_sha,
        "markets": {},
        "common_window_v2_vs_v3": {},
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }

    for market in MARKETS:
        try:
            status["markets"][market] = run_market_v3(
                market=market,
                matrix_dir=matrix_dir,
                output_root=output_root,
                spec=spec,
                code_sha=args.code_sha,
            )
        except Exception as exc:
            status["status"] = "FAIL"
            status["markets"][market] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    ready = [
        market
        for market, row in status["markets"].items()
        if row.get("status") == "READY"
    ]

    if len(ready) >= 2:
        try:
            status["portfolio"] = run_equal_weight_portfolio(output_root)
        except Exception as exc:
            status["status"] = "FAIL"
            status["portfolio"] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    for market in ready:
        try:
            status["common_window_v2_vs_v3"][market] = replay_v2_common_window(
                market=market,
                matrix_dir=matrix_dir,
                v2_root=v2_root,
                v3_root=output_root,
                spec=spec,
            )
        except Exception as exc:
            status["common_window_v2_vs_v3"][market] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    _write_json(output_root / "candidate_run_status.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0 if status["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
