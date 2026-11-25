import unittest
import numpy as np
import pandas as pd
from temporal_calibration import historical_calibration_rows, prior_correct, calibrate, gate, metric


class CalibrationTests(unittest.TestCase):
    def test_maturity_boundary(self):
        f=pd.DataFrame({"year":[2023,2023,2024],"signal_date":pd.to_datetime(["2023-12-27","2023-12-28","2024-01-02"]),
            "exit_date":pd.to_datetime(["2023-12-29","2024-01-03","2024-01-05"])})
        self.assertEqual(historical_calibration_rows(f,2024).index.tolist(),[0])

    def test_class_prior_correction(self):
        np.testing.assert_allclose(prior_correct([.5,.5],[.2,.8]),[.2,.8])
        np.testing.assert_allclose(prior_correct([.2,.8],.5),[.2,.8])

    def test_insufficient_calibration_abstains(self):
        f=pd.DataFrame({"year":[2023],"signal_date":pd.to_datetime(["2023-12-01"]),
            "exit_date":pd.to_datetime(["2023-12-07"]),"win":[1],"raw":[.9]})
        self.assertIsNone(calibrate(f,2024)[0])

    def test_gates(self):
        f=pd.DataFrame({"spy_above200_lag":[1,0,0,1,0],"vix_lag":[35,45,46,36,0]})
        self.assertEqual(gate(f,"BULL").tolist(),[True,False,False,False,False])
        self.assertEqual(gate(f,"BEAR").tolist(),[False,True,False,False,False])

    def test_probability_and_same_date(self):
        f=pd.DataFrame({"signal_date":pd.to_datetime(["2025-01-02"]*2),"win":[0,1],"score":[.1,.9]})
        d=metric(f,"score",True)
        self.assertAlmostEqual(d["brier"],.01);self.assertEqual(d["auc"],1)
        self.assertEqual(d["same_date_auc"],1)

    def test_calibration_excludes_late_exits_and_current_year(self):
        days = pd.date_range("2023-01-01", periods=240, freq="D")
        f = pd.DataFrame({"year": 2023, "signal_date": days,
                          "exit_date": days + pd.Timedelta(days=4),
                          "raw": np.linspace(.15, .85, 240),
                          "win": np.arange(240) % 2})
        est, audit = calibrate(f, 2024)
        self.assertIsNotNone(est)
        self.assertEqual(audit["n"], 240)
        altered = pd.concat([f, pd.DataFrame({
            "year": [2023, 2024], "signal_date": pd.to_datetime(["2023-12-30", "2024-01-02"]),
            "exit_date": pd.to_datetime(["2024-01-05", "2024-01-08"]),
            "raw": [.99, .01], "win": [0, 1]})], ignore_index=True)
        new, new_audit = calibrate(altered, 2024)
        self.assertEqual(audit, new_audit)
        np.testing.assert_allclose(est.coef_, new.coef_, rtol=0, atol=0)
        np.testing.assert_allclose(est.intercept_, new.intercept_, rtol=0, atol=0)

    def test_invalid_probability_rejected(self):
        f = pd.DataFrame({"signal_date": pd.to_datetime(["2025-01-02"]*2),
                          "win": [0, 1], "score": [.1, 1.1]})
        with self.assertRaisesRegex(ValueError, "INVALID_PROBABILITY"):
            metric(f, "score", True)

    def test_unavailable_scores_report_empty_not_pass(self):
        f = pd.DataFrame({"signal_date": pd.to_datetime(["2025-01-02"]*2),
                          "win": [0, 1], "score": [np.nan, np.nan]})
        d = metric(f, "score", True)
        self.assertEqual(d["n"], 0)
        self.assertIsNone(d["auc"])
        self.assertNotIn("brier", d)


if __name__=="__main__":
    unittest.main()
