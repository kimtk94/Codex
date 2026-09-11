from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


ARTIFACT_SCHEMA = "kalman_logit_json_v1"


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
    except Exception:
        return default
    return x if math.isfinite(x) else default


def score_row(row: pd.Series | dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    if artifact.get("artifact_schema") != ARTIFACT_SCHEMA:
        raise ValueError(f"unsupported artifact schema: {artifact.get('artifact_schema')!r}")

    selected = list(artifact["selected_features"])
    medians = artifact["imputer_medians"]
    means = artifact["scaler_mean"]
    scales = artifact["scaler_scale"]
    coefficients = artifact["coefficients"]

    raw_values: dict[str, float] = {}
    standardized: dict[str, float] = {}
    missing_count = 0
    z = float(artifact["intercept"])

    for feature in selected:
        value = row.get(feature) if hasattr(row, "get") else None
        try:
            value_float = float(value)
        except Exception:
            value_float = float("nan")

        if not math.isfinite(value_float):
            missing_count += 1
            value_float = _finite_float(medians.get(feature), 0.0)

        mean = _finite_float(means.get(feature), 0.0)
        scale = _finite_float(scales.get(feature), 1.0)
        if scale == 0:
            scale = 1.0
        standardized_value = (value_float - mean) / scale

        raw_values[feature] = value_float
        standardized[feature] = standardized_value
        z += standardized_value * _finite_float(coefficients.get(feature), 0.0)

    probability = 1.0 / (1.0 + math.exp(-max(min(z, 50.0), -50.0)))
    threshold = float(artifact["probability_threshold"])
    return {
        "probability_up": probability,
        "probability_threshold": threshold,
        "shadow_entry": probability >= threshold,
        "selected_feature_count": len(selected),
        "missing_feature_count": missing_count,
        "missing_feature_ratio": missing_count / max(len(selected), 1),
        "logit": z,
        "imputed_values": raw_values,
        "standardized_values": standardized,
    }


def score_frame(frame: pd.DataFrame, artifact: dict[str, Any]) -> pd.DataFrame:
    rows = [score_row(row, artifact) for _, row in frame.iterrows()]
    return pd.DataFrame(rows, index=frame.index)
