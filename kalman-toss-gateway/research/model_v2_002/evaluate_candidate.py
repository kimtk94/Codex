from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from research.model_v2.model_contract import score_frame as score_frame_v2001
from research.model_v2_002.model_contract import score_frame as score_frame_v2002, score_row
from research.model_v2_002.train_candidates import metrics


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate isolated Kalman V2.002 candidate")
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--model-dir", required=True)
    p.add_argument("--baseline-model-dir", required=True)
    p.add_argument("--baseline-matrix-dir", required=True)
    p.add_argument("--output-file", required=True)
    p.add_argument("--max-missing-feature-ratio", type=float, default=0.15)
    return p.parse_args()


def _test_slice(matrix: pd.DataFrame, artifact: dict[str, Any]) -> pd.DataFrame:
    x = matrix.copy()
    x["as_of"] = pd.to_datetime(x["as_of"], errors="raise")
    window = artifact.get("training_window") or {}
    start = pd.Timestamp(window["test_start"])
    end = pd.Timestamp(window["test_end"])
    mask = (
        (x["as_of"] >= start)
        & (x["as_of"] <= end)
        & x["target_label"].notna()
    )
    return x.loc[mask].sort_values("as_of").reset_index(drop=True)


def common_window_metrics(
    baseline_matrix: pd.DataFrame,
    baseline_artifact: dict[str, Any],
    candidate_matrix: pd.DataFrame,
    candidate_artifact: dict[str, Any],
) -> dict[str, Any]:
    old_test = _test_slice(baseline_matrix, baseline_artifact)
    new_test = _test_slice(candidate_matrix, candidate_artifact)

    old_scores = score_frame_v2001(old_test, baseline_artifact)
    new_scores = score_frame_v2002(new_test, candidate_artifact)

    old = old_test[["as_of", "target_label", "target_forward_return"]].copy()
    old["probability_up"] = old_scores["probability_up"].to_numpy()
    old = old.rename(
        columns={
            "target_label": "old_target_label",
            "target_forward_return": "old_target_forward_return",
            "probability_up": "old_probability_up",
        }
    )

    new = new_test[["as_of", "target_label", "target_forward_return"]].copy()
    new["probability_up"] = new_scores["probability_up"].to_numpy()
    new = new.rename(
        columns={
            "target_label": "new_target_label",
            "target_forward_return": "new_target_forward_return",
            "probability_up": "new_probability_up",
        }
    )

    aligned = old.merge(new, on="as_of", how="inner", validate="one_to_one")
    if aligned.empty:
        raise RuntimeError("no common untouched test dates between V2.001 and V2.002")

    label_mismatch = int(
        (
            pd.to_numeric(aligned["old_target_label"], errors="coerce")
            != pd.to_numeric(aligned["new_target_label"], errors="coerce")
        ).sum()
    )
    if label_mismatch:
        raise RuntimeError(
            f"target label mismatch on {label_mismatch} common test rows"
        )

    old_metrics = metrics(
        aligned["old_target_label"],
        aligned["old_probability_up"].to_numpy(),
        float(baseline_artifact["probability_threshold"]),
        aligned["old_target_forward_return"],
    )
    new_metrics = metrics(
        aligned["new_target_label"],
        aligned["new_probability_up"].to_numpy(),
        float(candidate_artifact["probability_threshold"]),
        aligned["new_target_forward_return"],
    )
    return {
        "rows": int(len(aligned)),
        "first_as_of": pd.Timestamp(aligned["as_of"].min()).isoformat(),
        "last_as_of": pd.Timestamp(aligned["as_of"].max()).isoformat(),
        "v2001": old_metrics,
        "v2002": new_metrics,
    }


def baseline_skills(metrics: dict[str, Any]) -> dict[str, float | None]:
    try:
        positive_rate = float(metrics["positive_rate"])
        brier = float(metrics["brier"])
        ll = float(metrics["log_loss"])
    except Exception:
        return {"brier_skill": None, "log_loss_skill": None}

    baseline_brier = positive_rate * (1.0 - positive_rate)
    baseline_ll = (
        -(positive_rate * math.log(positive_rate) + (1.0 - positive_rate) * math.log(1.0 - positive_rate))
        if 0.0 < positive_rate < 1.0
        else 0.0
    )
    return {
        "brier_skill": 1.0 - brier / baseline_brier if baseline_brier > 0 else None,
        "log_loss_skill": 1.0 - ll / baseline_ll if baseline_ll > 0 else None,
    }


def gt(a: Any, b: Any) -> bool:
    try:
        return float(a) > float(b)
    except Exception:
        return False


def ge(a: Any, b: Any) -> bool:
    try:
        return float(a) >= float(b)
    except Exception:
        return False


def main() -> int:
    args = parse_args()
    matrix_dir = Path(args.matrix_dir)
    model_dir = Path(args.model_dir)
    baseline_dir = Path(args.baseline_model_dir)
    baseline_matrix_dir = Path(args.baseline_matrix_dir)
    output_file = Path(args.output_file)

    report: dict[str, Any] = {
        "schema_version": "kalman-v2-002-candidate-evaluation-v1",
        "status": "READY",
        "research_only": True,
        "production_write": False,
        "neon_write": False,
        "trade_execution": False,
        "diagnostic_only_after_test_review": True,
        "promotion_allowed_from_this_report": False,
        "markets": {},
    }

    for market in ("US", "KR", "BTC"):
        key = market.lower()
        artifact = json.loads((model_dir / key / "model.json").read_text(encoding="utf-8"))
        baseline = json.loads((baseline_dir / key / "model.json").read_text(encoding="utf-8"))
        matrix = pd.read_parquet(matrix_dir / f"{key}_matrix.parquet")
        matrix["as_of"] = pd.to_datetime(matrix["as_of"], errors="raise")
        baseline_matrix = pd.read_parquet(
            baseline_matrix_dir / f"{key}_matrix.parquet"
        )
        baseline_matrix["as_of"] = pd.to_datetime(
            baseline_matrix["as_of"], errors="raise"
        )

        latest = matrix.sort_values("as_of").iloc[-1]
        latest_score = score_row(latest, artifact)

        new_metrics = artifact["test_metrics"]
        raw_new_metrics = artifact["raw_test_metrics"]
        old_metrics = baseline["test_metrics"]
        old_skill = baseline_skills(old_metrics)
        common = common_window_metrics(
            baseline_matrix,
            baseline,
            matrix,
            artifact,
        )
        common_old = common["v2001"]
        common_new = common["v2002"]

        checks = {
            "candidate_quality_gate_pass": artifact.get("quality_gate_pass") is True,
            "common_window_brier_skill_improved_vs_v2001": gt(
                common_new.get("brier_skill"),
                common_old.get("brier_skill"),
            ),
            "common_window_log_loss_skill_improved_vs_v2001": gt(
                common_new.get("log_loss_skill"),
                common_old.get("log_loss_skill"),
            ),
            "common_window_roc_auc_not_worse_vs_v2001": ge(
                common_new.get("roc_auc"),
                common_old.get("roc_auc"),
            ),
            "latest_feature_missing_ratio_ok": (
                float(latest_score["missing_feature_ratio"])
                <= float(args.max_missing_feature_ratio)
            ),
        }
        hypothetical_promotion_eligible = all(checks.values())
        promotion_eligible = False

        report["markets"][market] = {
            "status": "READY",
            "promotion_eligible": promotion_eligible,
            "hypothetical_promotion_eligible": hypothetical_promotion_eligible,
            "promotion_checks": checks,
            "promotion_block_reason": "TEST_REVIEWED_BEFORE_METHODOLOGY_CHANGE",
            "selected_feature_count": len(artifact["selected_features"]),
            "hyperparameters": artifact["hyperparameters"],
            "calibration": artifact["probability_calibration"],
            "v2001_test_metrics": {
                **old_metrics,
                **old_skill,
            },
            "v2002_raw_test_metrics": raw_new_metrics,
            "v2002_calibrated_test_metrics": new_metrics,
            "common_untouched_test_window": common,
            "latest": {
                "as_of": pd.Timestamp(latest["as_of"]).isoformat(),
                "raw_probability_up": latest_score["raw_probability_up"],
                "calibrated_probability_up": latest_score["probability_up"],
                "probability_threshold": latest_score["probability_threshold"],
                "missing_feature_ratio": latest_score["missing_feature_ratio"],
                "candidate_direction": (
                    "BUY"
                    if promotion_eligible and latest_score["shadow_entry"]
                    else "WATCH"
                ),
            },
        }

    report["all_markets_promotion_eligible"] = False
    report["all_markets_hypothetical_promotion_eligible"] = all(
        row["hypothetical_promotion_eligible"]
        for row in report["markets"].values()
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
