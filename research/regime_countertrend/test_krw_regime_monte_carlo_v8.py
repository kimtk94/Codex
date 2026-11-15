import unittest
import numpy as np
import pandas as pd

from research.regime_countertrend.krw_regime_monte_carlo_v8 import (
    SCENARIOS,VOL_TRAIN_END,
    previous_close_regimes,scenario_mask,_runs,
    conditional_joint_indices,conditional_stress
)

class RegimeConditionedKRWMonteCarloV8Tests(unittest.TestCase):
    def synthetic_qqq(self):
        days=pd.bdate_range("2017-01-03",periods=2400).strftime("%Y-%m-%d")
        rng=np.random.default_rng(23)
        daily=rng.normal(0,.012,len(days))+.0007
        close=100*np.exp(np.cumsum(daily))
        return pd.DataFrame({"date":days,"close":close})

    def test_asof_regime_uses_previous_qqq_close_and_pre_2022_vol_threshold(self):
        q=self.synthetic_qqq()
        dates=q.loc[(q.date>"2023-03-01")&(q.date<"2023-06-01"),
                    "date"].tolist()
        state,rule=previous_close_regimes(q,dates)
        self.assertEqual(len(state),len(dates))
        self.assertTrue((state.prior_close_date.astype(str)<state.date).all())
        self.assertEqual(rule["volatility_cutoff_fitted_no_later_than"],VOL_TRAIN_END)
        self.assertEqual(rule["regime_state_lag"],1)
        edited=q.copy()
        edited.loc[edited.date>="2023-06-01","close"]*=50
        later,_=previous_close_regimes(edited,dates)
        pd.testing.assert_frame_equal(state,later)
        self.assertEqual(set(state.prior_trend.unique())-{"UP","DOWN","SIDE"},set())

    def test_missing_market_day_prevents_model_risk_claim(self):
        q=self.synthetic_qqq()
        with self.assertRaises(ValueError):
            previous_close_regimes(q,["2024-01-01","2024-01-06"])

    def test_synchronous_regime_resampler_never_leaves_selected_state(self):
        mask=np.tile(np.r_[np.ones(11,dtype=bool),
                            np.zeros(3,dtype=bool)],20)
        rng=np.random.default_rng(100)
        idx,diag=conditional_joint_indices(mask,252,60,200,rng)
        self.assertEqual(idx.shape,(200,252))
        self.assertTrue(mask[idx].all())
        self.assertLess(diag["average_realized_block_sessions"],60)
        self.assertGreater(diag["forced_boundary_restart_fraction"],0)
        self.assertEqual(_runs(mask)[0],20)
        joint=np.column_stack([np.arange(len(mask)),np.arange(len(mask))])
        sampled=joint[idx]
        np.testing.assert_array_equal(sampled[:,:,0],sampled[:,:,1])

    def test_fully_conditioned_down_scenario_is_a_risk_stress_not_oos(self):
        # 450 days in repeated 15d UP / DOWN / SIDE contiguous blocks,
        # 10 independent DOWN runs; all years are historical descriptive.
        n=450
        days=pd.bdate_range("2022-01-03",periods=n).strftime("%Y-%m-%d")
        trend=np.tile(np.repeat(["UP","DOWN","SIDE"],15),10)
        vol=np.tile(np.repeat([False,True,False],15),10)
        states=pd.DataFrame({"date":days,
            "prior_trend":trend,"prior_high_vol":vol,
            "prior_down_high_vol":(trend=="DOWN")&vol})
        names=["V4_ETF_MARKET__USD_RETAIN",
               "V5_KRW_REGIME_BASE__USD_RETAIN",
               "QQQ","SPY","USD_CASH_ONLY"]
        down=(trend=="DOWN")
        model=np.where(down,-.005,.003)
        qqq=np.where(down,-.012,.006)
        daily=np.column_stack([model,model*.95,qqq,qqq*.7,np.zeros(n)])
        risk,coverage,meta=conditional_stress(
            daily,np.ones(len(names)),names,states,
            conditions=("UP","DOWN","SIDE","DOWN_HIGH_VOL"),
            lengths=(5,20),n_simulations=200,horizon=60,batch=32,seed=9)
        self.assertEqual(meta["held_scenarios"],[])
        self.assertEqual(len(risk),4*2*len(names))
        self.assertEqual(set(coverage.scenario),{"UP","DOWN","SIDE","DOWN_HIGH_VOL"})
        down_risk=risk[(risk.scenario=="DOWN")&
            (risk.requested_mean_block==20)&(risk.asset==names[0])].iloc[0]
        up_risk=risk[(risk.scenario=="UP")&
            (risk.requested_mean_block==20)&(risk.asset==names[0])].iloc[0]
        self.assertEqual(down_risk.p_terminal_loss,1.)
        self.assertEqual(up_risk.p_terminal_loss,0.)
        self.assertTrue((risk.p_terminal_loss.between(0,1)).all())
        self.assertTrue((risk.effective_mean_block<=risk.requested_mean_block*1.5).all())
        self.assertTrue((risk.conditional_full_path_in_requested_state).all())

    def test_underpowered_regime_is_explicitly_held(self):
        n=300
        states=pd.DataFrame({"date":pd.bdate_range("2022-01-03",periods=n).strftime("%Y-%m-%d"),
           "prior_trend":["UP"]*290+["DOWN"]*10,
           "prior_high_vol":[False]*n,
           "prior_down_high_vol":[False]*n})
        names=["V4_ETF_MARKET__USD_RETAIN","QQQ","SPY","USD_CASH_ONLY"]
        out,coverage,decision=conditional_stress(np.zeros((n,4)),
           np.ones(4),names,states,conditions=("UP","DOWN"),
           lengths=(5,),n_simulations=100,horizon=30)
        self.assertIn("DOWN",decision["held_scenarios"])
        self.assertEqual(coverage.loc[coverage.scenario=="DOWN",
               "risk_status"].iloc[0],"HOLD_INSUFFICIENT_REGIME_HISTORY")
        self.assertNotIn("DOWN",set(out.scenario))
        self.assertFalse(out.p_terminal_loss.isna().any())

if __name__=="__main__":
    unittest.main()
