"""Synthetic-only QQ pre-cursor replay test contracts; no network or writes."""
import json
import unittest
from automation.css_mail.qq_precursor_replay_readiness import classify_precursor,summarize_replay,REASONS

def target(n="209126000001",amount="1000",**extra):
    x={"category":"PRE_CURSOR_MISSING","number":n,
       "extract":{"invoice_number":n,"amount_krw":amount},"qq":None,"css":None}
    x.update(extra)
    return x

def proof(**kw):
    p={"search_matched":True,"ingest_present":True,"ingest_epoch_matched":True,
       "header_verified":True,"mime_verified":True}
    p.update(kw)
    return p

class ReplayTests(unittest.TestCase):
    def test_seven_valid_sources_still_do_not_authorize_writes(self):
        ts=[target(n="209126%06d"%i) for i in range(1,8)]
        result=summarize_replay(ts,{t["number"]:proof() for t in ts})
        self.assertEqual(result["replay_precursor_target_count"],7)
        self.assertEqual(result["replay_source_proved_hold"],7)
        for name in ("stage_writes_approved","canonical_writes_approved",
                     "official_issue_date_proved","persisted_receipts",
                     "current_sink_readback_proved"):
            self.assertEqual(result["replay_"+name],0)
        self.assertNotIn("209126",json.dumps(result))
    def test_existing_sinks_and_amount_conflicts(self):
        self.assertEqual(classify_precursor(target(qq={"amount_krw":"1000"}),proof()),
                         "EXISTING_SINK_RECORD")
        self.assertEqual(classify_precursor(target(css={"amount_krw":"1001"}),proof()),
                         "AMOUNT_CONFLICT")
        self.assertEqual(classify_precursor(target(css={"amount_krw":""}),proof()),
                         "EXISTING_SINK_RECORD")
    def test_all_unproved_cases_are_holds(self):
        for field,reason in (
            ("search_matched","ORIGINAL_SEARCH_ABSENT"),
            ("ingest_present","INGEST_EVIDENCE_MISSING"),
            ("ingest_epoch_matched","INGEST_UID_OR_EPOCH_CONFLICT"),
            ("header_verified","ORIGINAL_HEADER_UNVERIFIED"),
            ("mime_verified","MIME_IDENTITY_OR_AMOUNT_UNVERIFIED")):
            self.assertEqual(classify_precursor(target(),proof(**{field:False})),reason)
    def test_invalid_amount_key_missing_proofs_and_duplicates(self):
        for t in (target(amount="0"),target(amount="1,000"),target(n="PRIVATE")):
            self.assertEqual(classify_precursor(t,proof()),"INVALID_EXTRACT_ID_OR_AMOUNT")
        t=target()
        with self.assertRaisesRegex(ValueError,"REPLAY_PROOF_COVERAGE_INCOMPLETE"):
            summarize_replay([t],{})
        with self.assertRaisesRegex(ValueError,"REPLAY_DUPLICATE_OR_UNBOUNDED_TARGET"):
            summarize_replay([t,t],{t["number"]:proof()})
    def test_non_pre_cursor_does_not_become_replay(self):
        t=target()
        other=target(n="209126000002",category="POST_CURSOR_PENDING")
        data=summarize_replay([t,other],{t["number"]:proof()})
        self.assertEqual(data["replay_precursor_target_count"],1)
        self.assertEqual(sum(data["replay_reason_"+r.lower()] for r in REASONS),1)
        self.assertNotIn("209126",json.dumps(data))
if __name__=="__main__":
    unittest.main()
