from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn

from research.model_v2.train_candidates import select_features
from research.model_v2_002.train_candidates import fit_base
from research.model_v3.evaluation import (
    LockedQuantilePolicy,
    evaluate_forward_gate,
    evaluate_policy,
)
from research.model_v3.kr_candidate import (
    atomic_json,
    atomic_parquet,
    candidate_grid,
    candidate_id,
    current_shadow_signal,
    expanding_walk_forward_oof,
    probability_metrics,
    safe_pre_forward,
    sha256_file,
    update_forward_ledgers,
)
from research.model_v3.model_contract import ARTIFACT_SCHEMA, score_frame


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Freeze or track Kalman V3.003 US hurdle-target candidate"
    )
    p.add_argument("--matrix", required=True)
    p.add_argument("--matrix-manifest", required=True)
    p.add_argument("--model-spec", required=True)
    p.add_argument("--evaluation-spec", required=True)
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def _finite(value: Any, default: float = -999.0) -> float:
    try:
        x = float(value)
    except Exception:
        return default
    return x if math.isfinite(x) else default


def with_hurdle_label(
    frame: pd.DataFrame,
    hurdle: float,
) -> pd.DataFrame:
    x = frame.copy()
    ret = pd.to_numeric(x["target_forward_return"], errors="coerce")
    x["target_label"] = (ret > float(hurdle)).astype(float)
    x.loc[ret.isna(), "target_label"] = np.nan
    return x


def evaluate_half_stability(
    oof: pd.DataFrame,
    *,
    top_fraction: float,
    evaluation_spec: dict[str, Any],
    horizon: int,
) -> dict[str, Any]:
    x = oof.sort_values("as_of").reset_index(drop=True)
    midpoint = len(x) // 2
    parts = {
        "first_half": x.iloc[:midpoint].copy(),
        "second_half": x.iloc[midpoint:].copy(),
    }
    rolling = evaluation_spec["rolling_score_policy"]
    costs = evaluation_spec["costs"]
    result: dict[str, Any] = {}
    for name, part in parts.items():
        result[name] = evaluate_policy(
            part,
            top_fraction=float(top_fraction),
            lookback_observations=int(rolling["lookback_observations"]),
            minimum_history_observations=int(
                rolling["minimum_history_observations"]
            ),
            horizon_observations=horizon,
            round_trip_cost_bps=float(costs["round_trip_cost_bps"]),
        )
    return result


def select_us_candidate(
    safe_train: pd.DataFrame,
    *,
    model_spec: dict[str, Any],
    evaluation_spec: dict[str, Any],
    horizon: int,
) -> tuple[
    dict[str, Any] | None,
    LockedQuantilePolicy | None,
    dict[str, Any],
    pd.DataFrame | None,
    dict[str, Any] | None,
]:
    rolling = evaluation_spec["rolling_score_policy"]
    costs = evaluation_spec["costs"]
    market_eval = evaluation_spec["markets"]["US"]
    gate = model_spec["selection_gate"]
    minimum_oof = int(model_spec["walk_forward"]["minimum_oof_rows"])
    minimum_entries = int(gate["minimum_nonoverlap_entries"])
    minimum_half_entries = int(gate["minimum_half_nonoverlap_entries"])
    grid = {candidate_id(v): v for v in candidate_grid(model_spec)}

    all_rows: list[dict[str, Any]] = []
    hurdle_audits: dict[str, Any] = {}
    oof_lookup: dict[tuple[float, str], pd.DataFrame] = {}

    for hurdle in [float(v) for v in model_spec["target_hurdles"]]:
        labeled = with_hurdle_label(safe_train, hurdle)
        oof_by_candidate, wf_audit = expanding_walk_forward_oof(
            labeled,
            spec=model_spec,
            horizon=horizon,
        )
        hurdle_key = f"{hurdle:.6f}"
        hurdle_audits[hurdle_key] = wf_audit

        for key, oof in oof_by_candidate.items():
            oof_lookup[(hurdle, key)] = oof
            pm = probability_metrics(oof)

            for fraction in market_eval["candidate_top_fractions"]:
                strategy = evaluate_policy(
                    oof,
                    top_fraction=float(fraction),
                    lookback_observations=int(
                        rolling["lookback_observations"]
                    ),
                    minimum_history_observations=int(
                        rolling["minimum_history_observations"]
                    ),
                    horizon_observations=horizon,
                    round_trip_cost_bps=float(
                        costs["round_trip_cost_bps"]
                    ),
                )
                halves = evaluate_half_stability(
                    oof,
                    top_fraction=float(fraction),
                    evaluation_spec=evaluation_spec,
                    horizon=horizon,
                )
                net = strategy["nonoverlap_selected_net"]
                first = halves["first_half"]
                second = halves["second_half"]

                checks = {
                    "minimum_oof_rows": int(pm["rows"]) >= minimum_oof,
                    "minimum_nonoverlap_entries": (
                        int(strategy["nonoverlap_selected_rows"])
                        >= minimum_entries
                    ),
                    "minimum_first_half_entries": (
                        int(first["nonoverlap_selected_rows"])
                        >= minimum_half_entries
                    ),
                    "minimum_second_half_entries": (
                        int(second["nonoverlap_selected_rows"])
                        >= minimum_half_entries
                    ),
                    "positive_incremental_alpha_net": (
                        strategy[
                            "nonoverlap_incremental_alpha_mean_net"
                        ] is not None
                        and float(
                            strategy[
                                "nonoverlap_incremental_alpha_mean_net"
                            ]
                        ) > 0.0
                    ),
                    "positive_win_rate_lift": (
                        strategy["nonoverlap_win_rate_lift"] is not None
                        and float(strategy["nonoverlap_win_rate_lift"]) > 0.0
                    ),
                    "positive_net_mean": (
                        net["mean"] is not None and float(net["mean"]) > 0.0
                    ),
                    "positive_net_compounded_return": (
                        net["compounded_return"] is not None
                        and float(net["compounded_return"]) > 0.0
                    ),
                    "positive_alpha_first_half": (
                        first[
                            "nonoverlap_incremental_alpha_mean_net"
                        ] is not None
                        and float(
                            first[
                                "nonoverlap_incremental_alpha_mean_net"
                            ]
                        ) > 0.0
                    ),
                    "positive_alpha_second_half": (
                        second[
                            "nonoverlap_incremental_alpha_mean_net"
                        ] is not None
                        and float(
                            second[
                                "nonoverlap_incremental_alpha_mean_net"
                            ]
                        ) > 0.0
                    ),
                }
                all_rows.append(
                    {
                        "target_hurdle": hurdle,
                        "candidate_id": key,
                        "hyperparameters": grid[key],
                        "top_fraction": float(fraction),
                        "probability_metrics": pm,
                        "strategy_metrics": strategy,
                        "stability_halves": halves,
                        "joint_gate_checks": checks,
                        "joint_gate_pass": all(checks.values()),
                    }
                )

    joint = [row for row in all_rows if row["joint_gate_pass"]]

    def rank_key(item: dict[str, Any]) -> tuple[float, float, float, float, float]:
        strategy = item["strategy_metrics"]
        halves = item["stability_halves"]
        min_half_alpha = min(
            _finite(
                halves["first_half"].get(
                    "nonoverlap_incremental_alpha_mean_net"
                )
            ),
            _finite(
                halves["second_half"].get(
                    "nonoverlap_incremental_alpha_mean_net"
                )
            ),
        )
        return (
            min_half_alpha,
            _finite(strategy.get("nonoverlap_incremental_alpha_mean_net")),
            _finite(strategy.get("nonoverlap_win_rate_lift")),
            -float(item["top_fraction"]),
            _finite(item["probability_metrics"].get("roc_auc")),
        )

    joint.sort(key=rank_key, reverse=True)
    audit: dict[str, Any] = {
        "status": "READY",
        "objective": "RANK_ALPHA_AFTER_TARGET_REDESIGN",
        "target_design": model_spec["target_design"],
        "target_hurdles": model_spec["target_hurdles"],
        "selection_source": (
            "PRE_FORWARD_EXPANDING_WALK_FORWARD_OOF_WITH_HALF_STABILITY"
        ),
        "forward_rows_used_for_selection": 0,
        "auc_is_diagnostic_only": True,
        "candidate_policy_count": len(all_rows),
        "joint_gate_passing_count": len(joint),
        "joint_gate_passing_top": joint[:15],
        "walk_forward_by_hurdle": hurdle_audits,
    }

    if not joint:
        audit.update(
            {
                "selected_target_hurdle": None,
                "selected_candidate_id": None,
                "selected_hyperparameters": None,
                "selected_policy": None,
                "selected_oof_probability_metrics": None,
                "selected_oof_strategy_metrics": None,
                "selected_stability_halves": None,
                "pre_forward_gate_checks": None,
                "pre_forward_gate_pass": False,
                "next_action": "REDESIGN_US_MODEL_FAMILY",
            }
        )
        return None, None, audit, None, None

    best = joint[0]
    hurdle = float(best["target_hurdle"])
    best_id = str(best["candidate_id"])
    best_oof = oof_lookup[(hurdle, best_id)].copy()
    hp = dict(best["hyperparameters"])
    policy = LockedQuantilePolicy(
        top_fraction=float(best["top_fraction"]),
        lookback_observations=int(rolling["lookback_observations"]),
        minimum_history_observations=int(
            rolling["minimum_history_observations"]
        ),
        selection_end=pd.Timestamp(best_oof["as_of"].max()).isoformat(),
        source="US_HURDLE_OOF_STABILITY_PRE_FORWARD_ONLY",
    )
    audit.update(
        {
            "selected_target_hurdle": hurdle,
            "selected_candidate_id": best_id,
            "selected_hyperparameters": hp,
            "selected_policy": policy.to_dict(),
            "selected_oof_probability_metrics": best[
                "probability_metrics"
            ],
            "selected_oof_strategy_metrics": best["strategy_metrics"],
            "selected_stability_halves": best["stability_halves"],
            "pre_forward_gate_checks": best["joint_gate_checks"],
            "pre_forward_gate_pass": True,
            "next_action": "FREEZE_US_HURDLE_FORWARD_CANDIDATE",
        }
    )
    return hp, policy, audit, best_oof, {"target_hurdle": hurdle}


def freeze_us_model(
    train: pd.DataFrame,
    *,
    target_hurdle: float,
    hyperparameters: dict[str, Any],
    policy: LockedQuantilePolicy,
    model_spec: dict[str, Any],
    matrix_manifest: dict[str, Any],
    training_audit: dict[str, Any],
    selection_audit: dict[str, Any],
) -> dict[str, Any]:
    labeled = with_hurdle_label(train, target_hurdle)
    ranked = select_features(
        labeled,
        minimum_coverage=float(
            model_spec.get("minimum_feature_coverage", 0.80)
        ),
        maximum_features=int(hyperparameters["feature_count"]),
    )
    selected = ranked[: int(hyperparameters["feature_count"])]
    imputer, scaler, model = fit_base(
        labeled,
        selected,
        c_value=float(hyperparameters["C"]),
        class_weight=hyperparameters["class_weight"],
    )
    market = model_spec["markets"]["US"]
    return {
        "artifact_schema": ARTIFACT_SCHEMA,
        "model_version": model_spec["version"],
        "dataset_version": model_spec["dataset_version"],
        "feature_set": model_spec["feature_set"],
        "market": "US",
        "symbol": market["symbol"],
        "strategy_version": market["strategy_version"],
        "objective": model_spec["objective"],
        "target_design": model_spec["target_design"],
        "target_hurdle": float(target_hurdle),
        "score_semantics": (
            "RANK_SCORE_FOR_5D_RETURN_HURDLE_NOT_CALIBRATED_PROBABILITY"
        ),
        "forward_start": model_spec["forward_start"],
        "horizon_observations": int(market["horizon_observations"]),
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
            "selected_target_hurdle": float(target_hurdle),
            "selected_candidate_id": selection_audit[
                "selected_candidate_id"
            ],
            "selected_oof_probability_metrics": selection_audit[
                "selected_oof_probability_metrics"
            ],
            "selected_oof_strategy_metrics": selection_audit[
                "selected_oof_strategy_metrics"
            ],
            "selected_stability_halves": selection_audit[
                "selected_stability_halves"
            ],
            "pre_forward_gate_checks": selection_audit[
                "pre_forward_gate_checks"
            ],
            "pre_forward_gate_pass": selection_audit[
                "pre_forward_gate_pass"
            ],
            "auc_is_diagnostic_only": True,
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


def build_reference_with_bridge(
    *,
    selected_oof: pd.DataFrame,
    matrix: pd.DataFrame,
    artifact: dict[str, Any],
    forward_start: pd.Timestamp,
    safe_train_end: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    oof_ref = selected_oof[
        [
            "as_of",
            "anchor_close",
            "target_forward_return",
            "target_label",
            "score",
        ]
    ].copy()
    oof_ref["reference_source"] = "EXPANDING_WALK_FORWARD_OOF"

    bridge = matrix.loc[
        (matrix["as_of"] > safe_train_end)
        & (matrix["as_of"] < forward_start)
    ].copy()
    bridge = (
        bridge.sort_values("as_of")
        .drop_duplicates("as_of", keep="last")
        .reset_index(drop=True)
    )
    if bridge.empty:
        bridge_ref = pd.DataFrame(columns=oof_ref.columns)
    else:
        scored = score_frame(bridge, artifact)
        bridge_ref = pd.DataFrame(
            {
                "as_of": bridge["as_of"].to_numpy(),
                "anchor_close": bridge["anchor_close"].to_numpy(),
                "target_forward_return": np.nan,
                "target_label": np.nan,
                "score": scored["score"].to_numpy(),
                "reference_source": "FROZEN_MODEL_PRE_FORWARD_BRIDGE",
            }
        )

    reference = pd.concat([oof_ref, bridge_ref], ignore_index=True)
    reference = (
        reference.sort_values("as_of")
        .drop_duplicates("as_of", keep="last")
        .reset_index(drop=True)
    )
    if reference.empty:
        raise RuntimeError("US hurdle policy reference is empty")
    if pd.Timestamp(reference["as_of"].max()) >= forward_start:
        raise RuntimeError("US hurdle reference crosses forward boundary")
    return reference, {
        "oof_reference_rows": int(len(oof_ref)),
        "bridge_rows": int(len(bridge_ref)),
        "bridge_dates": [
            pd.Timestamp(v).isoformat()
            for v in bridge_ref.get(
                "as_of", pd.Series(dtype="datetime64[ns]")
            ).tolist()
        ],
        "reference_rows": int(len(reference)),
        "reference_start": pd.Timestamp(reference["as_of"].min()).isoformat(),
        "reference_end": pd.Timestamp(reference["as_of"].max()).isoformat(),
        "forward_rows_in_reference": 0,
        "bridge_outcomes_used": False,
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

    horizon = int(model_spec["markets"]["US"]["horizon_observations"])
    if int(evaluation_spec["markets"]["US"]["horizon_observations"]) != horizon:
        raise RuntimeError("model/evaluation US horizon mismatch")

    model_path = output_dir / "model.json"
    reference_path = output_dir / "policy_reference_scores.parquet"
    selection_path = output_dir / "pre_forward_selection.json"
    reference_audit_path = output_dir / "reference_audit.json"
    oof_path = output_dir / "selected_oof_scores.parquet"

    freeze_created = False
    if model_path.exists():
        artifact = json.loads(model_path.read_text(encoding="utf-8"))
        if artifact.get("artifact_schema") != ARTIFACT_SCHEMA:
            raise RuntimeError("existing US artifact schema mismatch")
        if artifact.get("model_version") != model_spec["version"]:
            raise RuntimeError("existing US model version mismatch")
        if artifact.get("frozen") is not True:
            raise RuntimeError("existing US artifact is not frozen")
        for required in [reference_path, selection_path, reference_audit_path]:
            if not required.exists():
                raise RuntimeError(f"missing frozen US file: {required}")
        selection_audit = json.loads(
            selection_path.read_text(encoding="utf-8")
        )
        reference_audit = json.loads(
            reference_audit_path.read_text(encoding="utf-8")
        )
        mode = "TRACK_EXISTING_FROZEN_MODEL"
    else:
        safe_train, boundary_audit = safe_pre_forward(
            matrix,
            forward_start=forward_start,
            horizon=horizon,
        )
        hp, policy, selection_audit, selected_oof, target = (
            select_us_candidate(
                safe_train,
                model_spec=model_spec,
                evaluation_spec=evaluation_spec,
                horizon=horizon,
            )
        )
        selection_audit["training_boundary"] = boundary_audit
        atomic_json(selection_path, selection_audit)

        if (
            hp is None
            or policy is None
            or selected_oof is None
            or target is None
        ):
            report = {
                "schema_version": "kalman-v3-003-us-hurdle-report-v1",
                "status": "NO_STABLE_JOINT_GATE_CANDIDATE",
                "mode": "PRE_FORWARD_OOF_TARGET_AUDIT_ONLY",
                "freeze_created": False,
                "model_version": model_spec["version"],
                "strategy_version": model_spec["markets"]["US"][
                    "strategy_version"
                ],
                "forward_start": forward_start.isoformat(),
                "pre_forward_gate_pass": False,
                "promotion_eligible": False,
                "selection_audit": selection_audit,
                "research_only": True,
                "shadow_only": True,
                "production_write": False,
                "neon_write": False,
                "trade_execution": False,
                "evaluated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            }
            atomic_json(output_dir / "latest.json", report)
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
            return 0

        target_hurdle = float(target["target_hurdle"])
        atomic_parquet(selected_oof, oof_path)
        artifact = freeze_us_model(
            safe_train,
            target_hurdle=target_hurdle,
            hyperparameters=hp,
            policy=policy,
            model_spec=model_spec,
            matrix_manifest=matrix_manifest,
            training_audit=boundary_audit,
            selection_audit=selection_audit,
        )
        model_sha = atomic_json(model_path, artifact)
        selection_audit["frozen_model_sha256"] = model_sha
        atomic_json(selection_path, selection_audit)

        reference, reference_audit = build_reference_with_bridge(
            selected_oof=selected_oof,
            matrix=matrix,
            artifact=artifact,
            forward_start=forward_start,
            safe_train_end=pd.Timestamp(safe_train["as_of"].max()),
        )
        atomic_parquet(reference, reference_path)
        atomic_json(reference_audit_path, reference_audit)
        freeze_created = True
        mode = "FREEZE_NEW_US_HURDLE_MODEL"

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
        raise RuntimeError("US frozen reference contains forward rows")

    forward_scores, ledger_audit = update_forward_ledgers(
        matrix,
        artifact,
        forward_start=forward_start,
        score_ledger_path=output_dir / "forward_score_ledger.parquet",
        outcome_ledger_path=output_dir / "forward_outcome_ledger.parquet",
    )
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
    signal = current_shadow_signal(
        combined,
        policy=policy,
        forward_start=forward_start,
    )

    report = {
        "schema_version": "kalman-v3-003-us-hurdle-report-v1",
        "status": "READY",
        "mode": mode,
        "freeze_created": freeze_created,
        "model_version": artifact["model_version"],
        "strategy_version": artifact["strategy_version"],
        "artifact_schema": artifact["artifact_schema"],
        "target_design": artifact["target_design"],
        "target_hurdle": artifact["target_hurdle"],
        "score_semantics": artifact["score_semantics"],
        "model_sha256": sha256_file(model_path),
        "frozen_reference_sha256": sha256_file(reference_path),
        "forward_start": forward_start.isoformat(),
        "pre_forward_gate_pass": pre_forward_pass,
        "pre_forward_selection": artifact["pre_forward_selection"],
        "locked_policy": policy.to_dict(),
        "reference_audit": reference_audit,
        "forward_gate": forward_gate,
        "promotion_eligible": bool(
            pre_forward_pass and forward_gate["promotion_eligible"]
        ),
        "current_shadow_signal": signal,
        "matrix_as_of": pd.Timestamp(matrix["as_of"].max()).isoformat(),
        "forward_score_rows": int(len(forward_scores)),
        "forward_ledgers": ledger_audit,
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
