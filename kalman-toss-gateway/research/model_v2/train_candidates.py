from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

from .model_contract import ARTIFACT_SCHEMA


NON_FEATURE_COLUMNS = {
    "as_of",
    "anchor_close",
    "target_forward_return",
    "target_label",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train Kalman V2 logistic candidate models")
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        + "\n",
        encoding="utf-8",
    )
    checksum = sha256_file(tmp)
    os.replace(tmp, path)
    return checksum


def atomic_parquet(frame: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(tmp, index=False)
    checksum = sha256_file(tmp)
    os.replace(tmp, path)
    return checksum


def safe_metric(fn, *args, **kwargs) -> float | None:
    try:
        value = float(fn(*args, **kwargs))
    except Exception:
        return None
    return value if math.isfinite(value) else None


def classification_metrics(
    y_true: pd.Series,
    probability: np.ndarray,
    threshold: float,
    forward_return: pd.Series | None = None,
) -> dict[str, Any]:
    pred = (probability >= threshold).astype(int)
    metrics: dict[str, Any] = {
        "rows": int(len(y_true)),
        "positive_rate": float(np.mean(y_true)),
        "selection_rate": float(np.mean(pred)),
        "roc_auc": safe_metric(roc_auc_score, y_true, probability),
        "brier": safe_metric(brier_score_loss, y_true, probability),
        "log_loss": safe_metric(log_loss, y_true, probability, labels=[0, 1]),
        "accuracy": safe_metric(accuracy_score, y_true, pred),
        "balanced_accuracy": safe_metric(balanced_accuracy_score, y_true, pred),
        "precision": safe_metric(precision_score, y_true, pred, zero_division=0),
        "recall": safe_metric(recall_score, y_true, pred, zero_division=0),
    }
    if forward_return is not None:
        ret = pd.to_numeric(forward_return, errors="coerce").to_numpy(dtype=float)
        selected = ret[pred == 1]
        selected = selected[np.isfinite(selected)]
        metrics["selected_forward_return_mean"] = (
            float(np.mean(selected)) if len(selected) else None
        )
        metrics["selected_forward_return_median"] = (
            float(np.median(selected)) if len(selected) else None
        )
        metrics["selected_forward_return_win_rate"] = (
            float(np.mean(selected > 0)) if len(selected) else None
        )
    return metrics


def chronological_split(
    frame: pd.DataFrame,
    *,
    horizon: int,
    train_fraction: float,
    validation_fraction: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    usable = frame.loc[frame["target_label"].notna()].copy()
    usable = usable.sort_values("as_of").reset_index(drop=True)
    n = len(usable)
    if n < 180:
        raise RuntimeError(f"insufficient labeled rows: {n}")

    train_boundary = int(n * train_fraction)
    validation_boundary = int(n * (train_fraction + validation_fraction))
    train_end = max(1, train_boundary - horizon)
    validation_end = max(train_boundary + 1, validation_boundary - horizon)

    train = usable.iloc[:train_end].copy()
    validation = usable.iloc[train_boundary:validation_end].copy()
    test = usable.iloc[validation_boundary:].copy()

    if min(len(train), len(validation), len(test)) < 30:
        raise RuntimeError(
            f"split too small train={len(train)} val={len(validation)} test={len(test)}"
        )
    return train, validation, test


def select_features(
    train: pd.DataFrame,
    *,
    minimum_coverage: float,
    maximum_features: int,
) -> list[str]:
    candidates = [c for c in train.columns if c not in NON_FEATURE_COLUMNS]
    y = pd.to_numeric(train["target_label"], errors="coerce")

    ranked: list[tuple[float, str]] = []
    for col in candidates:
        x = pd.to_numeric(train[col], errors="coerce")
        if float(x.notna().mean()) < minimum_coverage:
            continue
        median = x.median()
        filled = x.fillna(median)
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


def fit_transformer_and_model(
    frame: pd.DataFrame,
    features: list[str],
    *,
    c_value: float,
) -> tuple[SimpleImputer, StandardScaler, LogisticRegression]:
    x = frame[features].apply(pd.to_numeric, errors="coerce")
    y = frame["target_label"].astype(int).to_numpy()

    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    x_imp = imputer.fit_transform(x)
    x_std = scaler.fit_transform(x_imp)

    model = LogisticRegression(
        C=c_value,
        penalty="l2",
        solver="lbfgs",
        class_weight="balanced",
        max_iter=3000,
        random_state=42,
    )
    model.fit(x_std, y)
    return imputer, scaler, model


def predict_probability(
    frame: pd.DataFrame,
    features: list[str],
    imputer: SimpleImputer,
    scaler: StandardScaler,
    model: LogisticRegression,
) -> np.ndarray:
    x = frame[features].apply(pd.to_numeric, errors="coerce")
    return model.predict_proba(scaler.transform(imputer.transform(x)))[:, 1]


def choose_threshold(
    y_true: pd.Series,
    probability: np.ndarray,
    thresholds: list[float],
) -> tuple[float, dict[str, Any]]:
    scored: list[tuple[float, float, dict[str, Any]]] = []
    for threshold in thresholds:
        metrics = classification_metrics(y_true, probability, threshold)
        balanced = metrics["balanced_accuracy"]
        score = float(balanced) if balanced is not None else float("-inf")
        scored.append((score, -abs(threshold - 0.55), {"threshold": threshold, **metrics}))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best = scored[0][2]
    return float(best["threshold"]), best


def train_market(
    *,
    market_name: str,
    market_spec: dict[str, Any],
    global_spec: dict[str, Any],
    matrix_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    matrix_path = matrix_dir / f"{market_name.lower()}_matrix.parquet"
    manifest_path = matrix_dir / f"{market_name.lower()}_matrix_manifest.json"
    if not matrix_path.exists() or not manifest_path.exists():
        raise FileNotFoundError(f"missing matrix artifacts for {market_name}")

    matrix = pd.read_parquet(matrix_path)
    matrix["as_of"] = pd.to_datetime(matrix["as_of"], errors="raise")
    matrix_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    horizon = int(market_spec["horizon_observations"])

    train, validation, test = chronological_split(
        matrix,
        horizon=horizon,
        train_fraction=float(global_spec.get("train_fraction", 0.60)),
        validation_fraction=float(global_spec.get("validation_fraction", 0.20)),
    )
    selected = select_features(
        train,
        minimum_coverage=float(global_spec.get("minimum_feature_coverage", 0.80)),
        maximum_features=int(global_spec.get("maximum_features", 96)),
    )

    candidates: list[dict[str, Any]] = []
    candidate_models: dict[float, tuple[SimpleImputer, StandardScaler, LogisticRegression]] = {}
    for c_value in [float(x) for x in global_spec.get("candidate_c", [0.1])]:
        imputer, scaler, model = fit_transformer_and_model(
            train,
            selected,
            c_value=c_value,
        )
        prob = predict_probability(validation, selected, imputer, scaler, model)
        metrics = classification_metrics(validation["target_label"], prob, 0.5)
        auc = metrics["roc_auc"]
        brier = metrics["brier"]
        candidates.append(
            {
                "c": c_value,
                "validation_roc_auc": auc,
                "validation_brier": brier,
                "validation_balanced_accuracy_at_0_5": metrics["balanced_accuracy"],
            }
        )
        candidate_models[c_value] = (imputer, scaler, model)

    def candidate_sort(item: dict[str, Any]) -> tuple[float, float, float]:
        auc = item["validation_roc_auc"]
        brier = item["validation_brier"]
        return (
            float(auc) if auc is not None else -1.0,
            -(float(brier) if brier is not None else 999.0),
            -float(item["c"]),
        )

    candidates.sort(key=candidate_sort, reverse=True)
    best_c = float(candidates[0]["c"])
    train_imputer, train_scaler, train_model = candidate_models[best_c]
    validation_probability = predict_probability(
        validation,
        selected,
        train_imputer,
        train_scaler,
        train_model,
    )
    threshold, threshold_metrics = choose_threshold(
        validation["target_label"],
        validation_probability,
        [float(x) for x in global_spec.get("threshold_grid", [0.5])],
    )

    train_validation = pd.concat([train, validation], ignore_index=True)
    imputer, scaler, model = fit_transformer_and_model(
        train_validation,
        selected,
        c_value=best_c,
    )
    test_probability = predict_probability(test, selected, imputer, scaler, model)
    test_metrics = classification_metrics(
        test["target_label"],
        test_probability,
        threshold,
        test["target_forward_return"],
    )

    medians = {
        feature: float(value)
        for feature, value in zip(selected, imputer.statistics_)
    }
    means = {
        feature: float(value)
        for feature, value in zip(selected, scaler.mean_)
    }
    scales = {
        feature: float(value) if float(value) != 0 else 1.0
        for feature, value in zip(selected, scaler.scale_)
    }
    coefficients = {
        feature: float(value)
        for feature, value in zip(selected, model.coef_[0])
    }

    artifact = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "model_family": "logistic_regression_l2",
        "model_version": global_spec["version"],
        "dataset_version": global_spec["dataset_version"],
        "feature_set": global_spec["feature_set"],
        "market": market_name,
        "symbol": market_spec["symbol"],
        "strategy_version": market_spec["strategy_version"],
        "horizon_observations": horizon,
        "probability_threshold": threshold,
        "selected_features": selected,
        "imputer_medians": medians,
        "scaler_mean": means,
        "scaler_scale": scales,
        "coefficients": coefficients,
        "intercept": float(model.intercept_[0]),
        "hyperparameters": {
            "C": best_c,
            "penalty": "l2",
            "class_weight": "balanced",
            "solver": "lbfgs",
        },
        "validation_threshold_metrics": threshold_metrics,
        "test_metrics": test_metrics,
        "candidate_summary": candidates,
        "training_window": {
            "train_start": str(train["as_of"].min()),
            "train_end": str(train["as_of"].max()),
            "validation_start": str(validation["as_of"].min()),
            "validation_end": str(validation["as_of"].max()),
            "test_start": str(test["as_of"].min()),
            "test_end": str(test["as_of"].max()),
            "refit_through": str(train_validation["as_of"].max()),
            "horizon_purge_observations": horizon,
        },
        "matrix_lineage_sha256": matrix_manifest["lineage_sha256"],
        "matrix_sha256": matrix_manifest["matrix_sha256"],
        "sklearn_version": sklearn.__version__,
        "shadow_only": True,
        "live_execution": False,
        "allow_trade_shadow": False,
        "trained_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }

    market_dir = output_dir / market_name.lower()
    model_path = market_dir / "model.json"
    model_sha = atomic_json(model_path, artifact)

    manifest = {
        "status": "READY",
        "market": market_name,
        "symbol": market_spec["symbol"],
        "strategy_version": market_spec["strategy_version"],
        "model_path": str(model_path),
        "model_sha256": model_sha,
        "selected_feature_count": len(selected),
        "validation_threshold": threshold,
        "test_metrics": test_metrics,
        "matrix_lineage_sha256": matrix_manifest["lineage_sha256"],
        "shadow_only": True,
        "live_execution": False,
    }
    atomic_json(market_dir / "model_manifest.json", manifest)

    predictions = test[["as_of", "target_forward_return", "target_label"]].copy()
    predictions["probability_up"] = test_probability
    predictions["threshold"] = threshold
    predictions["predicted_entry"] = test_probability >= threshold
    atomic_parquet(predictions, market_dir / "test_predictions.parquet")
    return manifest


def main() -> int:
    args = parse_args()
    matrix_dir = Path(args.matrix_dir).expanduser()
    spec_path = Path(args.spec).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    status: dict[str, Any] = {
        "status": "READY",
        "model_version": spec["version"],
        "dataset_version": spec["dataset_version"],
        "shadow_only": True,
        "markets": {},
    }

    for market_name, market_spec in spec["markets"].items():
        try:
            status["markets"][market_name] = train_market(
                market_name=market_name,
                market_spec=market_spec,
                global_spec=spec,
                matrix_dir=matrix_dir,
                output_dir=output_dir,
            )
        except Exception as exc:
            status["status"] = "FAIL"
            status["markets"][market_name] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    atomic_json(output_dir / "model_v2_training_status.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0 if status["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
