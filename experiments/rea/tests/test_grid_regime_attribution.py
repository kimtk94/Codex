import datetime as dt
import importlib.util
import sqlite3
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=ROOT/"experiments/rea/grid_regime_attribution.py"
spec=importlib.util.spec_from_file_location("attribution",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
SRC=(ROOT/"research/upbit_eth/grid_event_v3.py").read_text()
KST=dt.timezone(dt.timedelta(hours=9))
def simulate(policy, rows, state):
    c=sqlite3.connect(":memory:")
    c.execute("CREATE TABLE candles(ts_utc TEXT,high REAL,low REAL,close REAL)")
    c.executemany("INSERT INTO candles VALUES (?,?,?,?)",rows)
    d={dt.date(2025,1,1):state}
    r=m.simulate(SRC,c,2025,.01,20,1e6,.001,d,KST,policy)
    c.close()
    return r
def bar(minute,high=2e6,low=2e6,close=2e6):
    return (f"2024-12-31T15:{minute:02}:00+00:00",high,low,close)
class TestRegimeAttribution(unittest.TestCase):
    def test_all_arms_flat(self):
        rows=[bar(0),bar(1)]
        results=[simulate(policy,rows,"DOWN") for policy in m.POLICIES]
        self.assertTrue(all(r["fills"]==0 for r in results))
        self.assertTrue(all(r.get("policy_violations",0)==0 for r in results))
    def test_exposure_metrics_bounded(self):
        rows=[bar(0),bar(1),bar(2)]
        for policy in m.POLICIES:
            r=simulate(policy,rows,"DOWN")
            self.assertGreater(r["measured_bars"],0)
            self.assertGreaterEqual(r["exposure_mean_pct"],0)
            self.assertLessEqual(r["exposure_max_pct"],100)
            if policy!="baseline":
                self.assertEqual(r["down_bars"],r["measured_bars"])

    def test_inhibit_gap_no_reseed_buys(self):
        rows=[bar(0),bar(8,high=3e6,low=1e6)]
        r=simulate("inhibit_new_buys",rows,"DOWN")
        self.assertEqual(r["gap_resets"],1)
        self.assertEqual(r["gap_buy_violations"],0)

    def test_baseline_matches_original(self):
        rows=[bar(0),bar(1,low=1979500),bar(2)]
        a=simulate("baseline",rows,"UP")
        b=simulate("inhibit_new_buys",rows,"UP")
        self.assertEqual(a["fills"],b["fills"])
        self.assertEqual(a["return_pct"],b["return_pct"])
    def test_gap_cancel_policy(self):
        rows=[bar(0),bar(8,high=3e6,low=1e6)]
        for arm in ("cancel_resting_buys","reseed_on_up"):
            r=simulate(arm,rows,"DOWN")
            self.assertEqual(r["gap_resets"],1)
            self.assertEqual(r["policy_violations"],0)
            self.assertEqual(r["gap_buy_violations"],0)
if __name__=="__main__":unittest.main()
