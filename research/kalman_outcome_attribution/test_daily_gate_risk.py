import unittest
import numpy as np
import pandas as pd

from daily_gate_risk import outcomes, contrasts, two_way, rank_auc, describe, difference, METRICS


class DailyGateRiskContracts(unittest.TestCase):
    def test_cost_boundaries_and_same_return_difference(self):
        f=pd.DataFrame({"signal_date":["2025-01-02"]*3,"symbol":["A","B","C"],
            "qualifies":[True,True,False],"gross_return":[.002,-.048,.03]})
        q=outcomes(f,20)
        self.assertEqual(q.win.tolist(),[0,0,1])
        self.assertEqual(q.severe.tolist(),[0,1,0])
        self.assertEqual(describe(q.loc[q.qualifies])["severe"],1)
        self.assertAlmostEqual(contrasts(q,["signal_date"]).net.iloc[0],
                               contrasts(outcomes(f,80),["signal_date"]).net.iloc[0])
        with self.assertRaisesRegex(ValueError,"UNREGISTERED_COST"):
            outcomes(f,30)

    def test_missing_arm_not_filled_and_date_weighting(self):
        f=pd.DataFrame({"signal_date":["a","a","a","b","b","c"],"qualifies":[True,True,False,True,False,True],
            "net":[.10,.20,0.,0.,.10,.99],"win":[1,1,0,0,1,1],"severe":[0]*6})
        q=contrasts(f,["signal_date"])
        self.assertEqual(q.index.tolist(),["a","b"])
        self.assertAlmostEqual(q.net.mean(),.025)
        self.assertEqual(len(contrasts(f.loc[f.qualifies],["signal_date"])),0)
        self.assertEqual(len(contrasts(f.iloc[:0],["signal_date"])),0)

    def test_symbol_and_date_fixed_effect_identification(self):
        f=pd.DataFrame({"symbol":["A","B","A","B"],"signal_date":["a","a","b","b"],
            "qualifies":[True,False,False,True],"net":[.13,.2,0.,.33],
            "win":[1,1,0,1],"severe":[0,0,0,0]})
        r=two_way(f)
        self.assertTrue(r["identified"])
        self.assertAlmostEqual(r["coefficients"]["net"],.13)
        f["qualifies"]=[True,True,False,False]
        r=two_way(f)
        self.assertFalse(r["identified"])
        self.assertIsNone(r["coefficients"])

    def test_rank_auc_missing_and_ties(self):
        x=pd.DataFrame({"natr14":[1.,2.,2.,4.,np.nan],"severe":[0,0,1,1,1]})
        a,n=rank_auc(x,"natr14")
        self.assertEqual(n,4);self.assertAlmostEqual(a,.875)
        self.assertEqual(rank_auc(x.loc[x.severe.eq(1)],"natr14"),(None,0))


if __name__=="__main__":
    unittest.main()
