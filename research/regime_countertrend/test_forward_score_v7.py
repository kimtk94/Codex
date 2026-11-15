import json
import tempfile
import unittest
from datetime import datetime,timezone
import numpy as np
import pandas as pd

from research.regime_countertrend.forward_score_v7 import (
    audit_frozen_vintage,run_forward,score_frozen_candidates
)
from research.regime_countertrend.freeze_krw_model_v7 import (
    FIRST_PROSPECTIVE,LAST_TRAIN_SESSION
)
from research.regime_countertrend.sector_price_sources_v3 import manifest_load
from research.regime_countertrend.test_freeze_krw_model_v7 import (
    KRWProspectiveFreezeV7Tests
)

class FrozenProspectiveScorerV7Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=manifest_load(
          "research/regime_countertrend/universe_sector_v3.json")

    def setup_audit(self):
        model=KRWProspectiveFreezeV7Tests().valid_fixture()[1]
        names=[a["symbol"] for a in self.manifest["universe"]
               if a["asset_class"]!="CRYPTO"]
        assets={sym:pd.DataFrame({
            "date":["2024-12-31","2026-11-10","2026-11-13"],
            "close":[100.,110.,111.]}) for sym in names}
        anchors={sym:{"historical_checkpoints":{
            "2024-12-31":100.,"2026-11-10":110.}} for sym in names}
        fx=pd.DataFrame({"date":["2026-11-10","2026-11-13"],
                         "usdkrw_close":[1341.91,1350.]})
        model["source_price_provenance"]={
            "anchors":anchors,"usdkrw_last_close":1341.91}
        return model,assets,fx

    def test_all_24_market_and_fx_anchors_are_checked(self):
        model,data,fx=self.setup_audit()
        result=audit_frozen_vintage(data,fx,model)
        self.assertEqual(result["status"],"PASS_FROZEN_V7_VINTAGE")
        self.assertEqual(result["checks"],49)
        fx.loc[0,"usdkrw_close"]*=1.007
        result=audit_frozen_vintage(data,fx,model)
        self.assertEqual(result["status"],"HOLD_SOURCE_VINTAGE_DRIFT")
        self.assertTrue(any("USDKRW" in x for x in result["failures"]))

    def test_changed_adjusted_historical_price_blocks_future_scoring(self):
        model,data,fx=self.setup_audit()
        data["AAPL"].loc[data["AAPL"].date=="2024-12-31","close"]+=.2
        result=audit_frozen_vintage(data,fx,model)
        self.assertEqual(result["status"],"HOLD_SOURCE_VINTAGE_DRIFT")
        self.assertTrue(any("AAPL" in x for x in result["failures"]))

    def test_no_future_session_does_not_download_market_data(self):
        model,data,fx=self.setup_audit()
        calls=[]
        def blocked_download(*args,**kwargs):
            calls.append(args)
            raise AssertionError("must not fetch before 2026-11-16 close")
        with tempfile.TemporaryDirectory() as tmp:
            decision=run_forward(model,self.manifest,tmp,
                 now_utc=datetime(2026,11,15,11,0,tzinfo=timezone.utc),
                 downloader=blocked_download)
            self.assertEqual(decision["status"],"HOLD_NO_POST_FREEZE_SESSION")
            self.assertEqual(calls,[])
            self.assertEqual(decision["asof_last_nyse_session"],"2026-11-13")
            self.assertFalse(decision["promotion_allowed"])
            self.assertTrue(json.loads(
                open(tmp+"/decision.json").read())["v7_model_frozen"])

    def test_before_prospective_start_no_candles_create_signals(self):
        model,data,fx=self.setup_audit()
        signals,outcomes=score_frozen_candidates({},{},fx,self.manifest,
                                                  model,"2026-11-13")
        self.assertTrue(signals.empty)
        self.assertTrue(outcomes.empty)

if __name__=="__main__":
    unittest.main()
