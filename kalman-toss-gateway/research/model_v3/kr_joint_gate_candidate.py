from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.model_v3.evaluation import LockedQuantilePolicy, evaluate_forward_gate
from research.model_v3.kr_candidate import (
    atomic_json,
    atomic_parquet,
    candidate_id,
    current_shadow_signal,
    expanding_walk_forward_oof,
    freeze_model,
    probability_metrics,
    safe_pre_forward,
    sha256_file,
    update_forward_ledgers,
)
from research.model_v3.evaluation import evaluate_policy
from research.model_v3.model_contract import ARTIFACT_SCHEMA, score_frame


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Freeze or track Kalman V3.004 KR joint-gate candidate"
    )
    p.add_argument("--matrix", required=True)
    p.add_argument("--matrix-manifest", required=True)
    p.add_argument("--model-spec", required=True)
    p.add_argument("--evaluation-spec", required=True)
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def fixed_selection(
    oof_by_candidate: dict[str, pd.DataFrame],
    *,
    model_spec: dict[str, Any],
    evaluation_spec: dict[str, Any],
    horizon: int,
) -> tuple[dict[str, Any], LockedQuantilePolicy, dict[str, Any], pd.DataFrame]:
    fixed = model_spec["fixed_joint_gate_policy"]
    hp = {
        "feature_count": int(fixed["feature_count"]),
        "C": float(fixed["C"]),
        "class_weight": fixed.get("class_weight"),
    }
    expected_id = str(fixed["candidate_id"])
    actual_id = candidate_id(hp)
    if actual_id != expected_id:
        raise RuntimeError(
            f"fixed candidate id mismatch expected={expected_id} actual={actual_id}"
        )
    if expected_id not in oof_by_candidate:
        raise RuntimeError(f"fixed candidate OOF missing: {expected_id}")

    oof = oof_by_candidate[expected_id].copy()
    pm = probability_metrics(oof)
    rolling = evaluation_spec["rolling_score_policy"]
    costs = evaluation_spec["costs"]
    strategy = evaluate_policy(
        oof,
        top_fraction=float(fixed["top_fraction"]),
        lookback_observations=int(rolling["lookback_observations"]),
        minimum_history_observations=int(
            rolling["minimum_history_observations"]
        ),
        horizon_observations=horizon,
        round_trip_cost_bps=float(costs["round_trip_cost_bps"]),
    )

    min_oof = int(model_spec["walk_forward"]["minimum_oof_rows"])
    min_entries = int(fixed["expected_minimum_nonoverlap_entries"])
    net_stats = strategy["nonoverlap_selected_net"]
    checks = {
        "minimum_oof_rows": int(pm["rows"]) >= min_oof,
        "minimum_nonoverlap_entries": (
            int(strategy["nonoverlap_selected_rows"]) >= min_entries
        ),
        "positive_incremental_alpha_net": (
            strategy["nonoverlap_incremental_alpha_mean_net"] is not None
            and float(strategy["nonoverlap_incremental_alpha_mean_net"]) > 0.0
        ),
        "positive_win_rate_lift": (
            strategy["nonoverlap_win_rate_lift"] is not None
            and float(strategy["nonoverlap_win_rate_lift"]) > 0.0
        ),
        "positive_net_mean": (
            net_stats["mean"] is not None and float(net_stats["mean"]) > 0.0
        ),
        "positive_net_compounded_return": (
            net_stats["compounded_return"] is not None
            and float(net_stats["compounded_return"]) > 0.0
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(
            "fixed V3.004 KR candidate no longer satisfies joint gate: "
            + json.dumps(checks, sort_keys=True)
        )

    selection_end = pd.Timestamp(oof["as_of"].max()).isoformat()
    policy = LockedQuantilePolicy(
        top_fraction=float(fixed["top_fraction"]),
        lookback_observations=int(rolling["lookback_observations"]),
        minimum_history_observations=int(
            rolling["minimum_history_observations"]
        ),
        selection_end=selection_end,
        source="V3_003_OOF_AUDIT_FIXED_BEFORE_FORWARD_OBSERVATION",
    )
    audit = {
        "status": "LOCKED",
        "methodology_status": model_spec["methodology_status"],
        "selection_source": fixed["selection_origin"],
        "forward_rows_used_for_selection": 0,
        "selected_candidate_id": expected_id,
        "selected_hyperparameters": hp,
        "selected_policy": policy.to_dict(),
        "selected_oof_probability_metrics": pm,
        "selected_oof_strategy_metrics": strategy,
        "pre_forward_gate_checks": checks,
        "pre_forward_gate_pass": all(checks.values()),
        "grid_retuning_after_v3_003_audit": False,
        "fixed_candidate_research_only": True,
    }
    return hp, policy, audit, oof


def build_reference_with_bridge(
    *,
    selected_oof: pd.DataFrame,
    matrix: pd.DataFrame,
    artifact: dict[str, Any],
    forward_start: pd.Timestamp,
    safe_train_end: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    oof_reference = selected_oof[
        [
            "as_of",
            "anchor_close",
            "target_forward_return",
            "target_label",
            "score",
        ]
    ].copy()
    oof_reference["reference_source"] = "EXPANDING_WALK_FORWARD_OOF"

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
        bridge_reference = pd.DataFrame(
            columns=oof_reference.columns
        )
    else:
        bridge_scores = score_frame(bridge, artifact)
        bridge_reference = pd.DataFrame(
            {
                "as_of": bridge["as_of"].to_numpy(),
                "anchor_close": bridge["anchor_close"].to_numpy(),
                # Outcomes are deliberately blank. These rows are used only
                # to update the pre-forward score distribution.
                "target_forward_return": np.nan,
                "target_label": np.nan,
                "score": bridge_scores["score"].to_numpy(),
                "reference_source": "FROZEN_MODEL_PRE_FORWARD_BRIDGE",
            }
        )

    reference = pd.concat(
        [oof_reference, bridge_reference],
        ignore_index=True,
    )
    reference = (
        reference.sort_values("as_of")
        .drop_duplicates("as_of", keep="last")
        .reset_index(drop=True)
    )
    if reference.empty:
        raise RuntimeError("V3.004 policy reference is empty")
    if pd.Timestamp(reference["as_of"].max()) >= forward_start:
        raise RuntimeError("V3.004 reference crosses forward boundary")

    audit = {
        "oof_reference_rows": int(len(oof_reference)),
        "bridge_rows": int(len(bridge_reference)),
        "bridge_dates": [
            pd.Timestamp(v).isoformat()
            for v in bridge_reference.get(
                "as_of", pd.Series(dtype="datetime64[ns]")
            ).tolist()
        ],
        "reference_rows": int(len(reference)),
        "reference_start": pd.Timestamp(
            reference["as_of"].min()
        ).isoformat(),
        "reference_end": pd.Timestamp(
            reference["as_of"].max()
        ).isoformat(),
        "forward_rows_in_reference": 0,
        "bridge_outcomes_used": False,
    }
    return reference, audit


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
    if model_spec.get("forward_data_used_for_model_selection") is not False:
        raise RuntimeError("V3.004 must declare zero forward selection usage")

    market_spec = model_spec["markets"]["KR"]
    horizon = int(market_spec["horizon_observations"])
    if int(evaluation_spec["markets"]["KR"]["horizon_observations"]) != horizon:
        raise RuntimeError("model/evaluation KR horizon mismatch")

    model_path = output_dir / "model.json"
    reference_path = output_dir / "policy_reference_scores.parquet"
    selection_path = output_dir / "pre_forward_selection.json"
    oof_path = output_dir / "selected_oof_scores.parquet"
    reference_audit_path = output_dir / "reference_audit.json"

    freeze_created = False
    if model_path.exists():
        artifact = json.loads(model_path.read_text(encoding="utf-8"))
        if artifact.get("artifact_schema") != ARTIFACT_SCHEMA:
            raise RuntimeError("existing V3.004 artifact schema mismatch")
        if artifact.get("model_version") != model_spec["version"]:
            raise RuntimeError("existing V3.004 model version mismatch")
        if artifact.get("frozen") is not True:
            raise RuntimeError("existing V3.004 artifact is not frozen")
        for required in [reference_path, selection_path, reference_audit_path]:
            if not required.exists():
                raise RuntimeError(f"missing frozen V3.004 file: {required}")
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
        oof_by_candidate, wf_audit = expanding_walk_forward_oof(
            safe_train,
            spec=model_spec,
            horizon=horizon,
        )
        hp, policy, selection_audit, selected_oof = fixed_selection(
            oof_by_candidate,
            model_spec=model_spec,
            evaluation_spec=evaluation_spec,
            horizon=horizon,
        )
        selection_audit["walk_forward"] = wf_audit
        selection_audit["training_boundary"] = boundary_audit
        atomic_parquet(selected_oof, oof_path)

        artifact = freeze_model(
            safe_train,
            hyperparameters=hp,
            policy=policy,
            model_spec=model_spec,
            matrix_manifest=matrix_manifest,
            training_audit=boundary_audit,
            selection_audit=selection_audit,
        )
        artifact["methodology_status"] = model_spec["methodology_status"]
        artifact["forward_data_used_for_model_selection"] = False
        artifact["v3_003_audit_derived_fixed_candidate"] = True
        artifact["reselection_after_freeze_allowed"] = False

        model_sha = atomic_json(model_path, artifact)
        selection_audit["frozen_model_sha256"] = model_sha
        atomic_json(selection_path, selection_audit)

        reference, reference_audit = build_reference_with_bridge(
            selected_oof=selected_oof,
            matrix=matrix,
            artifact=artifact,
            forward_start=forward_start,
            safe_train_end=pd.Timestamp(
                safe_train["as_of"].max()
            ),
        )
        atomic_parquet(reference, reference_path)
        atomic_json(reference_audit_path, reference_audit)
        freeze_created = True
        mode = "FREEZE_NEW_V3_004_MODEL"

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
        raise RuntimeError("V3.004 frozen reference contains forward rows")

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
    promotion_eligible = bool(
        pre_forward_pass and forward_gate["promotion_eligible"]
    )
    signal = current_shadow_signal(
        combined,
        policy=policy,
        forward_start=forward_start,
    )

    report = {
        "schema_version": "kalman-v3-004-kr-forward-report-v1",
        "status": "READY",
        "mode": mode,
        "freeze_created": freeze_created,
        "model_version": artifact["model_version"],
        "strategy_version": artifact["strategy_version"],
        "artifact_schema": artifact["artifact_schema"],
        "methodology_status": artifact["methodology_status"],
        "model_sha256": sha256_file(model_path),
        "frozen_reference_sha256": sha256_file(reference_path),
        "forward_start": forward_start.isoformat(),
        "forward_data_used_for_model_selection": False,
        "pre_forward_gate_pass": pre_forward_pass,
        "pre_forward_selection": artifact["pre_forward_selection"],
        "locked_policy": policy.to_dict(),
        "reference_audit": reference_audit,
        "forward_gate": forward_gate,
        "promotion_eligible": promotion_eligible,
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
