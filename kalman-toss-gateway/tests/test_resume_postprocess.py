from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.quant_stack.resume_postprocess import (
    REQUIRED_MARKET_ARTIFACTS,
    ready_markets_from_status,
    validate_reusable_market_artifacts,
)


def _make_market(root: Path, market: str) -> None:
    market_dir = root / market.lower()
    market_dir.mkdir(parents=True)
    for name in REQUIRED_MARKET_ARTIFACTS:
        (market_dir / name).write_bytes(b"x")


def test_ready_markets_from_status_preserves_supported_order():
    status = {
        "markets": {
            "BTC": {"status": "READY"},
            "US": {"status": "READY"},
            "KR": {"status": "FAIL"},
        }
    }
    assert ready_markets_from_status(status) == ["US", "BTC"]


def test_validate_reusable_market_artifacts_accepts_existing_markets(tmp_path):
    _make_market(tmp_path, "US")
    _make_market(tmp_path, "KR")
    validate_reusable_market_artifacts(tmp_path, ["US", "KR"])


def test_validate_reusable_market_artifacts_rejects_missing_file(tmp_path):
    _make_market(tmp_path, "US")
    _make_market(tmp_path, "KR")
    (tmp_path / "kr" / "historical_equity.parquet").unlink()

    with pytest.raises(FileNotFoundError, match="KR/historical_equity.parquet"):
        validate_reusable_market_artifacts(tmp_path, ["US", "KR"])


def test_validate_reusable_market_artifacts_requires_two_markets(tmp_path):
    _make_market(tmp_path, "US")
    with pytest.raises(RuntimeError, match="at least two READY"):
        validate_reusable_market_artifacts(tmp_path, ["US"])
