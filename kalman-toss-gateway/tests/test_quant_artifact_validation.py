from __future__ import annotations

import json
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.quant_stack.validate_artifacts import validate_output


def test_validator_accepts_clean_research_artifacts(tmp_path):
    market = tmp_path / "us"
    market.mkdir()

    pd.DataFrame(
        {
            "run_id": ["r1", "r2"],
            "market": ["US", "US"],
            "symbol": ["SPY", "SPY"],
            "as_of": pd.to_datetime(["2020-01-10", "2020-01-13"], utc=True),
            "fold_id": [0, 0],
            "probability": [0.7, 0.3],
            "probability_threshold": [0.6, 0.6],
        }
    ).to_parquet(market / "historical_model_output.parquet", index=False)

    pd.DataFrame(
        {
            "symbol": ["SPY", "SPY"],
            "signal_ts": pd.to_datetime(["2020-01-10", "2020-01-13"], utc=True),
            "signal": ["BUY", "SELL"],
            "entry_allowed": [True, False],
            "probability": [0.7, 0.3],
            "probability_threshold": [0.6, 0.6],
            "exit_threshold": [0.4, 0.4],
            "fold_id": [0, 0],
            "run_id": ["r1", "r2"],
        }
    ).to_parquet(market / "historical_strategy_signal.parquet", index=False)

    pd.DataFrame(
        {
            "symbol": ["SPY"],
            "entry_ts": pd.to_datetime(["2020-01-13"], utc=True),
            "exit_ts": pd.to_datetime(["2020-01-14"], utc=True),
            "net_pnl": [1.0],
        }
    ).to_parquet(market / "historical_trades.parquet", index=False)

    pd.DataFrame(
        {
            "ts": pd.to_datetime(["2020-01-13", "2020-01-14"], utc=True),
            "cash": [900.0, 1001.0],
            "position_value": [100.0, 0.0],
            "equity": [1000.0, 1001.0],
            "open_positions": [1, 0],
        }
    ).to_parquet(market / "historical_equity.parquet", index=False)

    (market / "fold_metrics.json").write_text(
        json.dumps(
            [
                {
                    "fold": {
                        "train_end": "2019-01-01T00:00:00+00:00",
                        "valid_start": "2019-01-10T00:00:00+00:00",
                        "valid_end": "2019-04-01T00:00:00+00:00",
                        "test_start": "2019-04-10T00:00:00+00:00",
                        "test_end": "2019-10-01T00:00:00+00:00"
                    },
                    "selected_features": ["a", "b", "c", "d", "e"]
                }
            ]
        ),
        encoding="utf-8",
    )
    (market / "experiment.json").write_text(
        json.dumps({"mode": "BACKTEST"}),
        encoding="utf-8",
    )
    (market / "historical_performance.json").write_text(
        json.dumps({"trade_count": 1}),
        encoding="utf-8",
    )
    (market / "run_summary.json").write_text(
        json.dumps({"price_source": "RAW_ANCHOR_OHLC"}),
        encoding="utf-8",
    )
    (tmp_path / "historical_experiment_status.json").write_text(
        json.dumps(
            {
                "status": "READY",
                "research_only": True,
                "live_execution": False,
                "neon_write": False,
                "markets": {"US": {"status": "READY"}}
            }
        ),
        encoding="utf-8",
    )

    report = validate_output(tmp_path)
    assert report["status"] == "READY"
    assert report["ready_for_neon"] is True
