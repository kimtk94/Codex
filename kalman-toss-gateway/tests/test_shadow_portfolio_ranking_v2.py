from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from engine.shadow_portfolio_ranking import (
    MARKETS,
    STRATEGIES,
    _assert_wall_clock_freshness,
    build_snapshot,
)
from engine.shadow_portfolio_ranking_writer import validate_snapshot


class ShadowPortfolioRankingTests(unittest.TestCase):
    def _write_market(self, path: Path, market: str, closes: np.ndarray, index: pd.DatetimeIndex) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            {
                "timestamp": index,
                "symbol": market,
                "market": market,
                "currency": "USD",
                "open": closes,
                "high": closes * 1.001,
                "low": closes * 0.999,
                "close": closes,
                "volume": 1000.0,
                "source": "synthetic",
            }
        ).to_parquet(path, index=False)

    def test_build_snapshot_and_safety_contract(self) -> None:
        rng=np.random.default_rng(42)
        idx=pd.date_range("2025-10-01","2026-09-20",freq="D",tz="UTC")
        n=len(idx)
        us=100*np.cumprod(1+rng.normal(0.0005,0.008,n))
        kr=100*np.cumprod(1+rng.normal(0.0003,0.007,n))
        btc=100*np.cumprod(1+rng.normal(0.0008,0.018,n))

        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            market_root=root/"market"
            self._write_market(market_root/"raw/yfinance/yf_spy.parquet","US",us,idx)
            self._write_market(market_root/"raw/yfinance/yf_kospi.parquet","KR",kr,idx)
            self._write_market(market_root/"raw/yfinance/yf_btc.parquet","BTC",btc,idx)

            config={
                "version":"test-shadow-ranking-v2",
                "seed_end":"2026-08-31T00:00:00Z",
                "market_files":{
                    "US":{"path":"raw/yfinance/yf_spy.parquet","max_lag_days":4},
                    "KR":{"path":"raw/yfinance/yf_kospi.parquet","max_lag_days":4},
                    "BTC":{"path":"raw/yfinance/yf_btc.parquet","max_lag_days":2},
                },
                "lookback_days":180,
                "min_observations":90,
                "rebalance_frequency":"M",
                "rebalance_cost_bps":10.0,
                "annualization_days":365,
                "initial_equity":1000000.0,
                "risk_cap_ratio":1.10,
                "simplex_step":0.01,
            }
            config_path=root/"config.json"
            config_path.write_text(json.dumps(config),encoding="utf-8")

            snapshot,targets,audit=build_snapshot(
                market_root=market_root,
                config_path=config_path,
                code_sha="testsha",
            )

            self.assertEqual(snapshot["schema_version"],"kalman-shadow-portfolio-ranking-v2")
            self.assertEqual(snapshot["status"],"READY")
            self.assertEqual({x["strategy"] for x in snapshot["forward_ranking"]},set(STRATEGIES))
            self.assertGreater(snapshot["post_seed_return_rows"],10)
            self.assertFalse(snapshot["invariants"]["trade_execution"])
            self.assertFalse(snapshot["invariants"]["strategy_signal_write"])
            self.assertFalse(snapshot["invariants"]["dashboard_snapshot_write"])
            self.assertTrue(snapshot["invariants"]["research_only"])

            for strategy in STRATEGIES:
                frame=targets[strategy]
                self.assertFalse(frame.empty)
                sums=frame[list(MARKETS)].sum(axis=1)
                self.assertTrue(np.allclose(sums.to_numpy(),1.0,atol=1e-8))
                self.assertTrue((frame[list(MARKETS)]>=-1e-12).all().all())

            self.assertFalse(audit.empty)
            cap=1.10*audit["equal_weight_vol"]+1e-10
            self.assertTrue((audit["blended_vol"]<=cap).all())

            ready=[x for x in snapshot["forward_ranking"] if x["status"]=="READY"]
            self.assertEqual(sorted(x["forward_rank"] for x in ready),list(range(len(ready))))
            validate_snapshot(snapshot)

    def test_wall_clock_freshness_rejects_uniformly_stale_sources(self) -> None:
        files={
            "US":{"max_wall_clock_age_days":3},
            "KR":{"max_wall_clock_age_days":3},
            "BTC":{"max_wall_clock_age_days":1},
        }
        last_raw={
            "US":pd.Timestamp("2026-09-18T00:00:00Z"),
            "KR":pd.Timestamp("2026-09-18T00:00:00Z"),
            "BTC":pd.Timestamp("2026-09-20T00:00:00Z"),
        }
        with self.assertRaisesRegex(RuntimeError,"BTC: stale market source by wall clock"):
            _assert_wall_clock_freshness(
                last_raw,
                files,
                now=pd.Timestamp("2026-09-22T10:00:00Z"),
            )

    def test_wall_clock_freshness_allows_expected_weekend_lag(self) -> None:
        files={
            "US":{"max_wall_clock_age_days":3},
            "KR":{"max_wall_clock_age_days":3},
            "BTC":{"max_wall_clock_age_days":1},
        }
        last_raw={
            "US":pd.Timestamp("2026-09-18T00:00:00Z"),
            "KR":pd.Timestamp("2026-09-18T00:00:00Z"),
            "BTC":pd.Timestamp("2026-09-20T00:00:00Z"),
        }
        _assert_wall_clock_freshness(
            last_raw,
            files,
            now=pd.Timestamp("2026-09-20T10:00:00Z"),
        )

    def test_writer_rejects_trade_enabled_payload(self) -> None:
        payload={
            "schema_version":"kalman-shadow-portfolio-ranking-v2",
            "status":"READY",
            "forward_ranking":[
                {"strategy":"A_EQUAL_WEIGHT","status":"READY","forward_rank":0},
                {"strategy":"B_STATIC_MAX_SHARPE","status":"READY","forward_rank":1},
                {"strategy":"C_RISK_CAP_110","status":"READY","forward_rank":2},
            ],
            "invariants":{
                "research_only":True,
                "entry_allowed_for_real_orders":False,
                "auto_trade_visible":False,
                "production_model_write":False,
                "strategy_signal_write":False,
                "dashboard_snapshot_write":False,
                "toss_execution":False,
                "live_execution":False,
                "trade_execution":True,
            },
        }
        with self.assertRaises(RuntimeError):
            validate_snapshot(payload)


if __name__ == "__main__":
    unittest.main()
