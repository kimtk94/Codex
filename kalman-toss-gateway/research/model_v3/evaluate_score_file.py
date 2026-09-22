from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .evaluation import evaluate_forward_gate, select_pre_forward_policy


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Evaluate a frozen Kalman V3 score stream under the locked forward contract"
    )
    p.add_argument("--policy-reference", required=True)
    p.add_argument("--forward-scores", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--market", required=True, choices=["US", "KR", "BTC"])
    p.add_argument("--output", required=True)
    return p.parse_args()


def _read(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    required = {"as_of", "score", "target_forward_return"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path}: missing {sorted(missing)}")
    frame = frame.copy()
    frame["as_of"] = pd.to_datetime(frame["as_of"], errors="raise")
    return frame.sort_values("as_of").reset_index(drop=True)


def main() -> int:
    args = parse_args()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    market_spec: dict[str, Any] = spec["markets"][args.market]
    forward_start = pd.Timestamp(spec["forward_start"])

    reference = _read(Path(args.policy_reference))
    forward = _read(Path(args.forward_scores))

    if reference.empty:
        raise RuntimeError("policy reference is empty")
    if forward.empty:
        raise RuntimeError("forward score file is empty")
    if pd.Timestamp(reference["as_of"].max()) >= forward_start:
        raise RuntimeError("policy reference contains rows on/after forward_start")
    if pd.Timestamp(forward["as_of"].min()) < forward_start:
        raise RuntimeError("forward scores contain pre-forward rows")

    rolling = spec["rolling_score_policy"]
    selection = spec["policy_selection"]
    costs = spec["costs"]
    gate = spec["promotion_gate"]

    policy, policy_audit = select_pre_forward_policy(
        reference,
        top_fractions=market_spec["candidate_top_fractions"],
        forward_start=forward_start,
        lookback_observations=int(rolling["lookback_observations"]),
        minimum_history_observations=int(rolling["minimum_history_observations"]),
        horizon_observations=int(market_spec["horizon_observations"]),
        round_trip_cost_bps=float(costs["round_trip_cost_bps"]),
        minimum_nonoverlap_entries=int(selection["minimum_nonoverlap_entries"]),
    )

    combined = pd.concat([reference, forward], ignore_index=True)
    forward_gate = evaluate_forward_gate(
        combined,
        policy=policy,
        forward_start=forward_start,
        horizon_observations=int(market_spec["horizon_observations"]),
        round_trip_cost_bps=float(costs["round_trip_cost_bps"]),
        gate=gate,
    )

    payload = {
        "schema_version": spec["schema_version"],
        "evaluation_version": spec["version"],
        "market": args.market,
        "market_status": market_spec["status"],
        "objective": market_spec["objective"],
        "research_only": True,
        "production_write": False,
        "neon_write": False,
        "trade_execution": False,
        "forward_start": forward_start.isoformat(),
        "policy_selection": policy_audit,
        "forward_gate": forward_gate,
        "promotion_eligible": bool(forward_gate["promotion_eligible"]),
        "invariants": {
            "policy_reference_precedes_forward_start": True,
            "forward_scores_on_or_after_forward_start": True,
            "current_score_excluded_from_rolling_threshold": bool(
                rolling["current_score_excluded_from_threshold"]
            ),
            "nonoverlap_horizon_enforced": True,
            "research_only": True,
            "trade_execution": False,
        },
        "evaluated_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
