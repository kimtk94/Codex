from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd


MODEL_PATHS = {
    "KR": Path("Market_Model_V3_004_KR_JointGate/frozen/latest.json"),
    "BTC": Path("Market_Model_V3_003_BTC_Tail/frozen/latest.json"),
    "US": Path("Market_Model_V3_003_US_Hurdle/frozen/latest.json"),
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Aggregate frozen Kalman V3 shadow-forward reports"
    )
    p.add_argument("--data-root", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _forward_metrics(report: dict[str, Any]) -> dict[str, Any]:
    gate = report.get("forward_gate") or {}
    net = gate.get("nonoverlap_selected_net") or {}
    return {
        "status": gate.get("status"),
        "observations": int(gate.get("forward_observations") or 0),
        "nonoverlap_entries": int(net.get("rows") or 0),
        "incremental_alpha_mean_net": gate.get(
            "nonoverlap_incremental_alpha_mean_net"
        ),
        "win_rate_lift": gate.get("nonoverlap_win_rate_lift"),
        "net_mean": net.get("mean"),
        "net_win_rate": net.get("win_rate"),
        "net_compounded_return": net.get("compounded_return"),
        "max_drawdown": net.get("max_drawdown"),
        "checks": gate.get("checks") or {},
    }


def normalize_market(
    market: str,
    path: Path,
) -> dict[str, Any]:
    if not path.exists():
        return {
            "market": market,
            "status": "MISSING",
            "path": str(path),
            "safety_pass": False,
            "promotion_eligible": False,
            "current_shadow_entry": False,
        }

    report = _load_json(path)
    signal = report.get("current_shadow_signal") or {}
    selection = report.get("pre_forward_selection") or {}
    oof = selection.get("selected_oof_strategy_metrics") or {}
    oof_net = oof.get("nonoverlap_selected_net") or {}
    safety = {
        "research_only": report.get("research_only") is True,
        "shadow_only": report.get("shadow_only") is True,
        "production_write_false": report.get("production_write") is False,
        "neon_write_false": report.get("neon_write") is False,
        "trade_execution_false": report.get("trade_execution") is False,
        "not_retrained_existing_frozen_model": (
            report.get("retrained_existing_frozen_model") is False
        ),
    }
    safety_pass = all(safety.values())

    return {
        "market": market,
        "status": report.get("status"),
        "mode": report.get("mode"),
        "model_version": report.get("model_version"),
        "strategy_version": report.get("strategy_version"),
        "forward_start": report.get("forward_start"),
        "matrix_as_of": report.get("matrix_as_of"),
        "pre_forward_gate_pass": report.get("pre_forward_gate_pass") is True,
        "promotion_eligible": report.get("promotion_eligible") is True,
        "locked_policy": report.get("locked_policy"),
        "target_hurdle": report.get("target_hurdle"),
        "score_semantics": report.get("score_semantics"),
        "oof": {
            "nonoverlap_entries": int(oof.get("nonoverlap_selected_rows") or 0),
            "incremental_alpha_mean_net": oof.get(
                "nonoverlap_incremental_alpha_mean_net"
            ),
            "win_rate_lift": oof.get("nonoverlap_win_rate_lift"),
            "net_mean": oof_net.get("mean"),
            "net_win_rate": oof_net.get("win_rate"),
            "net_compounded_return": oof_net.get("compounded_return"),
        },
        "forward": _forward_metrics(report),
        "signal": {
            "status": signal.get("status"),
            "as_of": signal.get("as_of"),
            "score": signal.get("score"),
            "score_cutoff": signal.get("score_cutoff"),
            "top_fraction": signal.get("top_fraction"),
            "policy_ready": signal.get("policy_ready"),
            "forward_era": signal.get("forward_era"),
            "shadow_entry": signal.get("shadow_entry") is True,
            "live_execution": signal.get("live_execution") is True,
        },
        "forward_ledgers": report.get("forward_ledgers") or {},
        "safety": safety,
        "safety_pass": safety_pass,
        "path": str(path),
    }


def build_summary(data_root: Path) -> dict[str, Any]:
    markets = {
        market: normalize_market(market, data_root / rel)
        for market, rel in MODEL_PATHS.items()
    }
    all_present = all(v["status"] != "MISSING" for v in markets.values())
    safety_pass = all(v.get("safety_pass") is True for v in markets.values())
    any_entry = any(
        v.get("signal", {}).get("shadow_entry") is True
        for v in markets.values()
    )
    promotions = [
        market
        for market, row in markets.items()
        if row.get("promotion_eligible") is True
    ]
    forward_obs = {
        market: int(row.get("forward", {}).get("observations") or 0)
        for market, row in markets.items()
    }
    return {
        "schema_version": "kalman-v3-shadow-tracker-v1",
        "status": "READY" if all_present and safety_pass else "ATTENTION",
        "all_models_present": all_present,
        "safety_pass": safety_pass,
        "any_shadow_entry": any_entry,
        "promotion_candidate_markets": promotions,
        "forward_observations": forward_obs,
        "markets": markets,
        "production_write": False,
        "neon_write": False,
        "trade_execution": False,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }


def main() -> int:
    args = parse_args()
    data_root = Path(args.data_root).expanduser()
    output = Path(args.output).expanduser()
    summary = build_summary(data_root)

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
