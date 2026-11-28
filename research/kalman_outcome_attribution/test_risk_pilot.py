import unittest
import pandas as pd

from risk_pilot import annual_split, admissible, label, stratified_flag_differences, fixed_arms, matched_date_random, fixed_arm_metrics


class RiskPilotContracts(unittest.TestCase):
    def test_annual_purge_uses_exit_not_signal_date(self):
        calendar=pd.date_range("2024-12-01","2025-01-15",freq="B")
        frame=pd.DataFrame({
            "signal_date":pd.to_datetime(["2024-12-10","2024-12-20","2024-12-23","2025-01-02"]),
            "exit_date":pd.to_datetime(["2024-12-16","2024-12-26","2025-01-02","2025-01-08"]),
            "net_return":[.02,-.06,.01,.02]})
        train,test,cutoff=annual_split(frame,calendar,2025)
        self.assertEqual(cutoff,pd.Timestamp("2024-12-26"))
        self.assertEqual(len(train),1)
        self.assertEqual(len(test),1)
        self.assertTrue(train.exit_date.lt(cutoff).all())

    def test_small_and_rare_loss_training_abstains(self):
        train=pd.DataFrame({"signal_date":pd.date_range("2024-01-01",periods=120),
                            "net_return":[.01]*60+[-.02]*40+[-.05]*20})
        self.assertTrue(admissible(train,train.iloc[:1]))
        self.assertFalse(admissible(train.iloc[:78],train.iloc[:1]))
        thin=train.copy()
        thin.loc[thin.index[-1],"net_return"]=-.049
        self.assertFalse(admissible(thin,train.iloc[:1]))
        self.assertFalse(admissible(train,train.iloc[:0]))
        win,severe=label(pd.DataFrame({"net_return":[0.,-.049,-.05,.01]}))
        self.assertEqual(win.tolist(),[False,False,False,True])
        self.assertEqual(severe.tolist(),[False,False,True,False])

    def test_stratified_diagnostics_do_not_confuse_symbol_mix(self):
        frame=pd.DataFrame({"symbol":["A","A","B","B","C"],
            "signal_date":pd.to_datetime(["2025-01-02"]*5),
            "flag":[True,False,True,False,True],
            "net_return":[-.06,.01,.02,-.01,-.10]})
        r=stratified_flag_differences(frame)
        self.assertEqual(r["groups"],2)
        self.assertEqual(r["positive_severity_difference"],1)
        self.assertAlmostEqual(r["weighted_severity_difference"],.5)
        self.assertAlmostEqual(r["weighted_return_difference"],-.02)


class FixedArmContracts(unittest.TestCase):
    def test_fixed_selection_and_cost_relabel(self):
        frame=pd.DataFrame({"signal_date":pd.to_datetime(["2025-01-02"]*3),
             "flag":[True,False,False],"vol_flag":[False,True,False],
             "win_prob":[.9,.4,.5],"return_pred":[.01,-.01,0.],
             "gross_return":[-.049,.012,.002],"net_return":[-.051,.01,0.]})
        arms=fixed_arms(frame)
        self.assertEqual(arms["COMBINED_KEEP"].tolist(),[False,False,True])
        result=fixed_arm_metrics(frame)
        self.assertEqual(result["costs"]["20"]["RISK_KEEP"]["n"],2)
        self.assertEqual(result["costs"]["80"]["RISK_KEEP"]["n"],2)
        self.assertAlmostEqual(result["costs"]["20"]["RISK_KEEP"]["mean"],.005)
        self.assertAlmostEqual(result["costs"]["80"]["RISK_KEEP"]["mean"],-.001)
        self.assertFalse(result["portfolio_mdd_verified"])

    def test_random_control_keeps_each_date_count(self):
        frame=pd.DataFrame({"signal_date":pd.to_datetime(["2025-01-02","2025-01-02","2025-01-03"]),
                            "net_return":[-.06,.02,.01]})
        r=matched_date_random(frame,pd.Series([True,False,True]),draws=1000)
        self.assertEqual(r["matched_candidate_count"],2)
        self.assertAlmostEqual(r["random_mean_net_quantiles"][0],-.025)
        self.assertAlmostEqual(r["random_mean_net_quantiles"][-1],.015)
        self.assertTrue(r["not_cash_exposure_matched"])

if __name__=="__main__":
    unittest.main()
