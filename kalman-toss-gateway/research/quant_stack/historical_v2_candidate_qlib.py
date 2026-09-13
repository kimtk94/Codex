from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .qlib_recorder import record_market_experiment


MARKETS = ("US", "KR", "BTC")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def run(
    output_root: Path,
    *,
    tracking_root: Path,
    provider_root: Path,
    experiment_name: str,
) -> dict[str, Any]:
    recorded: dict[str, Any] = {}
    for market in MARKETS:
        summary_path = output_root / market.lower() / "candidate_summary.json"
        if not summary_path.exists():
            continue
        summary = _load_json(summary_path)
        metrics = summary.get("backtests", {}).get("100pct", {}).get("strategy", {})
        recorded[market] = record_market_experiment(
            experiment_name=experiment_name,
            tracking_root=tracking_root,
            provider_root=provider_root,
            params={
                "market": market,
                "model_version": summary.get("model_version", ""),
                "feature_version": summary.get("feature_version", ""),
                "git_sha": summary.get("git_sha", ""),
                "nested_walk_forward": True,
                "maximum_features": 32,
                "research_only": True,
            },
            metrics=metrics,
            artifact_manifest={
                "market": market,
                "output_dir": str(output_root / market.lower()),
                "candidate_summary": str(summary_path),
                "fold_metrics": str(output_root / market.lower() / "fold_metrics.json"),
                "strategy_signal": str(output_root / market.lower() / "historical_strategy_signal.parquet"),
                "model_output": str(output_root / market.lower() / "historical_model_output.parquet"),
                "research_only": True,
                "live_execution": False,
                "toss_execution": False,
                "neon_write": False,
            },
        )

    payload = {
        "status": "READY" if recorded else "SKIPPED",
        "python_requirement": "3.12",
        "experiment_name": experiment_name,
        "markets": recorded,
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _write_json(output_root / "qlib_recording.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return payload


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Qlib recorder for Historical V2 candidate")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--tracking-root", required=True)
    p.add_argument("--provider-root", required=True)
    p.add_argument("--experiment-name", default="kalman_historical_v2_nested_candidate")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    run(
        Path(args.output_dir).expanduser(),
        tracking_root=Path(args.tracking_root).expanduser(),
        provider_root=Path(args.provider_root).expanduser(),
        experiment_name=args.experiment_name,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
