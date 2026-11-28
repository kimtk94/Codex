import unittest
import numpy as np
import pandas as pd

from adjustment_basis_audit import compare_frames
from backfill_queue import PRICE_KEYS


def frames():
    ts = pd.date_range("2026-09-01", periods=15, freq="B", tz="UTC")
    a = pd.DataFrame({"timestamp": ts, "is_adjusted": False,
                      "open": 100., "high": 102., "low": 99., "close": 101.})
    b = a.copy()
    b["is_adjusted"] = True
    return a, b


class BasisAuditTests(unittest.TestCase):
    def test_equal_values_do_not_clear_basis_mismatch(self):
        a,b=frames()
        r=compare_frames(a,b,"yf_gld")
        self.assertEqual(r["status"],"EQUAL_VALUES_DIFFERENT_BASIS_HOLD")
        self.assertEqual(r["uniform_factor_sessions"],15)
        self.assertEqual(r["approved_backfill_rows"],0)

    def test_uniform_factor_change_not_issuer_evidence(self):
        a,b=frames()
        b.loc[:6,list(PRICE_KEYS)] *= .985
        b.loc[7:,list(PRICE_KEYS)] *= .995
        r=compare_frames(a,b,"yf_hyg")
        self.assertEqual(r["status"],"MULTIPLICATIVE_PATTERN_UNCERTIFIED_HOLD")
        self.assertEqual(r["uniform_factor_sessions"],15)
        self.assertEqual(len(r["factor_step_candidates"]),1)
        self.assertFalse(r["issuer_factor_verified"])
        self.assertFalse(r["pit_approved"])

    def test_nonuniform_ohlc_difference(self):
        a,b=frames()
        b.loc[4,"open"] *= .99
        r=compare_frames(a,b,"yf_qqq")
        self.assertEqual(r["status"],"NONUNIFORM_OHLC_DIFFERENCE_HOLD")
        self.assertEqual(r["nonuniform_valid_sessions"],1)

    def test_invalid_overlap_not_uniform(self):
        a,b=frames()
        b.loc[1,"close"]=np.inf
        b.loc[2,"low"]=0
        r=compare_frames(a,b,"yf_tlt")
        self.assertEqual(r["invalid_sessions"],2)
        self.assertEqual(r["status"],"INVALID_OVERLAP_HOLD")

    def test_same_flag_does_not_approve_price(self):
        a,b=frames()
        b["is_adjusted"]=False
        r=compare_frames(a,b,"yf_vix")
        self.assertEqual(r["status"],"SAME_FLAG_EQUAL_OVERLAP_UNCERTIFIED_HOLD")
        self.assertFalse(r["official_close_verified"])
        b.loc[:,list(PRICE_KEYS)] *= .99
        self.assertEqual(compare_frames(a,b,"yf_vix")["status"],"SAME_FLAG_REVISED_VALUES_HOLD")

    def test_invalid_flag_and_short_overlap_fail(self):
        a,b=frames()
        b["is_adjusted"]="False"
        with self.assertRaisesRegex(ValueError,"FLAG_INVALID"):
            compare_frames(a,b,"yf_spy")
        a,b=frames()
        with self.assertRaisesRegex(ValueError,"OVERLAP_INSUFFICIENT"):
            compare_frames(a.iloc[:11],b,"yf_spy")
