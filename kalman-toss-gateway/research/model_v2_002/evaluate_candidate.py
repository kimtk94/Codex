from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from research.model_v2_002.model_contract import score_row


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate isolated Kalman V2.002 candidate")
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--model-dir", required=True)
    p.add_argument("--baseline-model-dir", required=True)
    p.add_argument("--output-file", required=True)
    p.add_argument("--max-missing-feature-ratio", type=float, default=0.15)
    return p.parse_args()


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
    output_file = Path(args.output_file)

    report: dict[str, Any] = {
        "schema_version": "kalman-v2-002-candidate-evaluation-v1",
        "status": "READY",
        "research_only": True,
        "production_write": False,
        "neon_write": False,
        "trade_execution": False,
        "markets": {},
    }

    for market in ("US", "KR", "BTC"):
        key = market.lower()
        artifact = json.loads((model_dir / key / "model.json").read_text(encoding="utf-8"))
        baseline = json.loads((baseline_dir / key / "model.json").read_text(encoding="utf-8"))
        matrix = pd.read_parquet(matrix_dir / f"{key}_matrix.parquet")
        matrix["as_of"] = pd.to_datetime(matrix["as_of"], errors="raise")
        latest = matrix.sort_values("as_of").iloc[-1]
        latest_score = score_row(latest, artifact)

        new_metrics = artifact["test_metrics"]
        raw_new_metrics = artifact["raw_test_metrics"]
        old_metrics = baseline["test_metrics"]
        old_skill = baseline_skills(old_metrics)

        checks = {
            "candidate_quality_gate_pass": artifact.get("quality_gate_pass") is True,
            "brier_skill_improved_vs_v2001": gt(
                new_metrics.get("brier_skill"),
                old_skill.get("brier_skill"),
            ),
            "log_loss_skill_improved_vs_v2001": gt(
                new_metrics.get("log_loss_skill"),
                old_skill.get("log_loss_skill"),
            ),
            "roc_auc_not_worse_vs_v2001": ge(
                new_metrics.get("roc_auc"),
                old_metrics.get("roc_auc"),
            ),
            "latest_feature_missing_ratio_ok": (
                float(latest_score["missing_feature_ratio"])
                <= float(args.max_missing_feature_ratio)
            ),
        }
        promotion_eligible = all(checks.values())

        report["markets"][market] = {
            "status": "READY",
            "promotion_eligible": promotion_eligible,
            "promotion_checks": checks,
            "selected_feature_count": len(artifact["selected_features"]),
            "hyperparameters": artifact["hyperparameters"],
            "calibration": artifact["probability_calibration"],
            "v2001_test_metrics": {
                **old_metrics,
                **old_skill,
            },
            "v2002_raw_test_metrics": raw_new_metrics,
            "v2002_calibrated_test_metrics": new_metrics,
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

    report["all_markets_promotion_eligible"] = all(
        row["promotion_eligible"] for row in report["markets"].values()
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
