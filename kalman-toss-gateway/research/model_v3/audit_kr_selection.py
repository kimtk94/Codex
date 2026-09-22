from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Audit all frozen KR V3.003 OOF candidate/policy combinations"
    )
    p.add_argument("--selection", required=True)
    p.add_argument("--output", required=False)
    p.add_argument("--top", type=int, default=12)
    return p.parse_args()


def finite(value: Any, default: float | None = None) -> float | None:
    try:
        x = float(value)
    except Exception:
        return default
    return x if math.isfinite(x) else default


def summarize(payload: dict[str, Any], top: int = 12) -> dict[str, Any]:
    rows = list(payload.get("candidate_policy_results") or [])
    if not rows:
        raise RuntimeError("candidate_policy_results missing from selection audit")

    audited: list[dict[str, Any]] = []
    for row in rows:
        strategy = row.get("strategy_metrics") or {}
        probability = row.get("probability_metrics") or {}
        checks = dict(row.get("selection_checks") or {})
        alpha = finite(strategy.get("nonoverlap_incremental_alpha_mean_net"))
        lift = finite(strategy.get("nonoverlap_win_rate_lift"))
        entries = int(strategy.get("nonoverlap_selected_rows") or 0)
        net_mean = finite(
            (strategy.get("nonoverlap_selected_net") or {}).get("mean")
        )
        net_compounded = finite(
            (strategy.get("nonoverlap_selected_net") or {}).get(
                "compounded_return"
            )
        )
        auc = finite(probability.get("roc_auc"))
        brier = finite(probability.get("brier"))
        logloss = finite(probability.get("log_loss"))

        joint_checks = {
            "selection_floor_pass": bool(row.get("selection_eligible")),
            "positive_incremental_alpha_net": (
                alpha is not None and alpha > 0.0
            ),
            "positive_win_rate_lift": (
                lift is not None and lift > 0.0
            ),
            "positive_net_mean": (
                net_mean is not None and net_mean > 0.0
            ),
            "positive_net_compounded_return": (
                net_compounded is not None and net_compounded > 0.0
            ),
        }
        joint_pass = all(joint_checks.values())
        audited.append(
            {
                "candidate_id": row.get("candidate_id"),
                "hyperparameters": row.get("hyperparameters"),
                "top_fraction": row.get("top_fraction"),
                "oof_rows": probability.get("rows"),
                "oof_auc": auc,
                "oof_brier": brier,
                "oof_log_loss": logloss,
                "nonoverlap_entries": entries,
                "incremental_alpha_mean_net": alpha,
                "win_rate_lift": lift,
                "selected_net_mean": net_mean,
                "selected_net_compounded_return": net_compounded,
                "joint_gate_checks": joint_checks,
                "joint_gate_pass": joint_pass,
                "original_selection_checks": checks,
            }
        )

    def rank_key(item: dict[str, Any]) -> tuple[float, float, float, float]:
        return (
            float(item["incremental_alpha_mean_net"])
            if item["incremental_alpha_mean_net"] is not None
            else -999.0,
            float(item["win_rate_lift"])
            if item["win_rate_lift"] is not None
            else -999.0,
            -float(item["top_fraction"] or 1.0),
            float(item["oof_auc"])
            if item["oof_auc"] is not None
            else -999.0,
        )

    joint = sorted(
        [item for item in audited if item["joint_gate_pass"]],
        key=rank_key,
        reverse=True,
    )
    positive_both = sorted(
        [
            item
            for item in audited
            if item["incremental_alpha_mean_net"] is not None
            and item["incremental_alpha_mean_net"] > 0.0
            and item["win_rate_lift"] is not None
            and item["win_rate_lift"] > 0.0
        ],
        key=rank_key,
        reverse=True,
    )
    ranked_all = sorted(audited, key=rank_key, reverse=True)

    selected_id = payload.get("selected_candidate_id")
    selected_fraction = (payload.get("selected_policy") or {}).get(
        "top_fraction"
    )
    selected = next(
        (
            item
            for item in audited
            if item["candidate_id"] == selected_id
            and item["top_fraction"] == selected_fraction
        ),
        None,
    )

    return {
        "schema_version": "kalman-v3-003-kr-selection-audit-v1",
        "status": "READY",
        "candidate_policy_count": len(audited),
        "selected_candidate": selected,
        "joint_gate_passing_count": len(joint),
        "positive_alpha_and_win_lift_count": len(positive_both),
        "joint_gate_passing_top": joint[:top],
        "positive_alpha_and_win_lift_top": positive_both[:top],
        "ranked_all_top": ranked_all[:top],
        "next_action": (
            "V3_004_JOINT_GATE_CANDIDATE_AVAILABLE"
            if joint
            else "REDESIGN_KR_MODEL_FAMILY"
        ),
        "research_only": True,
        "production_write": False,
        "neon_write": False,
        "trade_execution": False,
    }


def main() -> int:
    args = parse_args()
    payload = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    report = summarize(payload, top=max(1, int(args.top)))

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
