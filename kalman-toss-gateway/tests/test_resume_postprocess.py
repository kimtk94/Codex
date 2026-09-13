from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import research.quant_stack.resume_postprocess as resume_mod
from research.quant_stack.resume_postprocess import (
    REQUIRED_MARKET_ARTIFACTS,
    assert_market_artifacts_unchanged,
    market_artifact_fingerprint,
    preflight_resume,
    ready_markets_from_status,
    validate_reusable_market_artifacts,
    validate_status_safety_invariants,
)


def _write_market(root: Path, market: str) -> None:
    market_dir = root / market.lower()
    market_dir.mkdir(parents=True)

    pd.DataFrame(
        {
            "as_of": pd.to_datetime(["2020-01-01"], utc=True),
            "probability": [0.6],
        }
    ).to_parquet(market_dir / "historical_model_output.parquet", index=False)

    pd.DataFrame(
        {
            "signal_ts": pd.to_datetime(["2020-01-01"], utc=True),
            "signal": ["BUY"],
        }
    ).to_parquet(market_dir / "historical_strategy_signal.parquet", index=False)

    pd.DataFrame(
        {
            "entry_ts": pd.to_datetime(["2020-01-01"], utc=True),
            "exit_ts": pd.to_datetime(["2020-01-02"], utc=True),
        }
    ).to_parquet(market_dir / "historical_trades.parquet", index=False)

    pd.DataFrame(
        {
            "ts": pd.to_datetime(["2020-01-01", "2020-01-02"], utc=True),
            "equity": [1_000_000.0, 1_001_000.0],
        }
    ).to_parquet(market_dir / "historical_equity.parquet", index=False)

    (market_dir / "fold_metrics.json").write_text(
        json.dumps([{"fold": {"test_start": "2020-01-01"}}]),
        encoding="utf-8",
    )
    (market_dir / "experiment.json").write_text(
        json.dumps({"mode": "BACKTEST"}),
        encoding="utf-8",
    )
    (market_dir / "historical_performance.json").write_text(
        json.dumps({"total_return": 0.001}),
        encoding="utf-8",
    )
    (market_dir / "run_summary.json").write_text(
        json.dumps({"price_source": "RAW_ANCHOR_OHLC"}),
        encoding="utf-8",
    )


def _write_status(root: Path, *, live_execution: bool = False) -> dict:
    payload = {
        "status": "FAIL",
        "research_only": True,
        "live_execution": live_execution,
        "neon_write": False,
        "markets": {
            "US": {"status": "READY"},
            "KR": {"status": "READY"},
            "BTC": {"status": "READY"},
        },
    }
    (root / "historical_experiment_status.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return payload


def test_ready_markets_from_status_preserves_supported_order():
    status = {
        "markets": {
            "BTC": {"status": "READY"},
            "US": {"status": "READY"},
            "KR": {"status": "FAIL"},
        }
    }
    assert ready_markets_from_status(status) == ["US", "BTC"]


def test_validate_reusable_market_artifacts_reads_real_json_and_parquet(tmp_path):
    _write_market(tmp_path, "US")
    _write_market(tmp_path, "KR")
    validate_reusable_market_artifacts(tmp_path, ["US", "KR"])


def test_validate_reusable_market_artifacts_rejects_corrupt_parquet(tmp_path):
    _write_market(tmp_path, "US")
    _write_market(tmp_path, "KR")
    (tmp_path / "kr" / "historical_equity.parquet").write_bytes(b"not-parquet")

    with pytest.raises(Exception):
        validate_reusable_market_artifacts(tmp_path, ["US", "KR"])


def test_validate_reusable_market_artifacts_rejects_missing_file(tmp_path):
    _write_market(tmp_path, "US")
    _write_market(tmp_path, "KR")
    (tmp_path / "kr" / "historical_equity.parquet").unlink()

    with pytest.raises(FileNotFoundError, match="KR/historical_equity.parquet"):
        validate_reusable_market_artifacts(tmp_path, ["US", "KR"])


def test_validate_reusable_market_artifacts_requires_two_markets(tmp_path):
    _write_market(tmp_path, "US")
    with pytest.raises(RuntimeError, match="at least two READY"):
        validate_reusable_market_artifacts(tmp_path, ["US"])


def test_validate_status_safety_invariants_rejects_live():
    with pytest.raises(RuntimeError, match="live_execution=false"):
        validate_status_safety_invariants(
            {
                "research_only": True,
                "live_execution": True,
                "neon_write": False,
            }
        )


def test_preflight_resume_hashes_immutable_artifacts(tmp_path):
    _write_status(tmp_path)
    for market in ("US", "KR", "BTC"):
        _write_market(tmp_path, market)

    report = preflight_resume(tmp_path)

    assert report["status"] == "READY"
    assert report["immutable_artifact_count"] == 24
    assert (tmp_path / "resume_preflight_report.json").exists()


def test_immutable_fingerprint_detects_market_mutation(tmp_path):
    for market in ("US", "KR"):
        _write_market(tmp_path, market)
    baseline = market_artifact_fingerprint(tmp_path, ["US", "KR"])

    (tmp_path / "us" / "historical_performance.json").write_text(
        json.dumps({"total_return": 999}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="modified immutable"):
        assert_market_artifacts_unchanged(
            tmp_path,
            ["US", "KR"],
            baseline,
        )


def test_failed_resume_restores_original_status(tmp_path, monkeypatch):
    original = _write_status(tmp_path)
    for market in ("US", "KR", "BTC"):
        _write_market(tmp_path, market)

    def fail_portfolio(*args, **kwargs):
        raise RuntimeError("synthetic portfolio failure")

    monkeypatch.setattr(resume_mod, "run_portfolio_target_layer", fail_portfolio)

    with pytest.raises(RuntimeError, match="synthetic portfolio failure"):
        resume_mod.resume_postprocess(tmp_path)

    restored = json.loads(
        (tmp_path / "historical_experiment_status.json").read_text(encoding="utf-8")
    )
    assert restored == original
