import json
import unittest
import numpy as np
import pandas as pd
from research.regime_countertrend.sector_price_sources_v3 import (
    manifest_load,parse_chart,apply_ticker_trade_eligibility
)
from research.regime_countertrend.sector_hierarchy_v3 import (
    make_pair,stock_proxy,stock_correlation_report,run_hierarchy
)
from research.regime_countertrend.correlated_factor_model import FEATURES,feature_frame

PATH="research/regime_countertrend/universe_sector_v3.json"
PRICE="research/regime_countertrend/data/QLD_QQQ_daily_alignment.csv"

class SectorHierarchyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=manifest_load(PATH)
        cls.prices=pd.read_csv(PRICE)
    def test_all_previously_agreed_assets_and_industry_pools(self):
        stocks=[a for a in self.manifest["universe"] if a["asset_class"]=="STOCK"]
        self.assertEqual(len(stocks),14)
        semi=[a["symbol"] for a in stocks if a["industry"]=="SEMICONDUCTORS"]
        software=[a["symbol"] for a in stocks if a["industry"]=="ENTERPRISE_SOFTWARE_CLOUD"]
        self.assertEqual(set(semi),{"NVDA","AMD","MU","INTC","AMAT"})
        self.assertEqual(set(software),{"MSFT","PLTR","ORCL","CRM"})
        self.assertEqual(sum(a["asset_class"]=="ETF" for a in self.manifest["universe"]),10)
        self.assertEqual(sum(a["asset_class"]=="CRYPTO" for a in self.manifest["universe"]),4)
    def test_ionq_spac_predecessor_excluded(self):
        ionq=next(a for a in self.manifest["universe"] if a["symbol"]=="IONQ")
        self.assertEqual(ionq["equity_ticker_first_trade"],"2021-10-01")
        dates=pd.bdate_range("2021-01-04",periods=380).strftime("%Y-%m-%d")
        data=pd.DataFrame({"date":dates,"close":[10.]*len(dates)})
        valid,removed=apply_ticker_trade_eligibility(data,ionq)
        self.assertGreater(removed,50)
        self.assertTrue((valid.date>="2021-10-01").all())
        self.assertFalse((valid.date<"2021-10-01").any())
    def test_adj_close_ohlc_basis(self):
        periods=pd.bdate_range("2023-01-01",periods=140)
        raw={"chart":{"result":[
            {"timestamp":[int(x.timestamp()) for x in periods.tz_localize("America/New_York")],
            "indicators":{"quote":[{"open":[100.]*140,"high":[102.]*140,
                "low":[99.]*140,"close":[101.]*140,"volume":[100]*140}],
                "adjclose":[{"adjclose":[90.9]*140}]}}
        ]}}
        d=parse_chart(json.dumps(raw).encode(),"TEST")
        self.assertAlmostEqual(d.close.iloc[0],90.9)
        self.assertAlmostEqual(d.open.iloc[0],90)
        self.assertEqual(len(d),140)
    def test_stock_target_feature_schema_and_events(self):
        d=self.prices
        benchmark=pd.DataFrame({"date":d.date_ny,**{
            k:d[f"{k}_qqq"] for k in ("open","high","low","close","volume")}})
        target=pd.DataFrame({"date":d.date_ny,**{
            k:d[f"{k}_qld"] for k in ("open","high","low","close","volume")}})
        pair=make_pair(target,benchmark,"SYNTHETIC_TEST")
        features=feature_frame(pair)
        signals=stock_proxy(pair,"SYNTHETIC_TEST","TECH_HARDWARE")
        self.assertGreater(len(signals),20)
        self.assertEqual(set(FEATURES)-set(signals.columns),set())
        self.assertTrue(np.isfinite(signals[list(FEATURES)].to_numpy()).all())
        self.assertTrue(set(signals.event).issubset({"UP_DIP","DOWN_RALLY","SIDE_DIP"}))
    def test_correlations_train_era_only(self):
        dates=pd.bdate_range("2023-01-01",periods=750).strftime("%Y-%m-%d")
        x=np.linspace(0,15,len(dates))
        a=pd.DataFrame({"date":dates,"close":100+np.arange(len(dates))*.1+np.sin(x)})
        b=pd.DataFrame({"date":dates,"close":85+np.arange(len(dates))*.13+np.sin(x)*1.5})
        first=stock_correlation_report({"AMD":a,"NVDA":b},self.manifest)
        b2=b.copy()
        b2.loc[b2.date>="2025-01-01","close"]=900000
        second=stock_correlation_report({"AMD":a,"NVDA":b2},self.manifest)
        pd.testing.assert_frame_equal(first,second)
        self.assertTrue(first.same_industry.iloc[0])
    def test_pooled_sector_symbol_fallback_without_lookahead(self):
        d=self.prices
        benchmark=pd.DataFrame({"date":d.date_ny,**{
            k:d[f"{k}_qqq"] for k in ("open","high","low","close","volume")}})
        target=pd.DataFrame({"date":d.date_ny,**{
            k:d[f"{k}_qld"] for k in ("open","high","low","close","volume")}})
        pair=make_pair(target,benchmark,"SYNTHETIC_TEST")
        feat=feature_frame(pair)
        common=stock_proxy(pair,"AMD","SEMICONDUCTORS")
        self.assertGreater(len(common),70)
        histories=[];events=[]
        for symbol,industry in (("AMD","SEMICONDUCTORS"),
                                 ("NVDA","SEMICONDUCTORS"),
                                 ("AAPL","TECH_HARDWARE")):
            h=feat.copy();h["symbol"]=symbol;histories.append(h)
            e=common.copy();e["symbol"]=symbol;e["industry"]=industry
            if symbol=="NVDA":
                e.loc[e.index[::5],"win"]=1-e.loc[e.index[::5],"win"]
            events.append(e)
        predictions,folds,meta=run_hierarchy(pd.concat(histories,ignore_index=True),
                    pd.concat(events,ignore_index=True),self.manifest)
        self.assertGreater(len(predictions),0)
        self.assertFalse(meta["promotion_allowed"])
        self.assertTrue((predictions.n_input_features==20).all())
        self.assertFalse(predictions[predictions.symbol=="AAPL"].industry_model_available.any())
        self.assertTrue((predictions.hierarchical_probability.between(0,1)).all())

if __name__=="__main__":
    unittest.main()
