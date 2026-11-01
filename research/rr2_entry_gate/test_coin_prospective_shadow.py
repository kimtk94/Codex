"""Strict COIN prospective shadow sealing and smoke privacy contracts."""
import unittest
from datetime import date,datetime,timezone,timedelta
from types import SimpleNamespace
from unittest.mock import patch

from coin_prospective_shadow import (
    ORIGINAL_SHA,ResearchHold,canonical,sha,check_decision_clock,
    make_commitment,produce,
)

UTC=timezone.utc

class DummyExchange:
    def is_session(self,d):
        return str(d) not in ("2026-11-01","2026-11-07","2026-11-08")
    def session_close(self,d):
        return SimpleNamespace(to_pydatetime=lambda:datetime(
            2026,11,2,21,0,tzinfo=UTC))
    def session_open(self,d):
        return SimpleNamespace(to_pydatetime=lambda:datetime(
            2026,11,3,14,30,tzinfo=UTC))
    def next_session(self,d):
        return SimpleNamespace(date=lambda:date(2026,11,3))

class SmokeCalendar(DummyExchange):
    def next_session(self,d):
        return SimpleNamespace(date=lambda:date(2026,11,2))

DETERMINISTIC={
    "score":.531,"candidate":True,
    "model_digest":"a"*64,"input_bar_digest":"b"*64,
    "available_features_hex":{"rvol20":float(1.4).hex()},
}

class ProspectiveContracts(unittest.TestCase):
    def setUp(self):
        self.cal=DummyExchange()
        self.day=date(2026,11,2)

    def test_utc_2150_after_rth_before_next_open_passes(self):
        nxt=check_decision_clock(self.day,datetime(
            2026,11,2,21,50,tzinfo=UTC),self.cal)
        self.assertEqual(nxt,date(2026,11,3))

    def test_preclose_and_next_open_and_yesterday_rejected(self):
        for now in (datetime(2026,11,2,21,10,tzinfo=UTC),
                    datetime(2026,11,3,14,30,tzinfo=UTC),
                    datetime(2026,11,3,12,0,tzinfo=UTC)):
            with self.assertRaises(ResearchHold):
                check_decision_clock(self.day,now,self.cal)
        with self.assertRaisesRegex(ResearchHold,"PRE_FREEZE_NOT_OOS"):
            check_decision_clock(date(2026,10,30),
                datetime(2026,10,30,23,30,tzinfo=UTC),self.cal)
        with self.assertRaisesRegex(ResearchHold,"ASOF_NOT_NYSE_SESSION"):
            check_decision_clock(date(2026,11,1),
                datetime(2026,11,1,23,30,tzinfo=UTC),self.cal)

    def test_retrospective_never_oos_even_if_prediction_positive(self):
        with patch("coin_prospective_shadow.frozen_signal",return_value=DETERMINISTIC):
            public,private=produce(None,date(2026,10,30),datetime(
                2026,11,2,21,50,tzinfo=UTC),
                prospective=False,calendar=SmokeCalendar(),
                original_snapshot_sha=ORIGINAL_SHA)
        self.assertEqual(public["status"],"RETROSPECTIVE_SMOKE_NO_OOS_CREDIT")
        self.assertTrue(public["no_unseen_oos_claim_for_smoke"])
        self.assertEqual(public["live"],"HOLD")
        self.assertTrue(private["candidate"])
        self.assertNotIn("candidate",public)
        self.assertNotIn("signal_probability",public)

    def test_opaque_commitment_changes_if_model_or_probability_changes(self):
        a=make_commitment(self.day,date(2026,11,3),DETERMINISTIC)
        b=make_commitment(self.day,date(2026,11,3),
                          dict(DETERMINISTIC,score=.53))
        c=make_commitment(self.day,date(2026,11,3),
                          dict(DETERMINISTIC,candidate=False))
        self.assertEqual(len(a),64)
        self.assertNotEqual(a,b)
        self.assertNotEqual(a,c)
        self.assertEqual(a,make_commitment(self.day,date(2026,11,3),DETERMINISTIC))

    def test_public_signal_seal_is_non_directional(self):
        with patch("coin_prospective_shadow.frozen_signal",return_value=DETERMINISTIC):
            public,private=produce(None,self.day,datetime(
                2026,11,2,21,50,tzinfo=UTC),
                prospective=True,calendar=self.cal,
                original_snapshot_sha=ORIGINAL_SHA)
        self.assertEqual(public["status"],"SEALED_PRE_ENTRY_OOS_SHADOW")
        self.assertFalse(public["no_unseen_oos_claim_for_smoke"])
        self.assertNotIn("signal_probability",str(public))
        self.assertNotIn("candidate",str(public))
        self.assertEqual(private["signal_commitment_sha256"],
                         public["signal_commitment_sha256"])

    def test_unpinned_source_is_hard_hold(self):
        with self.assertRaisesRegex(ResearchHold,"ORIGINAL_SOURCE_SHA_MISMATCH"):
            produce(None,self.day,datetime(2026,11,2,21,50,tzinfo=UTC),
                    prospective=True,calendar=self.cal,
                    original_snapshot_sha="main")

if __name__=="__main__":
    unittest.main()
