import unittest
import pandas as pd
from research.regime_countertrend.sector_ablation_v3 import evaluate

class IndustryAblationTests(unittest.TestCase):
    def sample(self):
        return pd.DataFrame([
            {"date":f"2025-01-{d:02d}","year":2025,
             "symbol":symbol,"industry":industry,"event":evt,
             "net_20bp":v,"win":int(v>0),
             "industry_model_available":industry=="SEMICONDUCTORS",
             "symbol_model_available":True,
             "global_selected":i%3==0,
             "hierarchical_selected":i%4==0}
            for i,(d,symbol,industry,evt,v) in enumerate([
             (2,"AMD","SEMICONDUCTORS","SIDE_DIP",-.032),
             (3,"NVDA","SEMICONDUCTORS","SIDE_DIP",.028),
             (6,"AMD","SEMICONDUCTORS","SIDE_DIP",-.032),
             (7,"NVDA","SEMICONDUCTORS","SIDE_DIP",.028),
             (8,"AAPL","TECH_HARDWARE","UP_DIP",.028),
             (9,"AAPL","TECH_HARDWARE","SIDE_DIP",-.032),
             (10,"AAPL","TECH_HARDWARE","SIDE_DIP",.028),
             (11,"AAPL","TECH_HARDWARE","SIDE_DIP",-.032)
            ])])
    def test_no_promotion_and_peer_subset(self):
        cost,industry,meta=evaluate(self.sample(),iterations=300)
        self.assertFalse(meta["promotion_allowed"])
        self.assertFalse(meta["industry_model_auto_promotion_allowed"])
        self.assertEqual(meta["evaluated"],8)
        self.assertEqual(meta["peer_available_events"],4)
        self.assertEqual(set(cost.cost),{"20bp","40bp","80bp"})
        self.assertEqual(set(cost.model),
            {"BASELINE","MARKET_FACTOR","INDUSTRY_AND_STOCK"})
        self.assertEqual(meta["placebo"]["market"]["selection_control"],
                          "year x industry x signal_event")
    def test_cost_decreases_return_and_same_cohort(self):
        cost,_,meta=evaluate(self.sample(),iterations=200)
        a=cost.query("cohort=='ALL' and model=='INDUSTRY_AND_STOCK'")
        self.assertGreater(a.query("cost=='20bp'").per_opportunity.iloc[0],
                           a.query("cost=='80bp'").per_opportunity.iloc[0])
    def test_duplicate_date_stock_rejected(self):
        p=self.sample()
        with self.assertRaises(ValueError):
            evaluate(pd.concat([p,p.iloc[[0]]],ignore_index=True))
if __name__=="__main__":unittest.main()
