import unittest
import numpy as np
import pandas as pd

from regime_cash_replay import context,masks,audit_original


class RegimeCashContracts(unittest.TestCase):
    def test_fixed_gates_and_missing_vix_abstention(self):
        f=pd.DataFrame({"family":["BULL_TREND","BULL_TREND","BULL_LOGISTIC",
                                  "BULL_LOGISTIC","BEAR_LOGISTIC","BEAR_LOGISTIC","BEAR_RULE"],
                        "mom_regime":["UP","SIDEWAYS","DOWN","SIDEWAYS","DOWN","DOWN","DOWN"],
                        "ret5":[.1,.1,-.01,-.02,.01,.01,.01],
                        "spy5":[.1,.1,.01,-.01,.01,.01,.01],
                        "vix":[15.,15.,15.,15.,20.,np.nan,25.],
                        "gld5":[0.]*7})
        r=masks(f)
        self.assertEqual(r["REGIME_SWITCH_BEAR"].tolist(),[True,False,True,False,True,True,False])
        self.assertEqual(r["REGIME_SWITCH_CASH"].tolist(),[True,False,True,False,False,False,False])
        self.assertEqual(r["DISCOVERY_GATES"].tolist(),[False,False,True,False,True,False,False])
        self.assertEqual(r["BULL_PLUS_BEAR"].tolist(),[False,False,True,True,True,True,False])

    def test_volatility_cash_gates_abstain_without_forced_exit(self):
        f=pd.DataFrame({"family":["BULL_TREND","BULL_LOGISTIC","BEAR_LOGISTIC",
                                  "BEAR_LOGISTIC","BEAR_LOGISTIC","BULL_TREND"],
                        "mom_regime":["UP","DOWN","DOWN","SIDEWAYS","DOWN","UP"],
                        "ret5":[0.]*6,"spy5":[0.]*6,"vix":[25.]*6,"gld5":[0.]*6,
                        "spy_realized_vol20_lag":[.21,.2,.19,.25,np.nan,.1]})
        r=masks(f)
        self.assertEqual(r["REGIME_SWITCH_AVOID_HIGH_DOWN"].tolist(),
                         [True,False,True,True,False,True])
        self.assertEqual(r["REGIME_SWITCH_AVOID_ALL_HIGH"].tolist(),
                         [False,False,True,False,False,True])
        self.assertFalse(r["CASH_ONLY"].any())
        self.assertTrue(r["REGIME_SWITCH_BEAR"].all())

    def test_context_is_previous_session_only(self):
        dates=pd.bdate_range("2024-01-01",periods=60)
        p={s:pd.DataFrame({"close":np.linspace(100,120,60)},index=dates)
           for s in ("SPY","GLD","^VIX")}
        d=dates[30];a=context(p)
        for f in p.values():f.loc[d:,"close"]*=5
        pd.testing.assert_frame_equal(a.loc[:d],context(p).loc[:d])
        self.assertTrue(pd.isna(a.mom_regime.iloc[0]))

    def test_original_replay_rejects_changed_cash_and_fills(self):
        date=pd.Timestamp("2025-01-06")
        curve=pd.DataFrame({"equity":[100001.]},index=pd.DatetimeIndex([date],name="date"))
        fill=pd.DataFrame({"symbol":["SPY"],"signal_date":["2024-12-31"],
                           "entry_date":["2025-01-02"],"exit_date":["2025-01-06"],"net_pnl":[1.]})
        original=curve.reset_index().assign(scenario="TEST")
        ex=fill.assign(scenario="TEST")
        for c in ["signal_date","entry_date","exit_date"]:ex[c]=pd.to_datetime(ex[c])
        r=audit_original(curve,fill,"TEST",(original,ex))
        self.assertEqual(r["fills"],1)
        changed=curve.copy();changed.equity+=.01
        with self.assertRaisesRegex(ValueError,"BASELINE_REPLAY_MISMATCH"):
            audit_original(changed,fill,"TEST",(original,ex))
        with self.assertRaisesRegex(ValueError,"BASELINE_FILL_KEY_MISMATCH"):
            audit_original(curve,fill.assign(symbol="QQQ"),"TEST",(original,ex))


if __name__=="__main__":
    unittest.main()
