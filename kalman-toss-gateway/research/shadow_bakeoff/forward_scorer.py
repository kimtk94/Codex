from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.quant_stack.contracts import stable_hash
from research.quant_stack.historical_backfill import (
    _decision_signals,
    _fit_model,
    _predict_probability,
)
from research.quant_stack.historical_v2_candidate import (
    _nested_feature_consensus,
    _tune_inner_model,
)
from research.quant_stack.historical_v3_return_regime import (
    _fit_regime_model,
    _fit_return_model,
    _predict_regime,
    _predict_return,
    build_signals as build_v3_signals,
    nested_return_feature_consensus,
    tune_regime_c,
    tune_return_model,
    tune_trading_gate,
)


def _sha(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_matrix(matrix_dir: Path, market: str) -> pd.DataFrame:
    path = matrix_dir / f"{market.lower()}_matrix.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_parquet(path)
    if "as_of" not in frame.columns:
        raise ValueError(f"{path} missing as_of")
    frame = frame.copy()
    frame["as_of"] = pd.to_datetime(frame["as_of"], utc=True, errors="raise")
    frame = (
        frame.sort_values("as_of")
        .drop_duplicates("as_of", keep="last")
        .reset_index(drop=True)
    )
    return frame


DEFAULT_MINIMUM_FEATURE_COVERAGE = 0.80


def _development_tail(
    frame: pd.DataFrame,
    *,
    target_col: str,
    observations: int,
) -> pd.DataFrame:
    labeled = frame.loc[frame[target_col].notna()].copy()
    if len(labeled) < observations:
        raise RuntimeError(
            f"insufficient labeled rows for final refit: "
            f"{len(labeled)} < {observations}"
        )
    return labeled.tail(observations).reset_index(drop=True)


def _validate_forward_row(
    latest: pd.DataFrame,
    *,
    trained_through: pd.Timestamp,
    features: list[str],
    max_missing_feature_ratio: float,
) -> float:
    as_of = pd.Timestamp(latest["as_of"].iloc[0])
    trained = pd.Timestamp(trained_through)
    if as_of <= trained:
        raise RuntimeError(
            f"latest row is not forward of training window: "
            f"latest={as_of} trained_through={trained}"
        )
    missing = latest[features].apply(
        pd.to_numeric,
        errors="coerce",
    ).isna()
    ratio = float(missing.sum(axis=1).iloc[0]) / max(len(features), 1)
    limit = float(max_missing_feature_ratio)
    if ratio > limit:
        raise RuntimeError(
            f"latest selected-feature missing ratio too high: "
            f"{ratio:.4f} > {limit:.4f}"
        )
    return ratio


def score_v2_forward(
    *,
    matrix_dir: Path,
    market: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    market_spec = spec["markets"][market]
    symbol = str(market_spec["symbol"])
    horizon = int(market_spec["horizon_observations"])
    frame = _load_matrix(matrix_dir, market)
    development = _development_tail(
        frame,
        target_col="target_label",
        observations=int(spec.get("outer_development_observations", 756)),
    )

    features, ranking, inner_folds = _nested_feature_consensus(
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
    imputer, scaler, model = _fit_model(
        development,
        features,
        c_value=best_c,
    )

    latest = frame.iloc[[-1]].copy()
    max_missing_feature_ratio = min(
        0.20,
        max(
            0.0,
            1.0
            - float(
                spec.get(
                    "minimum_feature_coverage",
                    DEFAULT_MINIMUM_FEATURE_COVERAGE,
                )
            ),
        ),
    )
    missing_feature_ratio = _validate_forward_row(
        latest,
        trained_through=pd.Timestamp(development["as_of"].max()),
        features=features,
        max_missing_feature_ratio=max_missing_feature_ratio,
    )
    probability = float(
        _predict_probability(
            latest,
            features,
            imputer,
            scaler,
            model,
        )[0]
    )
    parameter_hash = stable_hash(
        {
            "version": spec["version"],
            "market": market,
            "trained_start": development["as_of"].min(),
            "trained_through": development["as_of"].max(),
            "features": features,
            "c": best_c,
            "threshold": threshold,
        }
    )
    run_id = f"{market.lower()}-v2-forward-{parameter_hash[:16]}"
    model_output = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "market": market,
                "symbol": symbol,
                "as_of": latest["as_of"].iloc[0],
                "fold_id": -1,
                "model_version": spec["version"],
                "feature_version": spec["feature_set"],
                "probability": probability,
                "score": probability,
                "probability_threshold": threshold,
                "parameter_hash": parameter_hash,
            }
        ]
    )
    signal_frame = _decision_signals(
        model_output,
        symbol=symbol,
    )
    signal = signal_frame.iloc[0].to_dict()

    return {
        "status": "READY",
        "market": market,
        "model_family": "V2_NESTED_FINAL_REFIT",
        "symbol": symbol,
        "as_of": pd.Timestamp(signal["signal_ts"]).isoformat(),
        "run_id": run_id,
        "signal": str(signal["signal"]),
        "entry_allowed": bool(signal["entry_allowed"]),
        "probability": probability,
        "probability_threshold": float(threshold),
        "exit_threshold": float(signal["exit_threshold"]),
        "trained_start": pd.Timestamp(
            development["as_of"].min()
        ).isoformat(),
        "trained_through": pd.Timestamp(
            development["as_of"].max()
        ).isoformat(),
        "selected_feature_count": len(features),
        "missing_feature_ratio": missing_feature_ratio,
        "max_missing_feature_ratio": max_missing_feature_ratio,
        "selected_features": features,
        "feature_consensus": ranking,
        "best_c": float(best_c),
        "candidate_c_metrics": c_rows,
        "threshold_metrics": threshold_rows,
        "parameter_hash": parameter_hash,
        "research_only": True,
        "shadow_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }


def score_v3_forward(
    *,
    matrix_dir: Path,
    market: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    market_spec = spec["markets"][market]
    symbol = str(market_spec["symbol"])
    horizon = int(market_spec["horizon_observations"])
    model_type = str(market_spec["model_type"])
    regime_return_threshold = float(
        market_spec.get("regime_return_threshold", 0.0)
    )

    frame = _load_matrix(matrix_dir, market)
    development = _development_tail(
        frame,
        target_col="target_forward_return",
        observations=int(spec.get("outer_development_observations", 756)),
    )

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
            float(x)
            for x in spec.get("entry_quantile_grid", [0.6, 0.7, 0.8])
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
    development_pred = _predict_return(
        development,
        features,
        return_bundle,
    )
    entry_threshold = float(
        np.quantile(
            development_pred,
            float(trading_gate["entry_quantile"]),
        )
    )

    latest = frame.iloc[[-1]].copy()
    max_missing_feature_ratio = min(
        0.20,
        max(
            0.0,
            1.0
            - float(
                spec.get(
                    "minimum_feature_coverage",
                    DEFAULT_MINIMUM_FEATURE_COVERAGE,
                )
            ),
        ),
    )
    missing_feature_ratio = _validate_forward_row(
        latest,
        trained_through=pd.Timestamp(development["as_of"].max()),
        features=features,
        max_missing_feature_ratio=max_missing_feature_ratio,
    )
    predicted_return = float(
        _predict_return(latest, features, return_bundle)[0]
    )
    regime_probability = float(
        _predict_regime(latest, features, regime_bundle)[0]
    )

    parameter_hash = stable_hash(
        {
            "version": spec["version"],
            "market": market,
            "trained_start": development["as_of"].min(),
            "trained_through": development["as_of"].max(),
            "features": features,
            "model_type": model_type,
            "model_params": model_params,
            "regime_c": regime_c,
            "trading_gate": trading_gate,
            "entry_threshold": entry_threshold,
        }
    )
    run_id = f"{market.lower()}-v3-forward-{parameter_hash[:16]}"
    model_output = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "market": market,
                "symbol": symbol,
                "as_of": latest["as_of"].iloc[0],
                "fold_id": -1,
                "model_version": spec["version"],
                "feature_version": spec["feature_set"],
                "predicted_return": predicted_return,
                "score": predicted_return,
                "regime_probability": regime_probability,
                "entry_return_threshold": entry_threshold,
                "entry_quantile": float(trading_gate["entry_quantile"]),
                "regime_probability_gate": float(
                    trading_gate["regime_probability_gate"]
                ),
                "parameter_hash": parameter_hash,
            }
        ]
    )
    signal_frame = build_v3_signals(
        model_output,
        symbol=symbol,
    )
    signal = signal_frame.iloc[0].to_dict()

    return {
        "status": "READY",
        "market": market,
        "model_family": "V3_RETURN_REGIME_FINAL_REFIT",
        "symbol": symbol,
        "as_of": pd.Timestamp(signal["signal_ts"]).isoformat(),
        "run_id": run_id,
        "signal": str(signal["signal"]),
        "entry_allowed": bool(signal["entry_allowed"]),
        "predicted_return": predicted_return,
        "regime_probability": regime_probability,
        "entry_return_threshold": entry_threshold,
        "entry_quantile": float(trading_gate["entry_quantile"]),
        "regime_probability_gate": float(
            trading_gate["regime_probability_gate"]
        ),
        "trained_start": pd.Timestamp(
            development["as_of"].min()
        ).isoformat(),
        "trained_through": pd.Timestamp(
            development["as_of"].max()
        ).isoformat(),
        "selected_feature_count": len(features),
        "missing_feature_ratio": missing_feature_ratio,
        "max_missing_feature_ratio": max_missing_feature_ratio,
        "selected_features": features,
        "feature_consensus": feature_ranking,
        "model_type": model_type,
        "best_model_params": model_params,
        "model_tuning": model_tuning,
        "best_regime_c": float(regime_c),
        "regime_tuning": regime_tuning,
        "trading_gate": trading_gate,
        "trading_tuning": trading_tuning,
        "parameter_hash": parameter_hash,
        "research_only": True,
        "shadow_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }


def append_signal_history(
    history_path: Path,
    signal: dict[str, Any],
) -> pd.DataFrame:
    row = pd.DataFrame(
        [
            {
                "run_id": signal["run_id"],
                "market": signal["market"],
                "symbol": signal["symbol"],
                "signal_ts": pd.Timestamp(signal["as_of"]),
                "signal": signal["signal"],
                "entry_allowed": signal["entry_allowed"],
                "model_family": signal["model_family"],
                "parameter_hash": signal["parameter_hash"],
                "recorded_at": pd.Timestamp.now(tz="UTC"),
            }
        ]
    )
    if history_path.exists():
        old = pd.read_parquet(history_path)
        old["signal_ts"] = pd.to_datetime(
            old["signal_ts"],
            utc=True,
            errors="raise",
        )
        out = pd.concat([old, row], ignore_index=True)
    else:
        out = row

    out["signal_ts"] = pd.to_datetime(
        out["signal_ts"],
        utc=True,
        errors="raise",
    )
    if "recorded_at" not in out.columns:
        out["recorded_at"] = pd.NaT
    out["recorded_at"] = pd.to_datetime(
        out["recorded_at"],
        utc=True,
        errors="coerce",
    )
    out = (
        out.sort_values(
            ["signal_ts", "recorded_at"],
            kind="stable",
            na_position="first",
        )
        .drop_duplicates(
            ["market", "symbol", "signal_ts"],
            keep="last",
        )
        .reset_index(drop=True)
    )
    history_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = history_path.with_suffix(".tmp.parquet")
    out.to_parquet(tmp, index=False)
    tmp.replace(history_path)
    return out


def safe_signal_payload(signal: dict[str, Any]) -> dict[str, Any]:
    keep = {
        key: value
        for key, value in signal.items()
        if key not in {
            "feature_consensus",
            "model_tuning",
            "regime_tuning",
            "trading_tuning",
            "candidate_c_metrics",
            "threshold_metrics",
        }
    }
    keep["allow_trade_shadow"] = False
    keep["production_promotion"] = False
    keep["live_execution"] = False
    keep["toss_execution"] = False
    keep["neon_write"] = False
    return keep
