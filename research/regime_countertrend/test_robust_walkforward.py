import json
import unittest
from pathlib import Path

import pandas as pd
from research.regime_countertrend.robust_walkforward import (
    RULES,simulate,signal_features,audit,choose_rule
)
from research.regime_countertrend.failure_diagnostics import run as original_signals

PRICE=Path("research/regime_countertrend/data/QLD_QQQ_daily_alignment.csv")
OUT=Path("results/regime_countertrend/robustness")

class GapAwareWalkforwardTests(unittest.TestCase):
    def make_price(self,high_second=101,low_second=99,open_third=94):
        days=pd.date_range("2025-01-01",periods=7)
        return pd.DataFrame({"date_ny":days.astype(str),
          "open_qld":[100,100,open_third,100,100,100,100],
          "high_qld":[101,high_second,max(95,open_third),101,101,101,101],
          "low_qld":[99,low_second,min(93,open_third),99,99,99,99],
          "close_qld":[100,100,94,100,100,100,100]})
    def test_gap_loss_uses_next_open_not_stop(self):
        result=simulate(self.make_price(),0)
        self.assertEqual(result["outcome"],"GAP_SL")
        self.assertAlmostEqual(result["net"],-.062)
    def test_dual_barrier_reports_both_outcomes(self):
        prices=self.make_price(high_second=104,low_second=96)
        p=simulate(prices,0,"STOP_FIRST")
        q=simulate(prices,0,"TARGET_FIRST")
        self.assertTrue(p["ambiguity"])
        self.assertAlmostEqual(p["net"],-.032)
        self.assertAlmostEqual(q["net"],.028)
    def test_no_feature_lookahead(self):
        data=pd.read_csv(PRICE)
        before=signal_features(data)
        data.loc[data.index[-1],"close_qqq"]*=1.7
        after=signal_features(data)
        pd.testing.assert_frame_equal(before.iloc[:-1],after.iloc[:-1])
    def test_insufficient_training_selects_baseline(self):
        d=pd.DataFrame({"year":[2024]*5,"net_20bp":[.01]*5,
             **{k:[True]*5 for k in RULES}})
        self.assertEqual(choose_rule(d),"BASELINE")
    def test_frozen_prices_and_annual_split(self):
        prices=pd.read_csv(PRICE)
        old,_=original_signals(prices)
        events,fix,wf,verdict=audit(prices,old[["date","event"]])
        self.assertEqual(len(events),64)
        self.assertEqual(verdict["gap_exits"],9)
        self.assertEqual(verdict["ambiguous_events"],1)
        self.assertEqual(verdict["wf_opportunities"],56)
        self.assertFalse(verdict["approval_allowed"])
        self.assertEqual(set(fix),{"20bp","40bp","80bp"})
        for year,g in wf.groupby("year"):
            cutoff=f"{year}-01-01"
            self.assertTrue(all(str(x)<cutoff for x in g.training_last_exit.dropna()))
        OUT.mkdir(parents=True,exist_ok=True)
        events.to_csv(OUT/"events.csv",index=False)
        wf.to_csv(OUT/"annual_walkforward.csv",index=False)
        for cost,frame in fix.items():
            frame.to_csv(OUT/f"fixed_{cost}.csv",index=False)
        (OUT/"verdict.json").write_text(json.dumps(verdict,indent=2))
        print("ROBUST_WF_RESULTS",json.dumps(verdict))
        hold=fix["20bp"].query("era=='REVISITED_2025_2026' and event=='ALL'")
        print("REVISITED_HOLDOUT",hold.to_json(orient="records"))
if __name__=="__main__":unittest.main()
