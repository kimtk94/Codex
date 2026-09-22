from __future__ import annotations

import math
from typing import Any

import pandas as pd

ARTIFACT_SCHEMA = "kalman_rank_logit_json_v3"


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
    except Exception:
        return default
    return x if math.isfinite(x) else default


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(min(x, 50.0), -50.0)))


def score_row(
    row: pd.Series | dict[str, Any],
    artifact: dict[str, Any],
) -> dict[str, Any]:
    if artifact.get("artifact_schema") != ARTIFACT_SCHEMA:
        raise ValueError(
            f"unsupported artifact schema: {artifact.get('artifact_schema')!r}"
        )

    selected = list(artifact["selected_features"])
    medians = artifact["imputer_medians"]
    means = artifact["scaler_mean"]
    scales = artifact["scaler_scale"]
    coefficients = artifact["coefficients"]

    z = float(artifact["intercept"])
    missing_count = 0
    for feature in selected:
        value = row.get(feature) if hasattr(row, "get") else None
        try:
            x = float(value)
        except Exception:
            x = float("nan")
        if not math.isfinite(x):
            missing_count += 1
            x = _finite_float(medians.get(feature), 0.0)
        mean = _finite_float(means.get(feature), 0.0)
        scale = _finite_float(scales.get(feature), 1.0) or 1.0
        coef = _finite_float(coefficients.get(feature), 0.0)
        z += ((x - mean) / scale) * coef

    probability = _sigmoid(z)
    return {
        "score": probability,
        "probability_up": probability,
        "logit": z,
        "selected_feature_count": len(selected),
        "missing_feature_count": missing_count,
        "missing_feature_ratio": missing_count / max(len(selected), 1),
    }


def score_frame(frame: pd.DataFrame, artifact: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [score_row(row, artifact) for _, row in frame.iterrows()],
        index=frame.index,
    )
