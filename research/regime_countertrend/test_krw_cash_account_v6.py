import tempfile
import unittest
from pathlib import Path
import pandas as pd
from research.regime_countertrend.krw_cash_account_v6 import (
    broker_evidence_gate,selected_research_trades,simulate_cash
)

class KRWCashAccountV6Tests(unittest.TestCase):
    def sample(self):
        prices={
          "AMD":pd.DataFrame({"date":["2026-10-01","2026-10-02","2026-10-05","2026-10-06","2026-10-07"],
                              "open":[100.,100.,105.,103.,102.],
                              "close":[100.,102.,105.,103.,102.]})
        }
        fx=pd.DataFrame({"date":["2026-09-30","2026-10-01","2026-10-02","2026-10-05","2026-10-06"],
                         "usdkrw_close":[1000.,1000.,1100.,1000.,1100.]})
        trades=pd.DataFrame([
          {"date":"2026-10-01","year":2026,"symbol":"AMD",
            "entry_date":"2026-10-02","exit_date":"2026-10-05",
            "usd_net_return":.10,"net_20bp":.10,
            "entry_fx_close_previous_session":1000.,"exit_fx_close_previous_session":1100.,
            "macro_market_selected":True},
          {"date":"2026-10-05","year":2026,"symbol":"AMD",
            "entry_date":"2026-10-06","exit_date":"2026-10-07",
            "usd_net_return":.0,"net_20bp":.0,
            "entry_fx_close_previous_session":1000.,"exit_fx_close_previous_session":1100.,
            "macro_market_selected":True}
        ])
        v4=trades[["date","year","symbol","macro_market_selected"]].copy()
        v4["macro_market_probability"]=[.9,.8]
        v5=v4[["date","year","symbol"]].copy()
        v5["model"]="FX_REGIME_BASE"
        v5["selected"]=[True,True]
        v5["probability"]=[.8,.7]
        return selected_research_trades(trades,v4,v5),prices,fx

    def test_reuse_dollars_without_extra_fx_conversion(self):
        t,prices,fx=self.sample()
        a,events,s=simulate_cash(t,prices,fx,"V4_ETF_MARKET","USD_RETAIN")
        b,_,roundtrip=simulate_cash(t,prices,fx,"V4_ETF_MARKET",
                                    "EACH_SALE_CONVERT_TO_KRW")
        self.assertEqual(s["trades_executed_proxy"],2)
        self.assertEqual(s["fx_conversions"],1)
        self.assertEqual(roundtrip["fx_conversions"],4)
        self.assertEqual(s["skipped_due_capacity_or_cash"],0)
        self.assertGreater(s["last_cash_usd"],0)
        self.assertAlmostEqual(roundtrip["last_cash_usd"],0,places=9)
        self.assertTrue((a.cash_krw>=-1e-5).all())
        self.assertTrue((a.cash_usd>=-1e-5).all())
        self.assertEqual(a.open_positions.iloc[-1],0)
        self.assertNotAlmostEqual(a.equity_krw.iloc[-1],
                                  b.equity_krw.iloc[-1],places=2)
        self.assertTrue((events.action=="BUY_USD").any())

    def test_passive_usd_benchmark_separates_cash_fx_from_stock_selection(self):
        trades,prices,fx=self.sample()
        out=[]
        for cost in (0,10,25):
            _,_,summary=simulate_cash(trades,prices,fx,"V4_ETF_MARKET",
                                      "USD_RETAIN",spread_bps=cost)
            out.append(summary)
            self.assertEqual(summary["passive_krw_cash_return_pct"],0)
            self.assertAlmostEqual(
                summary["initial_to_final_krw_return_pct"]-
                summary["passive_usd_cash_krw_return_pct"],
                summary["excess_vs_passive_usd_cash_pp"],places=9)
        self.assertGreater(out[0]["initial_to_final_krw_return_pct"],
                           out[1]["initial_to_final_krw_return_pct"])
        self.assertGreater(out[1]["initial_to_final_krw_return_pct"],
                           out[2]["initial_to_final_krw_return_pct"])
        self.assertAlmostEqual(out[0]["passive_usd_cash_krw_return_pct"],
            (out[0]["valuation_rate_final"]/out[0]["valuation_rate_initial"]-1)*100,
            places=9)
    def test_position_cap_and_deterministic_order(self):
        trades,prices,fx=self.sample()
        extra=trades.iloc[[0]].copy()
        extra["symbol"]="NVDA"
        extra["date"]="2026-10-01"
        extra["macro_market_probability"]=.5
        extra["entry_date"]="2026-10-02"
        extra["exit_date"]="2026-10-05"
        extra["usd_net_return"]=.02
        enlarged=pd.concat([trades,extra],ignore_index=True)
        prices["NVDA"]=prices["AMD"].copy()
        _,event_log,result=simulate_cash(
            enlarged,prices,fx,"V4_ETF_MARKET","USD_RETAIN",max_positions=1)
        self.assertEqual(result["trades_executed_proxy"],2)
        self.assertEqual(result["skipped_due_capacity_or_cash"],1)
        self.assertTrue((event_log.action=="SKIP_CAPACITY_OR_DUPLICATE").any())

    def test_reject_unfunded_duplicate_or_future_entry(self):
        trades,_,_=self.sample()
        with self.assertRaises(ValueError):
            selected_research_trades(pd.concat([trades,trades.iloc[[0]]]),
                trades[["date","symbol","year","macro_market_selected",
                         "macro_market_probability"]],
                pd.DataFrame({"date":[],"symbol":[],"year":[],
                              "model":[],"selected":[],"probability":[]}))
        trades.loc[0,"entry_date"]=trades.loc[0,"date"]
        with self.assertRaises(ValueError):
            selected_research_trades(trades,trades[["date","symbol","year",
                "macro_market_selected","macro_market_probability"]],
                pd.DataFrame({"date":trades.date,"symbol":trades.symbol,
                    "year":trades.year,"model":"FX_REGIME_BASE",
                    "selected":True,"probability":.7}))

    def test_broker_presence_alone_is_not_actual_reconciliation(self):
        self.assertEqual(broker_evidence_gate()["status"],
                         "HOLD_BROKER_LEDGER_NOT_CONNECTED")
        with tempfile.TemporaryDirectory() as directory:
            schemas={
             "fills.csv":["timestamp_utc","symbol","side","quantity",
                          "price_usd","fee_usd","order_id"],
             "fx_conversions.csv":["timestamp_utc","from_currency",
                "to_currency","amount_from","amount_to","conversion_id"],
             "cash_balances.csv":["timestamp_utc","currency","balance"]}
            for file,cols in schemas.items():
                pd.DataFrame(columns=cols).to_csv(Path(directory)/file,index=False)
            evidence=broker_evidence_gate(directory)
            self.assertEqual(evidence["status"],
                             "HOLD_BROKER_FILES_PRESENT_NOT_RECONCILED")
            self.assertFalse(evidence["actual_fills_verified"])
            self.assertFalse(evidence["actual_fx_conversions_verified"])

if __name__=="__main__":
    unittest.main()
