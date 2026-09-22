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

from research.model_v2.train_candidates import chronological_split, select_features
from .model_contract import ARTIFACT_SCHEMA


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train isolated calibrated Kalman V2.002 candidates")
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
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False, default=str) + "\n",
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


def metrics(
    y_true: pd.Series,
    probability: np.ndarray,
    threshold: float,
    forward_return: pd.Series | None = None,
) -> dict[str, Any]:
    y = pd.to_numeric(y_true, errors="coerce").astype(int).to_numpy()
    p = np.clip(np.asarray(probability, dtype=float), 1e-12, 1.0 - 1e-12)
    pred = (p >= threshold).astype(int)
    positive_rate = float(np.mean(y))
    baseline_brier = positive_rate * (1.0 - positive_rate)
    baseline_log_loss = (
        float(-(positive_rate * np.log(positive_rate) + (1.0 - positive_rate) * np.log(1.0 - positive_rate)))
        if 0.0 < positive_rate < 1.0
        else 0.0
    )
    brier = safe_metric(brier_score_loss, y, p)
    ll = safe_metric(log_loss, y, p, labels=[0, 1])
    out: dict[str, Any] = {
        "rows": int(len(y)),
        "positive_rate": positive_rate,
        "selection_rate": float(np.mean(pred)),
        "roc_auc": safe_metric(roc_auc_score, y, p),
        "brier": brier,
        "baseline_brier": baseline_brier,
        "brier_skill": (
            float(1.0 - brier / baseline_brier)
            if brier is not None and baseline_brier > 0
            else None
        ),
        "log_loss": ll,
        "baseline_log_loss": baseline_log_loss,
        "log_loss_skill": (
            float(1.0 - ll / baseline_log_loss)
            if ll is not None and baseline_log_loss > 0
            else None
        ),
        "accuracy": safe_metric(accuracy_score, y, pred),
        "balanced_accuracy": safe_metric(balanced_accuracy_score, y, pred),
        "precision": safe_metric(precision_score, y, pred, zero_division=0),
        "recall": safe_metric(recall_score, y, pred, zero_division=0),
    }
    if forward_return is not None:
        ret = pd.to_numeric(forward_return, errors="coerce").to_numpy(dtype=float)
        selected = ret[pred == 1]
        selected = selected[np.isfinite(selected)]
        out["selected_forward_return_mean"] = float(np.mean(selected)) if len(selected) else None
        out["selected_forward_return_median"] = float(np.median(selected)) if len(selected) else None
        out["selected_forward_return_win_rate"] = float(np.mean(selected > 0)) if len(selected) else None
    return out


def validation_subsplit(
    validation: pd.DataFrame,
    *,
    horizon: int,
    ratios: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    x = validation.sort_values("as_of").reset_index(drop=True)
    n = len(x)
    tune_ratio = float(ratios.get("tune", 0.34))
    calibration_ratio = float(ratios.get("calibration", 0.33))
    b1 = int(n * tune_ratio)
    b2 = int(n * (tune_ratio + calibration_ratio))

    tune_end = max(1, b1 - horizon)
    calibration_end = max(b1 + 1, b2 - horizon)
    tune = x.iloc[:tune_end].copy()
    calibration = x.iloc[b1:calibration_end].copy()
    threshold = x.iloc[b2:].copy()

    if min(len(tune), len(calibration), len(threshold)) < 25:
        raise RuntimeError(
            f"validation subsplit too small tune={len(tune)} calibration={len(calibration)} threshold={len(threshold)}"
        )
    return tune, calibration, threshold


def fit_base(
    frame: pd.DataFrame,
    features: list[str],
    *,
    c_value: float,
    class_weight: str | None,
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
        class_weight=class_weight,
        max_iter=3000,
        random_state=42,
    )
    model.fit(x_std, y)
    return imputer, scaler, model


def transformed(
    frame: pd.DataFrame,
    features: list[str],
    imputer: SimpleImputer,
    scaler: StandardScaler,
) -> np.ndarray:
    x = frame[features].apply(pd.to_numeric, errors="coerce")
    return scaler.transform(imputer.transform(x))


def raw_probability(
    frame: pd.DataFrame,
    features: list[str],
    imputer: SimpleImputer,
    scaler: StandardScaler,
    model: LogisticRegression,
) -> np.ndarray:
    return model.predict_proba(transformed(frame, features, imputer, scaler))[:, 1]


def logits(
    frame: pd.DataFrame,
    features: list[str],
    imputer: SimpleImputer,
    scaler: StandardScaler,
    model: LogisticRegression,
) -> np.ndarray:
    return np.asarray(
        model.decision_function(transformed(frame, features, imputer, scaler)),
        dtype=float,
    )


def fit_platt(logit_values: np.ndarray, y_true: pd.Series) -> LogisticRegression:
    calibrator = LogisticRegression(
        C=1_000_000.0,
        penalty="l2",
        solver="lbfgs",
        max_iter=3000,
        random_state=42,
    )
    calibrator.fit(np.asarray(logit_values).reshape(-1, 1), y_true.astype(int).to_numpy())
    return calibrator


def calibrated_probability(logit_values: np.ndarray, calibrator: LogisticRegression) -> np.ndarray:
    return calibrator.predict_proba(np.asarray(logit_values).reshape(-1, 1))[:, 1]


def choose_threshold(
    frame: pd.DataFrame,
    probability: np.ndarray,
    thresholds: list[float],
) -> tuple[float, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        item = {"threshold": threshold, **metrics(
            frame["target_label"],
            probability,
            threshold,
            frame["target_forward_return"],
        )}
        rows.append(item)

    def key(item: dict[str, Any]) -> tuple[float, float, float, float]:
        selected_ret = item.get("selected_forward_return_mean")
        balanced = item.get("balanced_accuracy")
        precision = item.get("precision")
        return (
            float(selected_ret) if selected_ret is not None else -999.0,
            float(balanced) if balanced is not None else -999.0,
            float(precision) if precision is not None else -999.0,
            -abs(float(item["threshold"]) - 0.55),
        )

    rows.sort(key=key, reverse=True)
    return float(rows[0]["threshold"]), rows[0]


def quality_pass(test_metrics: dict[str, Any], gate: dict[str, Any]) -> tuple[bool, dict[str, bool]]:
    checks = {
        "minimum_test_rows": int(test_metrics.get("rows") or 0) >= int(gate.get("minimum_test_rows", 100)),
        "minimum_test_roc_auc": float(test_metrics.get("roc_auc") or -1.0) >= float(gate.get("minimum_test_roc_auc", 0.52)),
        "minimum_brier_skill": float(test_metrics.get("brier_skill") or -999.0) >= float(gate.get("minimum_brier_skill", 0.0)),
        "minimum_log_loss_skill": float(test_metrics.get("log_loss_skill") or -999.0) >= float(gate.get("minimum_log_loss_skill", 0.0)),
    }
    return all(checks.values()), checks


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
    tune, calibration, threshold_frame = validation_subsplit(
        validation,
        horizon=horizon,
        ratios=global_spec.get("validation_subsplit_ratios") or {},
    )

    feature_counts = sorted({int(x) for x in global_spec.get("candidate_feature_counts", [32])})
    max_features = max(feature_counts)
    ranked_features = select_features(
        train,
        minimum_coverage=float(global_spec.get("minimum_feature_coverage", 0.80)),
        maximum_features=max_features,
    )

    candidates: list[dict[str, Any]] = []
    for count in feature_counts:
        selected = ranked_features[: min(count, len(ranked_features))]
        for c_value in [float(x) for x in global_spec.get("candidate_c", [0.01])]:
            for class_weight in global_spec.get("candidate_class_weight", [None]):
                imputer, scaler, model = fit_base(
                    train,
                    selected,
                    c_value=c_value,
                    class_weight=class_weight,
                )
                p = raw_probability(tune, selected, imputer, scaler, model)
                m = metrics(tune["target_label"], p, 0.5)
                candidates.append(
                    {
                        "feature_count": len(selected),
                        "c": c_value,
                        "class_weight": class_weight,
                        "tune_metrics": m,
                    }
                )

    def candidate_key(item: dict[str, Any]) -> tuple[float, float, float, float, float]:
        m = item["tune_metrics"]
        return (
            float(m.get("brier_skill") if m.get("brier_skill") is not None else -999.0),
            float(m.get("log_loss_skill") if m.get("log_loss_skill") is not None else -999.0),
            float(m.get("roc_auc") if m.get("roc_auc") is not None else -999.0),
            -float(item["feature_count"]),
            -float(item["c"]),
        )

    candidates.sort(key=candidate_key, reverse=True)
    best = candidates[0]
    selected = ranked_features[: int(best["feature_count"])]
    train_tune = pd.concat([train, tune], ignore_index=True)
    imputer, scaler, model = fit_base(
        train_tune,
        selected,
        c_value=float(best["c"]),
        class_weight=best["class_weight"],
    )

    calibration_logits = logits(calibration, selected, imputer, scaler, model)
    calibrator = fit_platt(calibration_logits, calibration["target_label"])
    calibration_probability = calibrated_probability(calibration_logits, calibrator)
    calibration_metrics = metrics(calibration["target_label"], calibration_probability, 0.5)

    threshold_logits = logits(threshold_frame, selected, imputer, scaler, model)
    threshold_probability = calibrated_probability(threshold_logits, calibrator)
    threshold, threshold_metrics = choose_threshold(
        threshold_frame,
        threshold_probability,
        [float(x) for x in global_spec.get("threshold_grid", [0.5])],
    )

    test_logits = logits(test, selected, imputer, scaler, model)
    test_raw_probability = raw_probability(test, selected, imputer, scaler, model)
    test_probability = calibrated_probability(test_logits, calibrator)
    raw_test_metrics = metrics(
        test["target_label"],
        test_raw_probability,
        threshold,
        test["target_forward_return"],
    )
    test_metrics = metrics(
        test["target_label"],
        test_probability,
        threshold,
        test["target_forward_return"],
    )
    passed, quality_checks = quality_pass(
        test_metrics,
        global_spec.get("shadow_quality_gate") or {},
    )

    medians = {f: float(v) for f, v in zip(selected, imputer.statistics_)}
    means = {f: float(v) for f, v in zip(selected, scaler.mean_)}
    scales = {f: (float(v) if float(v) != 0 else 1.0) for f, v in zip(selected, scaler.scale_)}
    coefficients = {f: float(v) for f, v in zip(selected, model.coef_[0])}

    artifact = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "model_family": "calibrated_logistic_regression_l2",
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
        "probability_calibration": {
            "method": "platt",
            "slope": float(calibrator.coef_[0][0]),
            "intercept": float(calibrator.intercept_[0]),
            "calibration_rows": int(len(calibration)),
        },
        "hyperparameters": {
            "C": float(best["c"]),
            "class_weight": best["class_weight"],
            "penalty": "l2",
            "solver": "lbfgs",
            "feature_count": len(selected),
        },
        "candidate_summary": candidates,
        "calibration_metrics": calibration_metrics,
        "validation_threshold_metrics": threshold_metrics,
        "raw_test_metrics": raw_test_metrics,
        "test_metrics": test_metrics,
        "quality_gate_pass": passed,
        "quality_gate_checks": quality_checks,
        "training_window": {
            "train_start": str(train["as_of"].min()),
            "train_end": str(train["as_of"].max()),
            "tune_start": str(tune["as_of"].min()),
            "tune_end": str(tune["as_of"].max()),
            "calibration_start": str(calibration["as_of"].min()),
            "calibration_end": str(calibration["as_of"].max()),
            "threshold_start": str(threshold_frame["as_of"].min()),
            "threshold_end": str(threshold_frame["as_of"].max()),
            "test_start": str(test["as_of"].min()),
            "test_end": str(test["as_of"].max()),
            "refit_through": str(train_tune["as_of"].max()),
            "horizon_purge_observations": horizon,
        },
        "matrix_lineage_sha256": matrix_manifest["lineage_sha256"],
        "matrix_sha256": matrix_manifest["matrix_sha256"],
        "sklearn_version": sklearn.__version__,
        "shadow_only": True,
        "research_candidate": True,
        "live_execution": False,
        "allow_trade_shadow": False,
        "trained_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }

    market_dir = output_dir / market_name.lower()
    model_path = market_dir / "model.json"
    model_sha = atomic_json(model_path, artifact)

    predictions = test[["as_of", "target_forward_return", "target_label"]].copy()
    predictions["raw_probability_up"] = test_raw_probability
    predictions["probability_up"] = test_probability
    predictions["threshold"] = threshold
    predictions["predicted_entry"] = test_probability >= threshold
    atomic_parquet(predictions, market_dir / "test_predictions.parquet")

    manifest = {
        "status": "READY",
        "market": market_name,
        "symbol": market_spec["symbol"],
        "strategy_version": market_spec["strategy_version"],
        "model_path": str(model_path),
        "model_sha256": model_sha,
        "selected_feature_count": len(selected),
        "test_metrics": test_metrics,
        "raw_test_metrics": raw_test_metrics,
        "quality_gate_pass": passed,
        "quality_gate_checks": quality_checks,
        "shadow_only": True,
        "research_candidate": True,
        "live_execution": False,
    }
    atomic_json(market_dir / "model_manifest.json", manifest)
    return manifest


def main() -> int:
    args = parse_args()
    matrix_dir = Path(args.matrix_dir).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))

    status: dict[str, Any] = {
        "status": "READY",
        "model_version": spec["version"],
        "dataset_version": spec["dataset_version"],
        "feature_set": spec["feature_set"],
        "shadow_only": True,
        "research_candidate": True,
        "live_execution": False,
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

    atomic_json(output_dir / "model_v2_002_training_status.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0 if status["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
