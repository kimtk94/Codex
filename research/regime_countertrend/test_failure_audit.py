import unittest
import pandas as pd
from research.regime_countertrend.gate_audit import compare
from research.regime_countertrend.failure_stats import evaluate

class FailureAuditTests(unittest.TestCase):
    def fixture(self):
        data=[]
        for year in [2022,2023,2024,2025,2026]:
            for i in range(12):
                fail=i%3==0
                data.append({"date":f"{year}-01-{i+1:02d}","year":year,"event":"UP_DIP" if i%2 else "DOWN_RALLY","net_return":-.032 if fail else .028,"failed":fail,"ma20dist":-.01 if i%2 else .01})
        return pd.DataFrame(data)
    def test_era_split_and_no_promotion_on_small_sample(self):
        d=self.fixture()
        table,status=compare(d)
        self.assertEqual(int(table.query("era=='HOLDOUT_2025_26' and event=='ALL' and strategy=='BASELINE'").trades.iloc[0]),24)
        self.assertIn(status["status"],["HOLD","FURTHER_VALIDATION_REQUIRED"])
    def test_filter_using_holdout_is_not_fit(self):
        d=self.fixture()
        _,before=compare(d)
        d.loc[d.year==2026,"net_return"]=-.2
        _,after=compare(d)
        self.assertEqual(before["holdout_gate_n"],after["holdout_gate_n"])
    def test_stats_requires_columns(self):
        with self.assertRaises(ValueError):
            evaluate(pd.DataFrame({"failed":[True]}))
if __name__=="__main__": unittest.main()
