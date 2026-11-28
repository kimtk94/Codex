import unittest
import numpy as np
import pandas as pd
from sector_tail_excess import attach, compare, overlap_cluster_sizes, rank_auc, METRICS


class SectorTailContracts(unittest.TestCase):
    def setUp(self):
        self.cal=pd.bdate_range("2025-01-02",periods=10)
        self.prices={s:pd.DataFrame({"open":np.arange(100.,110.),"close":np.arange(101.,111.)},index=self.cal)
                     for s in ("SPY","QQQ","SMH")}
        self.f=pd.DataFrame({"symbol":["NVDA","AMD"],"signal_date":[self.cal[0]]*2,
            "entry_date":[self.cal[1]]*2,"exit_date":[self.cal[4]]*2,
            "gross_return":[.102,.022],"net_return":[.1,.02],"qualifies":[True,False]})

    def test_exact_horizon_and_same_date_benchmark_cancels(self):
        q=attach(self.f,self.prices)
        self.assertAlmostEqual(q.SPY.iloc[0],105./101.-1)
        d=compare(q,["signal_date"])
        self.assertAlmostEqual(d.ex_SPY.iloc[0],.08)
        self.assertAlmostEqual(d.net_return.iloc[0],.08)
        self.assertEqual(q.large.tolist(),[1,0])

    def test_wrong_horizon_and_missing_reference_rejected(self):
        f=self.f.copy();f["exit_date"]=self.cal[3]
        with self.assertRaisesRegex(ValueError,"BENCHMARK_HORIZON_MISMATCH"):
            attach(f,self.prices)
        p=dict(self.prices);p["QQQ"]=p["QQQ"].drop(self.cal[4])
        with self.assertRaisesRegex(ValueError,"MISSING_OR_INVALID_BENCHMARK_PRICE"):
            attach(self.f,p)

    def test_episode_weights_dates_not_candidate_count(self):
        f=pd.DataFrame({"episode":[1]*4,"qualifies":[True,True,True,False],
                        "signal_date":["a","a","b","c"]})
        for k in METRICS:f[k]=[.1,.1,.3,0.]
        self.assertAlmostEqual(compare(f,[],episode=True).net_return.iloc[0],.2)
        self.assertTrue(compare(f.loc[f.qualifies],[],episode=True).empty)

    def test_overlap_clusters_and_tied_rank(self):
        g=pd.DataFrame({"episode":[1,1,1,2],"entry_date":self.cal[[1,3,8,3]],
                        "exit_date":self.cal[[4,6,9,6]]})
        self.assertEqual(overlap_cluster_sizes(g),[2,1,1])
        r=pd.DataFrame({"v":[1.,2.,2.,3.],"large":[0,0,1,1]})
        self.assertEqual(rank_auc(r,"v"),(.875,4))


if __name__=="__main__":unittest.main()
