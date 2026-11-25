import unittest
import pandas as pd

from risk_pilot import annual_split, admissible, label, stratified_flag_differences


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


if __name__=="__main__":
    unittest.main()
