from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.quant_stack.qlib_recorder import qlib_available, record_market_experiment


def test_qlib_recorder_roundtrip(tmp_path):
    assert qlib_available()

    result = record_market_experiment(
        experiment_name="kalman_qlib_smoke",
        tracking_root=tmp_path / "mlruns",
        provider_root=tmp_path / "provider",
        params={
            "market": "US",
            "mode": "BACKTEST",
            "model_version": "test_model",
        },
        metrics={
            "sharpe": 1.25,
            "total_return": 0.12,
            "trade_count": 7,
        },
        artifact_manifest={
            "market": "US",
            "source": "synthetic_smoke",
            "live_execution": False,
        },
    )

    assert result["status"] == "RECORDED"
    assert result["backend"] == "QLIB_RECORDER_MLFLOW"
    assert result["recorder_id"]
    assert (tmp_path / "mlruns").exists()
