from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    balanced_accuracy_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

from .contracts import ExperimentSpec, stable_hash
from .walk_forward import generate_walk_forward_folds


NON_FEATURE_COLUMNS = {
    "as_of",
    "anchor_close",
    "target_forward_return",
    "target_label",
}


@dataclass(frozen=True)
class HistoricalBackfillResult:
    model_output: pd.DataFrame
    strategy_signal: pd.DataFrame
    fold_metrics: list[dict[str, Any]]
    experiment: dict[str, Any]


def _safe_metric(fn: Any, *args: Any, **kwargs: Any) -> float | None:
    try:
        value = float(fn(*args, **kwargs))
    except Exception:
        return None
    return value if math.isfinite(value) else None


def _select_features(
    train: pd.DataFrame,
    *,
    minimum_coverage: float,
    maximum_features: int,
) -> list[str]:
    y = pd.to_numeric(train["target_label"], errors="coerce")
    ranked: list[tuple[float, str]] = []

    for col in [c for c in train.columns if c not in NON_FEATURE_COLUMNS]:
        x = pd.to_numeric(train[col], errors="coerce")
        if float(x.notna().mean()) < minimum_coverage:
            continue
        filled = x.fillna(x.median())
        if filled.nunique(dropna=True) <= 1:
            continue
        corr = filled.corr(y)
        score = abs(float(corr)) if corr is not None and np.isfinite(corr) else 0.0
        ranked.append((score, col))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = [col for _, col in ranked[:maximum_features]]
    if len(selected) < 5:
        raise RuntimeError(f"too few selected features: {len(selected)}")
    return selected


def _fit_model(
    frame: pd.DataFrame,
    features: list[str],
    *,
    c_value: float,
) -> tuple[SimpleImputer, StandardScaler, LogisticRegression]:
    x = frame[features].apply(pd.to_numeric, errors="coerce")
    y = pd.to_numeric(frame["target_label"], errors="raise").astype(int).to_numpy()

    if len(np.unique(y)) < 2:
        raise RuntimeError("training fold has only one target class")

    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    x_imp = imputer.fit_transform(x)
    x_std = scaler.fit_transform(x_imp)

    model = LogisticRegression(
        C=float(c_value),
        penalty="l2",
        solver="lbfgs",
        class_weight="balanced",
        max_iter=3000,
        random_state=42,
    )
    model.fit(x_std, y)
    return imputer, scaler, model


def _predict_probability(
    frame: pd.DataFrame,
    features: list[str],
    imputer: SimpleImputer,
    scaler: StandardScaler,
    model: LogisticRegression,
) -> np.ndarray:
    x = frame[features].apply(pd.to_numeric, errors="coerce")
    return model.predict_proba(scaler.transform(imputer.transform(x)))[:, 1]


def _choose_candidate_c(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
    candidate_c: list[float],
) -> tuple[float, list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []

    for c_value in candidate_c:
        imputer, scaler, model = _fit_model(train, features, c_value=float(c_value))
        prob = _predict_probability(validation, features, imputer, scaler, model)
        y = pd.to_numeric(validation["target_label"], errors="raise").astype(int)
        candidates.append(
            {
                "c": float(c_value),
                "validation_roc_auc": _safe_metric(roc_auc_score, y, prob),
                "validation_brier": _safe_metric(brier_score_loss, y, prob),
            }
        )

    def key(item: dict[str, Any]) -> tuple[float, float, float]:
        auc = item["validation_roc_auc"]
        brier = item["validation_brier"]
        return (
            float(auc) if auc is not None else -1.0,
            -(float(brier) if brier is not None else 999.0),
            -float(item["c"]),
        )

    candidates.sort(key=key, reverse=True)
    return float(candidates[0]["c"]), candidates


def _choose_threshold(
    y_true: pd.Series,
    probability: np.ndarray,
    thresholds: list[float],
) -> tuple[float, list[dict[str, Any]]]:
    scored: list[dict[str, Any]] = []

    for threshold in thresholds:
        pred = (probability >= float(threshold)).astype(int)
        scored.append(
            {
                "threshold": float(threshold),
                "balanced_accuracy": _safe_metric(
                    balanced_accuracy_score,
                    y_true.astype(int),
                    pred,
                ),
            }
        )

    scored.sort(
        key=lambda item: (
            float(item["balanced_accuracy"])
            if item["balanced_accuracy"] is not None
            else -1.0,
            -abs(float(item["threshold"]) - 0.55),
        ),
        reverse=True,
    )
    return float(scored[0]["threshold"]), scored


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
        "selected_forward_return_mean": (
            float(np.mean(selected)) if len(selected) else None
        ),
        "selected_forward_return_win_rate": (
            float(np.mean(selected > 0)) if len(selected) else None
        ),
    }


def _decision_signals(
    model_output: pd.DataFrame,
    *,
    symbol: str,
) -> pd.DataFrame:
    if model_output.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "signal_ts",
                "signal",
                "entry_allowed",
                "probability",
                "probability_threshold",
                "exit_threshold",
                "fold_id",
                "run_id",
            ]
        )

    rows: list[dict[str, Any]] = []

    for row in model_output.sort_values("as_of").to_dict("records"):
        probability = float(row["probability"])
        entry_threshold = float(row["probability_threshold"])
        exit_threshold = max(0.0, min(1.0, 1.0 - entry_threshold))

        # Stateless decision layer. Position state belongs only to the ledger.
        # Repeated BUY/SELL decisions are safely de-duplicated by run_backtest().
        if probability >= entry_threshold:
            signal = "BUY"
            entry_allowed = True
        elif probability <= exit_threshold:
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
                "probability": probability,
                "probability_threshold": entry_threshold,
                "exit_threshold": exit_threshold,
                "fold_id": int(row["fold_id"]),
                "run_id": row["run_id"],
            }
        )

    return pd.DataFrame(rows)


def run_historical_backfill(
    matrix: pd.DataFrame,
    *,
    market_name: str,
    market_spec: dict[str, Any],
    global_spec: dict[str, Any],
    experiment_spec: ExperimentSpec,
    train_observations: int = 504,
    valid_observations: int = 63,
    test_observations: int = 126,
    purge_observations: int | None = None,
    expanding: bool = True,
) -> HistoricalBackfillResult:
    frame = matrix.copy()
    frame["as_of"] = pd.to_datetime(frame["as_of"], utc=True, errors="raise")
    frame = frame.sort_values("as_of").drop_duplicates("as_of", keep="last")
    frame = frame.loc[frame["target_label"].notna()].reset_index(drop=True)

    start = pd.Timestamp(experiment_spec.start_date, tz="UTC")
    frame = frame.loc[frame["as_of"] >= start].reset_index(drop=True)
    if frame.empty:
        raise RuntimeError(f"{market_name}: no labeled rows at/after {start.date()}")

    horizon = int(market_spec["horizon_observations"])
    purge = horizon if purge_observations is None else int(purge_observations)

    folds = generate_walk_forward_folds(
        frame["as_of"],
        train_observations=train_observations,
        valid_observations=valid_observations,
        test_observations=test_observations,
        purge_observations=purge,
        step_observations=test_observations,
        expanding=expanding,
    )
    if not folds:
        raise RuntimeError(
            f"{market_name}: insufficient history for walk-forward folds "
            f"(rows={len(frame)})"
        )

    outputs: list[pd.DataFrame] = []
    fold_metrics: list[dict[str, Any]] = []
    candidate_c = [float(x) for x in global_spec.get("candidate_c", [0.1])]
    threshold_grid = [
        float(x) for x in global_spec.get("threshold_grid", [0.50, 0.55, 0.60])
    ]

    for fold in folds:
        train = frame.loc[
            (frame["as_of"] >= pd.Timestamp(fold.train_start))
            & (frame["as_of"] <= pd.Timestamp(fold.train_end))
        ].copy()
        validation = frame.loc[
            (frame["as_of"] >= pd.Timestamp(fold.valid_start))
            & (frame["as_of"] <= pd.Timestamp(fold.valid_end))
        ].copy()
        test = frame.loc[
            (frame["as_of"] >= pd.Timestamp(fold.test_start))
            & (frame["as_of"] <= pd.Timestamp(fold.test_end))
        ].copy()

        if min(len(train), len(validation), len(test)) < 20:
            continue
        if train["target_label"].nunique() < 2 or validation["target_label"].nunique() < 2:
            continue

        features = _select_features(
            train,
            minimum_coverage=float(global_spec.get("minimum_feature_coverage", 0.80)),
            maximum_features=int(global_spec.get("maximum_features", 96)),
        )
        best_c, c_candidates = _choose_candidate_c(
            train,
            validation,
            features,
            candidate_c,
        )

        train_imputer, train_scaler, train_model = _fit_model(
            train,
            features,
            c_value=best_c,
        )
        validation_probability = _predict_probability(
            validation,
            features,
            train_imputer,
            train_scaler,
            train_model,
        )
        threshold, threshold_scores = _choose_threshold(
            validation["target_label"],
            validation_probability,
            threshold_grid,
        )

        train_validation = pd.concat([train, validation], ignore_index=True)
        imputer, scaler, model = _fit_model(
            train_validation,
            features,
            c_value=best_c,
        )
        test_probability = _predict_probability(
            test,
            features,
            imputer,
            scaler,
            model,
        )

        parameter_hash = stable_hash(
            {
                "experiment_hash": experiment_spec.experiment_hash,
                "fold": asdict(fold),
                "features": features,
                "best_c": best_c,
                "threshold": threshold,
            }
        )
        fold_run_id = (
            f"{experiment_spec.experiment_hash[:12]}-"
            f"{market_name.lower()}-f{fold.fold_id:03d}-"
            f"{parameter_hash[:10]}"
        )

        fold_output = pd.DataFrame(
            {
                "run_id": fold_run_id,
                "market": market_name,
                "symbol": str(market_spec["symbol"]),
                "as_of": test["as_of"].to_numpy(),
                "fold_id": fold.fold_id,
                "model_version": experiment_spec.model_version,
                "feature_version": experiment_spec.feature_version,
                "probability": test_probability,
                "score": test_probability,
                "probability_threshold": threshold,
                "parameter_hash": parameter_hash,
            }
        )
        outputs.append(fold_output)

        fold_metrics.append(
            {
                "fold": asdict(fold),
                "run_id": fold_run_id,
                "selected_feature_count": len(features),
                "selected_features": features,
                "best_c": best_c,
                "candidate_metrics": c_candidates,
                "threshold": threshold,
                "threshold_scores": threshold_scores,
                "test_metrics": _test_metrics(test, test_probability, threshold),
            }
        )

    if not outputs:
        raise RuntimeError(f"{market_name}: no valid walk-forward fold completed")

    model_output = (
        pd.concat(outputs, ignore_index=True)
        .sort_values("as_of")
        .drop_duplicates(["market", "symbol", "as_of"], keep="last")
        .reset_index(drop=True)
    )
    strategy_signal = _decision_signals(
        model_output,
        symbol=str(market_spec["symbol"]),
    )

    experiment = {
        **asdict(experiment_spec),
        "mode": experiment_spec.mode.value,
        "experiment_hash": experiment_spec.experiment_hash,
        "market": market_name,
        "symbol": str(market_spec["symbol"]),
        "horizon_observations": horizon,
        "purge_observations": purge,
        "train_observations": train_observations,
        "valid_observations": valid_observations,
        "test_observations": test_observations,
        "expanding": expanding,
        "completed_folds": len(fold_metrics),
        "model_output_rows": len(model_output),
        "signal_rows": len(strategy_signal),
        "signal_counts": strategy_signal["signal"].value_counts().to_dict(),
    }

    return HistoricalBackfillResult(
        model_output=model_output,
        strategy_signal=strategy_signal,
        fold_metrics=fold_metrics,
        experiment=experiment,
    )


def write_backfill_artifacts(
    result: HistoricalBackfillResult,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result.model_output.to_parquet(output_dir / "historical_model_output.parquet", index=False)
    result.strategy_signal.to_parquet(
        output_dir / "historical_strategy_signal.parquet",
        index=False,
    )
    (output_dir / "fold_metrics.json").write_text(
        json.dumps(result.fold_metrics, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    (output_dir / "experiment.json").write_text(
        json.dumps(result.experiment, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
