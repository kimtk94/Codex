import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from research.regime_countertrend.krw_monte_carlo_v7 import (
    CAPITAL_KRW,MODELS,POLICIES,ETF_BENCHMARKS,
    _stationary_indices,load_joint_equity,simulate_joint_blocks,run_mc
)

class KRWMonteCarloV7Tests(unittest.TestCase):
    def test_one_shared_index_preserves_exact_common_shocks(self):
        rng=np.random.default_rng(17)
        idx=_stationary_indices(n_periods=100,horizon=252,mean_block=20,
                                simulations=300,rng=rng)
        self.assertEqual(idx.shape,(300,252))
        self.assertTrue(((idx>=0)&(idx<100)).all())
        # All components sample the same shock indices; never independently.
        joint=np.column_stack([np.arange(100),np.arange(100)])
        out=joint[idx]
        np.testing.assert_array_equal(out[:,:,0],out[:,:,1])
        fraction=((idx[:,1:]-idx[:,:-1])%100==1).mean()
        self.assertGreater(fraction,.85)

    def test_repeated_fixed_seed_returns_identical_probabilities(self):
        rng=np.random.default_rng(101)
        models=["V4_ETF_MARKET__USD_RETAIN","QQQ","SPY","USD_CASH_ONLY"]
        history=rng.normal(0,.01,(300,4))
        history[:,1]=history[:,0]*.6+rng.normal(0,.008,300)
        first=np.array([.999,.998,.998,.999],float)
        first_result=simulate_joint_blocks(history,first,models,
            lengths=(5,20),horizons=(252,),n_simulations=300,
            batch=70,seed=222)
        next_result=simulate_joint_blocks(history,first,models,
            lengths=(5,20),horizons=(252,),n_simulations=300,
            batch=70,seed=222)
        pd.testing.assert_frame_equal(first_result,next_result)
        self.assertEqual(len(first_result),8)
        self.assertFalse(first_result.p_terminal_loss.isna().any())
        self.assertTrue(first_result.p_terminal_loss.between(0,1).all())
        self.assertTrue(first_result.p_max_drawdown_below_minus_20pct.between(0,1).all())

    def test_negative_model_daily_drift_always_loses_to_positive_qqq(self):
        names=["V4_ETF_MARKET__USD_RETAIN","QQQ","SPY","USD_CASH_ONLY"]
        ret=np.column_stack([
            np.full(260,-.003),np.full(260,.002),
            np.full(260,.001),np.zeros(260)])
        result=simulate_joint_blocks(ret,np.ones(4),names,
            lengths=(5,),horizons=(252,),n_simulations=200,batch=40)
        model=result.loc[result.asset==names[0]].iloc[0]
        self.assertEqual(model.p_terminal_loss,1.0)
        self.assertEqual(model.p_underperform_QQQ,1.0)
        self.assertEqual(model.p05_total_return_pct,model.p95_total_return_pct)

    def test_initial_friction_is_applied_once_not_every_resampled_day(self):
        names=["V5_KRW_REGIME_BASE__USD_RETAIN","QQQ","SPY","USD_CASH_ONLY"]
        ret=np.zeros((300,4))
        first=np.array([.99,1.,1.,1.])
        result=simulate_joint_blocks(ret,first,names,
            lengths=(5,20),horizons=(252,"observed_days"),
            n_simulations=100,batch=30)
        focus=result[result.asset==names[0]]
        np.testing.assert_allclose(focus.median_total_return_pct,-1.,atol=1e-12)
        np.testing.assert_allclose(focus.p05_total_return_pct,-1.,atol=1e-12)

    def test_full_pipeline_requires_exact_date_and_policy_reconciliation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            n=280
            days=pd.bdate_range("2022-01-03",periods=n).strftime("%Y-%m-%d")
            fx=1300+np.arange(n)*.05
            reference=np.full(n,CAPITAL_KRW,dtype=float)
            report=[]
            for i,model in enumerate(MODELS):
                for j,policy in enumerate(POLICIES):
                    val=CAPITAL_KRW*(.999*np.exp(np.arange(n)*(.0003+i*.00001-j*.00005)))
                    key=f"{model}__{policy}"
                    usd_exposure=0.8 if policy=="USD_RETAIN" else 0.
                    pd.DataFrame({
                        "date":days,"equity_krw":val,
                        "cash_krw":val*(1-usd_exposure),
                        "cash_usd":val*usd_exposure/fx,
                        "position_mark_usd":np.zeros(n),
                        "open_positions":np.zeros(n),
                        "fx_rate":fx
                    }).to_csv(root/f"{key}__10bps_equity.csv",index=False)
                    for spread in (0,10,25):
                        report.append({"model":model,"cash_policy":policy,
                            "spread_per_conversion_leg_bps":spread,
                            "initial_to_final_krw_return_pct":(
                                float(val[-1]/CAPITAL_KRW-1)*100 if spread==10 else 0),
                            "portfolio_status":"SYNTHETIC_NOT_BROKER_RECONCILED"})
            pd.DataFrame(report).to_csv(root/"policy_comparison.csv",index=False)
            for j,sym in enumerate(ETF_BENCHMARKS):
                val=CAPITAL_KRW*(.998*np.exp(np.arange(n)*(.0003+j*.00001)))
                pd.DataFrame({"date":days,"equity_krw":val}).to_csv(
                    root/f"passive_{sym}_equity_krw.csv",index=False)
            equity,fields,returns,friction,exposure,policy=load_joint_equity(root)
            self.assertEqual(len(fields),11)
            self.assertEqual(returns.shape,(279,11))
            self.assertEqual(len(exposure),4)
            self.assertEqual(len(policy),12)
            results,decision=run_mc(root,root/"mc",n_simulations=150,seed=2026)
            self.assertFalse(decision["promotion_allowed"])
            self.assertEqual(len(results),3*2*11)
            self.assertTrue((root/"mc/block_monte_carlo_krw_risk.csv").is_file())
            self.assertTrue((root/"mc/decision.json").is_file())
            self.assertEqual(decision["historical_daily_changes"],279)

    def test_broker_claims_and_missing_benchmarks_fail_closed(self):
        with self.assertRaises(ValueError):
            simulate_joint_blocks(np.zeros((300,3)),np.ones(3),
                 ["V4_ETF_MARKET__USD_RETAIN","QQQ","SPY"],
                 lengths=(5,),horizons=(252,),n_simulations=100)

if __name__=="__main__":
    unittest.main()
