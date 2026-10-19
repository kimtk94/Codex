#!/usr/bin/env python3
"""Test historical analysis wrapper against in-memory-like temporary sqlite fixtures."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
P=ROOT/"experiments/rea/grid_v3_historical_sensitivity.py"
spec=importlib.util.spec_from_file_location("grid_hist",P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class TestHistoricalSensitivity(unittest.TestCase):
    def test_strict_vs_inclusive_boundary_and_fee(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"candles.sqlite3"
            con=sqlite3.connect(db)
            con.execute("CREATE TABLE candles(ts_utc TEXT,high REAL,low REAL,close REAL)")
            con.executemany("INSERT INTO candles VALUES (?,?,?,?)",[
                ("2025-01-01T00:00:00+00:00",2e6,2e6,2e6),
                ("2025-01-01T00:01:00+00:00",2e6,1980000,2e6)])
            con.commit();con.close()
            output=m.evaluate(str(db),[2025],[.01],[20],[0,.001],1e6)
            self.assertEqual(len(output["results"]),4)
            strict=[r for r in output["results"] if r["fill_model"]=="strict"]
            inclusive=[r for r in output["results"] if r["fill_model"]=="inclusive_touch"]
            self.assertTrue(all(r["fills"]==0 for r in strict))
            self.assertTrue(all(r["fills"]>=1 for r in inclusive))
            self.assertEqual(output["data"]["bars"],2)

if __name__=="__main__":unittest.main()
