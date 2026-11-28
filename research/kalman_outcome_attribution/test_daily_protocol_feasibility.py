import unittest
import pandas as pd
import numpy as np
from daily_protocol_feasibility import daily_candidates


class DailyProtocolContracts(unittest.TestCase):
    def fixture(self):
        return pd.DataFrame({"spy_above200_lag":[1.,1.,1.,0.,0.,0.],
            "vix_lag":[20.,20.,20.,20.,19.,46.],"prob":[.6,.6,.59,.6,.6,.9],
            "ret5":[-.01,0.,-.02,-.01,-.01,-.01],"spy_mom5_lag":[0.,0.,0.,0.,0.,0.],
            "gld_mom5_lag":[0.,0.,0.,0.,0.,0.],"net_return":[.02,-.03,.01,.02,-.01,.02]},
            index=pd.bdate_range("2024-01-02",periods=6))

    def test_original_gate_boundary_and_no_nonoverlap_filter(self):
        f=self.fixture()
        x=daily_candidates(f,"BULL")
        self.assertEqual(x.index.tolist(),f.index[:2].tolist())
        self.assertEqual(x.qualifies.tolist(),[True,False])
        y=daily_candidates(f,"BEAR")
        self.assertEqual(y.index.tolist(),f.index[3:5].tolist())
        self.assertEqual(y.qualifies.tolist(),[True,False])

    def test_missing_gate_feature_is_not_complement(self):
        f=self.fixture();f.iloc[0,f.columns.get_loc("ret5")]=np.nan
        with self.assertRaisesRegex(ValueError,"MISSING_DISCOVERY_GATE_INPUT"):
            daily_candidates(f,"BULL")

    def test_pending_labels_excluded_without_imputation(self):
        f=self.fixture();f.iloc[0,f.columns.get_loc("net_return")]=np.nan
        self.assertEqual(daily_candidates(f,"BULL").index.tolist(),f.index[1:2].tolist())


if __name__=="__main__":
    unittest.main()
