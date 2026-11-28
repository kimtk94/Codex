import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from close_path import close_path,add_net_path,checkpoint,group_summary


class ClosePathContracts(unittest.TestCase):
    def test_four_closes_and_adjacent_signal_required(self):
        dates=pd.bdate_range("2025-01-01",periods=5)
        close=pd.Series([100,97,95,98,96],index=dates)
        event=SimpleNamespace(signal_date=dates[0],entry_date=dates[1],
                              exit_date=dates[4],gross_return=-.04)
        np.testing.assert_allclose(close_path(close,event),[-.03,-.05,-.02,-.04])
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_FOUR_SESSION_WINDOW"):
            close_path(close.drop(dates[2]),event)
        event.signal_date=dates[1]
        with self.assertRaisesRegex(ValueError,"SIGNAL_ENTRY_SESSION_MISMATCH"):
            close_path(close,event)

    def test_cost_basis_and_recovery_distinguished(self):
        x=pd.DataFrame({"signal_date":pd.to_datetime(["2025-01-01","2025-01-02"]),
                        "g1":[-.03,-.03],"g2":[-.01,-.05],
                        "g3":[.01,-.06],"g4":[.03,-.07]})
        x["net_return"]=x.g4-.002
        x["realized_return"]=(1+x.g4)*.999/1.001-1
        for filled in (True,False):
            r=add_net_path(x,filled)
            self.assertEqual(r.group.tolist(),["WIN","SEVERE_LOSS"])
            s=checkpoint(r,1,-.02)
            self.assertEqual(s["flagged"]["n"],2)
            self.assertEqual(s["flagged"]["severe"],1)
            self.assertEqual(s["flagged"]["wins"],1)
            self.assertAlmostEqual(s["flagged"]["mean_remaining_gross_close_to_close"],
                                   ((1.03/.97-1)+(.93/.97-1))/2)
            self.assertTrue(s["not_an_executable_exit"])
            self.assertAlmostEqual(group_summary(r.iloc[:1])["median_close_sampled_mae_gross"],-.03)

    def test_invalid_net_label_rejected(self):
        x=pd.DataFrame({"g1":[0.],"g2":[0.],"g3":[0.],"g4":[.02],"net_return":[.9]})
        with self.assertRaisesRegex(ValueError,"NET_RETURN_MISMATCH"):
            add_net_path(x,False)


if __name__=="__main__":
    unittest.main()
