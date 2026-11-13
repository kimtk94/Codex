import unittest
import pandas as pd
from research.regime_countertrend.krw_v5_evidence_audit import (
    check_coverage, audit, V5_MODELS
)

class KRWV5EvidenceTests(unittest.TestCase):
    def frame(self):
        v4=pd.DataFrame([
            {"date":"2025-04-01","symbol":"AMD","year":2025,
             "industry":"SEMICONDUCTORS","event":"SIDE_DIP",
             "entry_date":"2025-04-02","exit_date":"2025-04-07",
             "entry_fx_reference_date":"2025-04-01",
             "exit_fx_reference_date":"2025-04-04",
             "entry_fx_age_calendar_days":1,
             "exit_fx_age_calendar_days":3,
             "usd_net_return":.02,"krw_mark_return":-.01,
             "krw_roundtrip_fx_10bps_each_side":-.012,
             "krw_roundtrip_fx_25bps_each_side":-.015,
             "fx_return":-.0294117647,
             "fx_contribution":-.0294117647,
             "interaction_contribution":.02*(-.0294117647),
             "macro_market_selected":True,"macro_peer_selected":False},
            {"date":"2025-04-08","symbol":"NVDA","year":2025,
             "industry":"SEMICONDUCTORS","event":"UP_DIP",
             "entry_date":"2025-04-09","exit_date":"2025-04-10",
             "entry_fx_reference_date":"2025-04-08",
             "exit_fx_reference_date":"2025-04-09",
             "entry_fx_age_calendar_days":1,
             "exit_fx_age_calendar_days":1,
             "usd_net_return":-.02,"krw_mark_return":.01,
             "krw_roundtrip_fx_10bps_each_side":.008,
             "krw_roundtrip_fx_25bps_each_side":.005,
             "fx_return":(.01+.02)/.98,
             "fx_contribution":(.01+.02)/.98,
             "interaction_contribution":-.02*((.01+.02)/.98),
             "macro_market_selected":False,"macro_peer_selected":True}
        ])
        v5=pd.concat([pd.DataFrame([{"date":r.date,"symbol":r.symbol,"year":r.year,
              "model":model,"selected":True,"net_20bp":r.usd_net_return,
              "krw_mark_return":r.krw_mark_return,"krw_win":r.krw_mark_return>0}])
              for _,r in v4.iterrows() for model in V5_MODELS],ignore_index=True)
        return v4,v5
    def test_fx_winner_reversals_detected(self):
        a,b=self.frame()
        _,_,_,_,report=audit(a,b)
        self.assertEqual(report["opportunities"],2)
        self.assertEqual(report["usd_win_krw_loss"],1)
        self.assertEqual(report["usd_loss_krw_win"],1)
        self.assertTrue(report["fx_mark_contribution_identity_valid"])
        self.assertFalse(report["promotion_allowed"])
    def test_date_lookahead_rejected(self):
        a,b=self.frame()
        a.loc[0,"entry_fx_reference_date"]="2025-04-02"
        with self.assertRaises(ValueError):check_coverage(a,b)
    def test_missing_one_model_predictions_rejected(self):
        a,b=self.frame()
        b=b[b.model!="FX_REGIME_BASE"]
        with self.assertRaises(ValueError):check_coverage(a,b)
    def test_duplicate_events_rejected(self):
        a,b=self.frame()
        with self.assertRaises(ValueError):
            check_coverage(pd.concat([a,a.iloc[[0]]],ignore_index=True),b)
if __name__=="__main__":unittest.main()
