import unittest
import pandas as pd
from research.regime_countertrend.vintage_audit_v6 import (
    audit_price_vintage,signal_fingerprint
)

class VintageV6Tests(unittest.TestCase):
    def fixture(self):
        old={"QQQ":{"2024-12-31":500.,"2026-11-10":650.},
             "HYG":{"2024-12-31":70.,"2026-11-10":78.}}
        prices={sym:pd.DataFrame({"date":list(x),"close":list(x.values())})
                for sym,x in old.items()}
        fx=pd.DataFrame({"date":["2026-11-10"],"usdkrw_close":[1334.]})
        v4=pd.DataFrame([
          {"date":"2025-01-03","symbol":"QQQ","year":2025,
            "macro_market_selected":True},
          {"date":"2025-01-05","symbol":"HYG","year":2025,
            "macro_market_selected":False}])
        v5=v4[["date","symbol","year"]].copy()
        v5["model"]="FX_REGIME_BASE";v5["selected"]=[True,False]
        refs={
         "V4_ETF_MARKET":{"selected":1,"sha256":signal_fingerprint(v4,"macro_market_selected")["sha256"]},
         "V5_KRW_REGIME_BASE":{"selected":1,"sha256":signal_fingerprint(v5,"selected")["sha256"]},
         "ALL_EVALUABLE_PROXY_EVENTS":{"events":2,"sha256":signal_fingerprint(v4)["sha256"]}
        }
        base={"symbols":old,"revision_hold_threshold_bps":5.,
              "fx_baseline_2026_11_10_krw_per_usd":1334.,
              "frozen_selected_signal_sha256":refs,"source_artifact_id":100}
        return prices,fx,base,v4,v5
    def test_exact_vintage_and_identical_models_pass_source_only(self):
        prices,fx,base,v4,v5=self.fixture()
        rows,meta=audit_price_vintage(prices,fx,base,v4,v5)
        self.assertEqual(meta["status"],"PASS_FROZEN_VINTAGE")
        self.assertEqual(len(rows),4)
        self.assertFalse(meta["promotion_allowed"])
    def test_back_adjustment_before_anchor_is_detected(self):
        prices,fx,base,v4,v5=self.fixture()
        prices["HYG"].loc[prices["HYG"].date=="2024-12-31","close"]*=.995
        rows,meta=audit_price_vintage(prices,fx,base,v4,v5)
        self.assertEqual(meta["status"],"HOLD_REVISED_RETROSPECTIVE_DATA")
        self.assertEqual(meta["affected_equity_or_etf_symbols"],["HYG"])
        self.assertEqual(meta["revised_or_missing_checkpoint_rows"],1)
    def test_fx_revision_and_changed_selected_identity_are_hold(self):
        prices,fx,base,v4,v5=self.fixture()
        fx.loc[0,"usdkrw_close"]=1341.91
        v4.loc[0,"macro_market_selected"]=False
        _,meta=audit_price_vintage(prices,fx,base,v4,v5)
        self.assertEqual(meta["fx_status"],"HOLD_REVISED_FX")
        self.assertFalse(meta["frozen_selection_identity"]["V4_ETF_MARKET"]["matches"])
        self.assertEqual(meta["status"],"HOLD_REVISED_RETROSPECTIVE_DATA")
    def test_duplicate_identity_rejected(self):
        v4=pd.DataFrame([{"date":"2025-01-03","symbol":"AMD","year":2025}]*2)
        with self.assertRaises(ValueError):signal_fingerprint(v4)
if __name__=="__main__":unittest.main()
