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
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from research.model_v2.train_candidates import select_features
from research.model_v2_002.train_candidates import fit_base, raw_probability
from research.model_v3.evaluation import (
    LockedQuantilePolicy,
    evaluate_forward_gate,
    evaluate_policy,
    rolling_top_quantile_policy,
)
from research.model_v3.model_contract import ARTIFACT_SCHEMA, score_frame


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Freeze or track Kalman V3.003 KR rank-alpha candidate"
    )
    p.add_argument("--matrix", required=True)
    p.add_argument("--matrix-manifest", required=True)
    p.add_argument("--model-spec", required=True)
    p.add_argument("--evaluation-spec", required=True)
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


def _metric(fn, *args, **kwargs) -> float | None:
    try:
        value = float(fn(*args, **kwargs))
    except Exception:
        return None
    return value if math.isfinite(value) else None


def probability_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    x = frame.loc[
        frame["target_label"].notna() & frame["score"].notna()
    ].copy()
    if x.empty:
        return {
            "rows": 0,
            "positive_rate": None,
            "roc_auc": None,
            "brier": None,
            "log_loss": None,
        }
    y = x["target_label"].astype(int).to_numpy()
    p = np.clip(
        pd.to_numeric(x["score"], errors="coerce").to_numpy(dtype=float),
        1e-12,
        1.0 - 1e-12,
    )
    return {
        "rows": int(len(x)),
        "positive_rate": float(np.mean(y)),
        "roc_auc": _metric(roc_auc_score, y, p),
        "brier": _metric(brier_score_loss, y, p),
        "log_loss": _metric(log_loss, y, p, labels=[0, 1]),
    }


def safe_pre_forward(
    matrix: pd.DataFrame,
    *,
    forward_start: pd.Timestamp,
    horizon: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    x = matrix.sort_values("as_of").reset_index(drop=True)
    pre = x.loc[x["as_of"] < forward_start].copy().reset_index(drop=True)
    if len(pre) <= horizon:
        raise RuntimeError("insufficient pre-forward rows for horizon purge")

    purged_dates = pre.iloc[-horizon:]["as_of"].tolist()
    safe = pre.iloc[:-horizon].copy()
    safe = safe.loc[safe["target_label"].notna()].reset_index(drop=True)
    if safe.empty:
        raise RuntimeError("no labeled rows remain after forward-boundary purge")

    audit = {
        "forward_start": forward_start.isoformat(),
        "pre_forward_rows": int(len(pre)),
        "horizon_purge_observations": int(horizon),
        "purged_boundary_rows": int(horizon),
        "purged_boundary_dates": [
            pd.Timestamp(v).isoformat() for v in purged_dates
        ],
        "safe_labeled_rows": int(len(safe)),
        "safe_last_as_of": pd.Timestamp(safe["as_of"].max()).isoformat(),
        "target_outcome_crosses_forward_boundary": False,
    }
    return safe, audit


def candidate_grid(spec: dict[str, Any]) -> list[dict[str, Any]]:
    grid: list[dict[str, Any]] = []
    for feature_count in sorted(
        {int(v) for v in spec.get("candidate_feature_counts", [16])}
    ):
        for c_value in [float(v) for v in spec.get("candidate_c", [0.001])]:
            for class_weight in spec.get("candidate_class_weight", [None]):
                grid.append(
                    {
                        "feature_count": feature_count,
                        "C": c_value,
                        "class_weight": class_weight,
                    }
                )
    return grid


def candidate_id(item: dict[str, Any]) -> str:
    cw = item["class_weight"] if item["class_weight"] is not None else "none"
    return (
        f"f{int(item['feature_count'])}"
        f"_c{float(item['C']):g}"
        f"_cw{cw}"
    )


def expanding_walk_forward_oof(
    frame: pd.DataFrame,
    *,
    spec: dict[str, Any],
    horizon: int,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    wf = spec["walk_forward"]
    initial_train = int(wf["initial_train_observations"])
    block = int(wf["test_block_observations"])
    purge = int(wf["horizon_purge_observations"])
    if purge < horizon:
        raise ValueError("walk-forward purge cannot be smaller than target horizon")

    x = frame.sort_values("as_of").reset_index(drop=True)
    first_test = initial_train + purge
    if len(x) <= first_test:
        raise RuntimeError(
            f"insufficient safe rows for walk-forward: rows={len(x)} first_test={first_test}"
        )

    grid = candidate_grid(spec)
    max_features = max(int(v["feature_count"]) for v in grid)
    rows_by_candidate: dict[str, list[pd.DataFrame]] = {
        candidate_id(v): [] for v in grid
    }
    folds: list[dict[str, Any]] = []

    fold_id = 0
    for test_start in range(first_test, len(x), block):
        test_end = min(test_start + block, len(x))
        train_end = test_start - purge
        train = x.iloc[:train_end].copy()
        test = x.iloc[test_start:test_end].copy()
        if test.empty:
            continue

        ranked = select_features(
            train,
            minimum_coverage=float(spec.get("minimum_feature_coverage", 0.80)),
            maximum_features=max_features,
        )
        fold_record = {
            "fold": fold_id,
            "train_rows": int(len(train)),
            "train_start": pd.Timestamp(train["as_of"].min()).isoformat(),
            "train_end": pd.Timestamp(train["as_of"].max()).isoformat(),
            "test_rows": int(len(test)),
            "test_start": pd.Timestamp(test["as_of"].min()).isoformat(),
            "test_end": pd.Timestamp(test["as_of"].max()).isoformat(),
            "purge_observations": purge,
        }
        folds.append(fold_record)

        for item in grid:
            count = min(int(item["feature_count"]), len(ranked))
            features = ranked[:count]
            imputer, scaler, model = fit_base(
                train,
                features,
                c_value=float(item["C"]),
                class_weight=item["class_weight"],
            )
            probability = raw_probability(
                test,
                features,
                imputer,
                scaler,
                model,
            )
            part = test[
                [
                    "as_of",
                    "anchor_close",
                    "target_forward_return",
                    "target_label",
                ]
            ].copy()
            part["score"] = probability
            part["fold"] = fold_id
            part["fold_train_end"] = train["as_of"].max()
            part["feature_count_realized"] = count
            rows_by_candidate[candidate_id(item)].append(part)

        fold_id += 1

    oof_by_candidate: dict[str, pd.DataFrame] = {}
    for key, parts in rows_by_candidate.items():
        if not parts:
            raise RuntimeError(f"no OOF rows produced for {key}")
        oof = pd.concat(parts, ignore_index=True)
        oof = oof.sort_values("as_of").drop_duplicates("as_of", keep="last")
        oof_by_candidate[key] = oof.reset_index(drop=True)

    return oof_by_candidate, {
        "fold_count": int(len(folds)),
        "folds": folds,
        "initial_train_observations": initial_train,
        "test_block_observations": block,
        "purge_observations": purge,
        "first_oof_as_of": min(
            pd.Timestamp(v["as_of"].min())
            for v in oof_by_candidate.values()
        ).isoformat(),
        "last_oof_as_of": max(
            pd.Timestamp(v["as_of"].max())
            for v in oof_by_candidate.values()
        ).isoformat(),
    }


def select_candidate_and_policy(
    oof_by_candidate: dict[str, pd.DataFrame],
    *,
    model_spec: dict[str, Any],
    evaluation_spec: dict[str, Any],
    horizon: int,
) -> tuple[dict[str, Any], LockedQuantilePolicy, dict[str, Any]]:
    rolling = evaluation_spec["rolling_score_policy"]
    policy_spec = evaluation_spec["policy_selection"]
    costs = evaluation_spec["costs"]
    market_eval = evaluation_spec["markets"]["KR"]
    minimum_oof_rows = int(
        model_spec["walk_forward"].get("minimum_oof_rows", 126)
    )
    minimum_entries = int(policy_spec["minimum_nonoverlap_entries"])

    grid = {candidate_id(v): v for v in candidate_grid(model_spec)}
    results: list[dict[str, Any]] = []
    for key, oof in oof_by_candidate.items():
        pm = probability_metrics(oof)
        for top_fraction in market_eval["candidate_top_fractions"]:
            strategy = evaluate_policy(
                oof,
                top_fraction=float(top_fraction),
                lookback_observations=int(rolling["lookback_observations"]),
                minimum_history_observations=int(
                    rolling["minimum_history_observations"]
                ),
                horizon_observations=horizon,
                round_trip_cost_bps=float(costs["round_trip_cost_bps"]),
            )
            checks = {
                "minimum_oof_rows": int(pm["rows"]) >= minimum_oof_rows,
                "minimum_nonoverlap_entries": (
                    int(strategy["nonoverlap_selected_rows"])
                    >= minimum_entries
                ),
            }
            results.append(
                {
                    "candidate_id": key,
                    "hyperparameters": grid[key],
                    "top_fraction": float(top_fraction),
                    "probability_metrics": pm,
                    "strategy_metrics": strategy,
                    "selection_checks": checks,
                    "selection_eligible": all(checks.values()),
                }
            )

    eligible = [v for v in results if v["selection_eligible"]]
    if not eligible:
        raise RuntimeError("no KR candidate/policy combination passed OOF floors")

    def finite(value: Any, default: float = -999.0) -> float:
        try:
            x = float(value)
        except Exception:
            return default
        return x if math.isfinite(x) else default

    def key(item: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
        strategy = item["strategy_metrics"]
        prob = item["probability_metrics"]
        hp = item["hyperparameters"]
        return (
            finite(strategy.get("nonoverlap_incremental_alpha_mean_net")),
            finite(strategy.get("nonoverlap_win_rate_lift")),
            -float(item["top_fraction"]),
            finite(prob.get("roc_auc")),
            -float(hp["feature_count"]),
            -float(hp["C"]),
        )

    eligible.sort(key=key, reverse=True)
    best = eligible[0]
    best_hp = dict(best["hyperparameters"])
    best_oof = oof_by_candidate[best["candidate_id"]]

    policy = LockedQuantilePolicy(
        top_fraction=float(best["top_fraction"]),
        lookback_observations=int(rolling["lookback_observations"]),
        minimum_history_observations=int(
            rolling["minimum_history_observations"]
        ),
        selection_end=pd.Timestamp(best_oof["as_of"].max()).isoformat(),
        source="EXPANDING_WALK_FORWARD_OOF_PRE_FORWARD_ONLY",
    )

    s = best["strategy_metrics"]
    pre_forward_gate = {
        "minimum_oof_rows": int(best["probability_metrics"]["rows"])
        >= minimum_oof_rows,
        "minimum_nonoverlap_entries": int(s["nonoverlap_selected_rows"])
        >= minimum_entries,
        "positive_incremental_alpha_net": (
            s["nonoverlap_incremental_alpha_mean_net"] is not None
            and float(s["nonoverlap_incremental_alpha_mean_net"]) > 0.0
        ),
        "positive_win_rate_lift": (
            s["nonoverlap_win_rate_lift"] is not None
            and float(s["nonoverlap_win_rate_lift"]) > 0.0
        ),
    }

    audit = {
        "status": "LOCKED",
        "selection_source": "EXPANDING_WALK_FORWARD_OOF_PRE_FORWARD_ONLY",
        "forward_rows_used_for_selection": 0,
        "selected_candidate_id": best["candidate_id"],
        "selected_hyperparameters": best_hp,
        "selected_policy": policy.to_dict(),
        "selected_oof_probability_metrics": best["probability_metrics"],
        "selected_oof_strategy_metrics": best["strategy_metrics"],
        "pre_forward_gate_checks": pre_forward_gate,
        "pre_forward_gate_pass": all(pre_forward_gate.values()),
        "candidate_policy_results": results,
    }
    return best_hp, policy, audit


def freeze_model(
    train: pd.DataFrame,
    *,
    hyperparameters: dict[str, Any],
    policy: LockedQuantilePolicy,
    model_spec: dict[str, Any],
    matrix_manifest: dict[str, Any],
    training_audit: dict[str, Any],
    selection_audit: dict[str, Any],
) -> dict[str, Any]:
    ranked = select_features(
        train,
        minimum_coverage=float(model_spec.get("minimum_feature_coverage", 0.80)),
        maximum_features=int(hyperparameters["feature_count"]),
    )
    selected = ranked[: int(hyperparameters["feature_count"])]
    imputer, scaler, model = fit_base(
        train,
        selected,
        c_value=float(hyperparameters["C"]),
        class_weight=hyperparameters["class_weight"],
    )

    return {
        "artifact_schema": ARTIFACT_SCHEMA,
        "model_version": model_spec["version"],
        "dataset_version": model_spec["dataset_version"],
        "feature_set": model_spec["feature_set"],
        "market": "KR",
        "symbol": model_spec["markets"]["KR"]["symbol"],
        "strategy_version": model_spec["markets"]["KR"]["strategy_version"],
        "objective": "RANK_ALPHA",
        "forward_start": model_spec["forward_start"],
        "horizon_observations": int(
            model_spec["markets"]["KR"]["horizon_observations"]
        ),
        "selected_features": selected,
        "imputer_medians": {
            f: float(v) for f, v in zip(selected, imputer.statistics_)
        },
        "scaler_mean": {
            f: float(v) for f, v in zip(selected, scaler.mean_)
        },
        "scaler_scale": {
            f: float(v) if float(v) != 0.0 else 1.0
            for f, v in zip(selected, scaler.scale_)
        },
        "coefficients": {
            f: float(v) for f, v in zip(selected, model.coef_[0])
        },
        "intercept": float(model.intercept_[0]),
        "hyperparameters": {
            "C": float(hyperparameters["C"]),
            "class_weight": hyperparameters["class_weight"],
            "regularization": "l2_via_l1_ratio_0",
            "solver": "lbfgs",
            "feature_count": len(selected),
        },
        "rank_policy": policy.to_dict(),
        "training_boundary_audit": training_audit,
        "pre_forward_selection": {
            "selected_candidate_id": selection_audit["selected_candidate_id"],
            "selected_oof_probability_metrics": selection_audit[
                "selected_oof_probability_metrics"
            ],
            "selected_oof_strategy_metrics": selection_audit[
                "selected_oof_strategy_metrics"
            ],
            "pre_forward_gate_checks": selection_audit[
                "pre_forward_gate_checks"
            ],
            "pre_forward_gate_pass": selection_audit[
                "pre_forward_gate_pass"
            ],
        },
        "training_window": {
            "train_start": pd.Timestamp(train["as_of"].min()).isoformat(),
            "train_end": pd.Timestamp(train["as_of"].max()).isoformat(),
            "train_rows": int(len(train)),
        },
        "matrix_lineage_sha256": matrix_manifest.get("lineage_sha256"),
        "matrix_sha256_at_freeze": matrix_manifest.get("matrix_sha256"),
        "sklearn_version": sklearn.__version__,
        "frozen": True,
        "retrain_after_forward_start": False,
        "research_only": True,
        "shadow_only": True,
        "production_write": False,
        "neon_write": False,
        "trade_execution": False,
        "frozen_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }


def make_score_stream(
    matrix: pd.DataFrame,
    artifact: dict[str, Any],
) -> pd.DataFrame:
    scored = score_frame(matrix, artifact)
    out = matrix[
        [
            "as_of",
            "anchor_close",
            "target_forward_return",
            "target_label",
        ]
    ].copy()
    out["score"] = scored["score"].to_numpy()
    out["missing_feature_ratio"] = scored["missing_feature_ratio"].to_numpy()
    return out.sort_values("as_of").reset_index(drop=True)


def current_shadow_signal(
    combined_scores: pd.DataFrame,
    *,
    policy: LockedQuantilePolicy,
    forward_start: pd.Timestamp,
) -> dict[str, Any]:
    scored = rolling_top_quantile_policy(
        combined_scores,
        top_fraction=policy.top_fraction,
        lookback_observations=policy.lookback_observations,
        minimum_history_observations=policy.minimum_history_observations,
    )
    if scored.empty:
        return {"status": "NO_SCORE_ROWS", "shadow_entry": False}
    latest = scored.iloc[-1]
    as_of = pd.Timestamp(latest["as_of"])
    eligible_era = as_of >= forward_start
    ready = bool(latest["policy_ready"])
    selected = bool(latest["selected"])
    return {
        "status": "READY" if eligible_era and ready else "TRACKING",
        "as_of": as_of.isoformat(),
        "score": float(latest["score"]),
        "score_cutoff": (
            float(latest["score_cutoff"])
            if pd.notna(latest["score_cutoff"])
            else None
        ),
        "top_fraction": float(policy.top_fraction),
        "policy_ready": ready,
        "forward_era": eligible_era,
        "raw_shadow_entry": bool(eligible_era and ready and selected),
        "shadow_entry": bool(eligible_era and ready and selected),
        "live_execution": False,
    }


def main() -> int:
    args = parse_args()
    matrix_path = Path(args.matrix)
    manifest_path = Path(args.matrix_manifest)
    model_spec = json.loads(Path(args.model_spec).read_text(encoding="utf-8"))
    evaluation_spec = json.loads(
        Path(args.evaluation_spec).read_text(encoding="utf-8")
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    matrix = pd.read_parquet(matrix_path)
    matrix["as_of"] = pd.to_datetime(matrix["as_of"], errors="raise")
    matrix = matrix.sort_values("as_of").reset_index(drop=True)
    matrix_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    forward_start = pd.Timestamp(model_spec["forward_start"])
    if pd.Timestamp(evaluation_spec["forward_start"]) != forward_start:
        raise RuntimeError("model/evaluation forward_start mismatch")

    market_spec = model_spec["markets"]["KR"]
    horizon = int(market_spec["horizon_observations"])
    if int(evaluation_spec["markets"]["KR"]["horizon_observations"]) != horizon:
        raise RuntimeError("model/evaluation KR horizon mismatch")

    model_path = output_dir / "model.json"
    reference_path = output_dir / "policy_reference_scores.parquet"
    selection_path = output_dir / "pre_forward_selection.json"
    oof_path = output_dir / "selected_oof_scores.parquet"

    freeze_created = False
    if model_path.exists():
        artifact = json.loads(model_path.read_text(encoding="utf-8"))
        if artifact.get("artifact_schema") != ARTIFACT_SCHEMA:
            raise RuntimeError("existing frozen artifact schema mismatch")
        if artifact.get("model_version") != model_spec["version"]:
            raise RuntimeError("existing frozen artifact model version mismatch")
        if artifact.get("frozen") is not True:
            raise RuntimeError("existing artifact is not frozen")
        if not reference_path.exists():
            raise RuntimeError("frozen policy reference score file missing")
        if not selection_path.exists():
            raise RuntimeError("frozen pre-forward selection audit missing")
        mode = "TRACK_EXISTING_FROZEN_MODEL"
        selection_audit = json.loads(selection_path.read_text(encoding="utf-8"))
    else:
        safe_train, boundary_audit = safe_pre_forward(
            matrix,
            forward_start=forward_start,
            horizon=horizon,
        )
        oof_by_candidate, wf_audit = expanding_walk_forward_oof(
            safe_train,
            spec=model_spec,
            horizon=horizon,
        )
        hyperparameters, policy, selection_audit = select_candidate_and_policy(
            oof_by_candidate,
            model_spec=model_spec,
            evaluation_spec=evaluation_spec,
            horizon=horizon,
        )
        selection_audit["walk_forward"] = wf_audit
        selection_audit["training_boundary"] = boundary_audit

        selected_oof = oof_by_candidate[
            selection_audit["selected_candidate_id"]
        ].copy()
        atomic_parquet(selected_oof, oof_path)

        artifact = freeze_model(
            safe_train,
            hyperparameters=hyperparameters,
            policy=policy,
            model_spec=model_spec,
            matrix_manifest=matrix_manifest,
            training_audit=boundary_audit,
            selection_audit=selection_audit,
        )
        model_sha = atomic_json(model_path, artifact)
        selection_audit["frozen_model_sha256"] = model_sha
        atomic_json(selection_path, selection_audit)

        # Freeze OOF pre-forward scores as the permanent score-distribution
        # reference used by the rolling quantile policy.
        reference = selected_oof[
            [
                "as_of",
                "anchor_close",
                "target_forward_return",
                "target_label",
                "score",
            ]
        ].copy()
        if pd.Timestamp(reference["as_of"].max()) >= forward_start:
            raise RuntimeError("OOF policy reference crosses forward boundary")
        atomic_parquet(reference, reference_path)
        freeze_created = True
        mode = "FREEZE_NEW_MODEL"

    policy_payload = artifact["rank_policy"]
    policy = LockedQuantilePolicy(
        top_fraction=float(policy_payload["top_fraction"]),
        lookback_observations=int(policy_payload["lookback_observations"]),
        minimum_history_observations=int(
            policy_payload["minimum_history_observations"]
        ),
        selection_end=str(policy_payload["selection_end"]),
        source=str(policy_payload["source"]),
    )

    frozen_reference = pd.read_parquet(reference_path)
    frozen_reference["as_of"] = pd.to_datetime(
        frozen_reference["as_of"], errors="raise"
    )
    if pd.Timestamp(frozen_reference["as_of"].max()) >= forward_start:
        raise RuntimeError("frozen reference contains forward rows")

    forward_matrix = matrix.loc[matrix["as_of"] >= forward_start].copy()
    if forward_matrix.empty:
        forward_scores = pd.DataFrame(
            columns=[
                "as_of",
                "anchor_close",
                "target_forward_return",
                "target_label",
                "score",
                "missing_feature_ratio",
            ]
        )
    else:
        forward_scores = make_score_stream(forward_matrix, artifact)

    atomic_parquet(
        forward_scores,
        output_dir / "forward_scores_latest.parquet",
    )
    combined = pd.concat(
        [
            frozen_reference[
                [
                    "as_of",
                    "anchor_close",
                    "target_forward_return",
                    "target_label",
                    "score",
                ]
            ],
            forward_scores[
                [
                    "as_of",
                    "anchor_close",
                    "target_forward_return",
                    "target_label",
                    "score",
                ]
            ],
        ],
        ignore_index=True,
    ).sort_values("as_of").reset_index(drop=True)

    forward_gate = evaluate_forward_gate(
        combined,
        policy=policy,
        forward_start=forward_start,
        horizon_observations=horizon,
        round_trip_cost_bps=float(
            evaluation_spec["costs"]["round_trip_cost_bps"]
        ),
        gate=evaluation_spec["promotion_gate"],
    )
    pre_forward_pass = bool(
        artifact["pre_forward_selection"]["pre_forward_gate_pass"]
    )
    promotion_eligible = bool(
        pre_forward_pass and forward_gate["promotion_eligible"]
    )

    signal = current_shadow_signal(
        combined,
        policy=policy,
        forward_start=forward_start,
    )

    report = {
        "schema_version": "kalman-v3-003-kr-forward-report-v1",
        "status": "READY",
        "mode": mode,
        "freeze_created": freeze_created,
        "model_version": artifact["model_version"],
        "strategy_version": artifact["strategy_version"],
        "artifact_schema": artifact["artifact_schema"],
        "model_sha256": sha256_file(model_path),
        "frozen_reference_sha256": sha256_file(reference_path),
        "forward_start": forward_start.isoformat(),
        "pre_forward_gate_pass": pre_forward_pass,
        "pre_forward_selection": artifact["pre_forward_selection"],
        "locked_policy": policy.to_dict(),
        "forward_gate": forward_gate,
        "promotion_eligible": promotion_eligible,
        "current_shadow_signal": signal,
        "matrix_as_of": pd.Timestamp(matrix["as_of"].max()).isoformat(),
        "forward_score_rows": int(len(forward_scores)),
        "research_only": True,
        "shadow_only": True,
        "production_write": False,
        "neon_write": False,
        "trade_execution": False,
        "retrained_existing_frozen_model": False,
        "evaluated_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    atomic_json(output_dir / "latest.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
