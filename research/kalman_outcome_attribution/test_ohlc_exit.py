import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from ohlc_exit import path_from_ohlc, policy, net, excursion_groups


class ExactOHLCContracts(unittest.TestCase):
    def test_actual_entry_and_bar_extremes(self):
        idx=pd.bdate_range("2025-01-01",periods=5)
        bars=pd.DataFrame({"open":[100,100,94,96,97],"high":[102,102,98,101,103],
                           "low":[99,95,92,94,96],"close":[101,97,96,98,101]},index=idx)
        event=SimpleNamespace(signal_date=idx[0],entry_date=idx[1],exit_date=idx[-1],
                              gross_return=.01,net_return=.008)
        r=path_from_ohlc(bars,event)
        self.assertAlmostEqual(r["mfe"],.03)
        self.assertAlmostEqual(r["mae"],-.08)
        self.assertAlmostEqual(r["open2"],-.06)
        self.assertAlmostEqual(r["close1"],-.03)
        self.assertAlmostEqual(r["close4"],.01)
        with self.assertRaisesRegex(ValueError,"HOLD_WINDOW_MISMATCH"):
            path_from_ohlc(bars.drop(idx[2]),event)
        wrong=bars.copy();wrong.loc[idx[2],"high"]=90
        with self.assertRaisesRegex(ValueError,"INCONSISTENT_OHLC"):
            path_from_ohlc(wrong,event)
        event.gross_return=.99
        with self.assertRaisesRegex(ValueError,"ORIGINAL_LABEL_MISMATCH"):
            path_from_ohlc(bars,event)

    def test_next_open_gap_and_no_same_close_exit(self):
        frame=pd.DataFrame({"close1":[-.03,-.03,.01],"open2":[-.06,.02,-.1],
                            "close4":[.01,-.08,.02],"year":[2025,2025,2026]})
        r=policy(frame,1,-.02,20,False)
        self.assertEqual(r["trigger_count"],2)
        self.assertEqual(r["severe_original"],1)
        self.assertEqual(r["severe_alternate"],1)
        self.assertEqual(r["winners_to_nonwins"],1)
        self.assertEqual(r["nonwins_to_winners"],1)
        self.assertAlmostEqual(r["mean_alternate"],np.mean([-.062,.018,.018]))
        self.assertFalse(r["portfolio_resimulated"])
        changed=frame.copy();changed.close4=[.9,.8,.7]
        self.assertEqual(policy(changed,1,-.02,20,False)["trigger_count"],2)
        with self.assertRaisesRegex(ValueError,"UNREGISTERED_CHECKPOINT"):
            policy(frame,1,-.03,20,False)

    def test_cash_ledger_cost_basis(self):
        f=pd.DataFrame({"close1":[-.03],"open2":[-.06],"close4":[.01],
                        "year":[2025],"mfe":[.04],"mae":[-.08]})
        f["realized_return"]=net(f.close4,20,True)
        r=policy(f,1,-.02,20,True)
        self.assertAlmostEqual(r["mean_alternate"],.94*.999/1.001-1)
        self.assertEqual(excursion_groups(f,20,True)["WIN"]["n"],1)
        f["realized_return"]=.99
        with self.assertRaisesRegex(ValueError,"LEDGER_RETURN_MISMATCH"):
            policy(f,1,-.02,20,True)


if __name__=="__main__":
    unittest.main()
