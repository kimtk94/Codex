import unittest
from pathlib import Path
import pandas as pd
from research.regime_countertrend.advanced_failure_audit import indicators,audit,FEATURES

CSV=Path("research/regime_countertrend/data/QLD_QQQ_daily_alignment.csv")
class AdvancedAuditTests(unittest.TestCase):
    def test_indicators_are_signal_time_only(self):
        prices=pd.read_csv(CSV)
        before=indicators(prices)
        prices.loc[prices.index[-1],"close_qqq"]*=1.2
        after=indicators(prices)
        pd.testing.assert_frame_equal(before.iloc[:-1],after.iloc[:-1])
    def test_fdr_and_frozen_eras(self):
        prices=pd.read_csv(CSV)
        idx=[180,220,270,290,380,450,570,630,720,800,950,1100,1950,2010,2040,2100,2230,2350]
        trade=pd.DataFrame([{
          "date":prices.iloc[i].date_ny,
          "year":int(prices.iloc[i].date_ny[:4]),
          "event":"UP_DIP" if k%2 else "DOWN_RALLY",
          "net_return":-.032 if k%3==0 else .028,
          "failed":k%3==0} for k,i in enumerate(idx)])
        out,feat,rule=audit(prices,trade)
        self.assertEqual(len(feat),len(FEATURES))
        self.assertTrue(feat.bh_fdr_q.between(0,1).all())
        self.assertEqual(int(rule.query("era=='HOLDOUT_2025_2026' and event=='ALL' and rule=='BASELINE'").n.iloc[0]),6)
if __name__=="__main__":unittest.main()
