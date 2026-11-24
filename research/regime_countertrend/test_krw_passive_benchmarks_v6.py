import tempfile
import unittest
from pathlib import Path
import pandas as pd
from research.regime_countertrend.krw_passive_benchmarks_v6 import (
    evaluate_buyhold,compare_to_strategies,BENCHMARKS
)

class PassiveKRWBenchV6Tests(unittest.TestCase):
    def prices(self):
        dates=["2026-10-01","2026-10-02","2026-10-05","2026-10-06","2026-10-07"]
        return pd.DataFrame({"date":dates,"close":[100,110,105,120,120]})
    def fx(self):
        return pd.DataFrame({"date":["2026-09-30","2026-10-01","2026-10-02",
            "2026-10-05","2026-10-06"],
            "usdkrw_close":[1000.,1000.,1050.,990.,900.]})
    def test_krw_benchmark_exposes_currency_and_cost(self):
        a,row=evaluate_buyhold(self.prices(),self.fx(),"2026-10-01",
            "2026-10-07","QQQ",initial_krw=1_000_000)
        self.assertEqual(len(a),5)
        self.assertAlmostEqual(row["buy_hold_usd_return_pct"],20.)
        self.assertLess(row["buy_hold_krw_return_pct"],20.)
        self.assertFalse(row["promotion_allowed"])
        b,reference=evaluate_buyhold(self.prices(),self.fx(),
             "2026-10-01","2026-10-07","QQQ",initial_krw=1_000_000,
             fx_spread_bps=0,stock_roundtrip_bps=0)
        self.assertGreater(reference["buy_hold_krw_return_pct"],
                           row["buy_hold_krw_return_pct"])
        self.assertTrue((b.equity_krw>0).all())
    def test_exact_same_time_window_required(self):
        with self.assertRaises(ValueError):
            evaluate_buyhold(self.prices().iloc[:-1],self.fx(),
                            "2026-10-01","2026-10-07","SPY")
    def test_strategy_with_100pct_cash_is_not_alpha(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            daily=pd.DataFrame({
                "date":pd.date_range("2026-01-02",periods=135,freq="B").strftime("%Y-%m-%d"),
                "equity_krw":[10_000_000.]*135
            })
            for model in ("V4_ETF_MARKET","V5_KRW_REGIME_BASE"):
                daily.to_csv(root/f"{model}__USD_RETAIN__10bps_equity.csv",index=False)
            dates=daily.date.tolist()
            etfs={sym:pd.DataFrame({"date":dates,
                     "close":[100.+i/100 for i in range(len(dates))]}) for sym in BENCHMARKS}
            fx_dates=pd.date_range("2025-12-29",periods=190,freq="B").strftime("%Y-%m-%d")
            fx=pd.DataFrame({"date":fx_dates,"usdkrw_close":[1300.]*len(fx_dates)})
            compare,meta=compare_to_strategies(root,etfs,fx)
            self.assertEqual(len(compare),7)
            self.assertFalse(meta["promotion_allowed"])
            self.assertEqual(set(compare.symbol),set(BENCHMARKS)|{"V4_ETF_MARKET","V5_KRW_REGIME_BASE"})
if __name__=="__main__":
    unittest.main()
