import copy
import unittest
from origin_sidecar import make_sidecar, EVENTS, FLAGS
from cache_rehearsal import CURRENT_PIN, PRIOR_PIN, PINS
from evidence_review import TARGETS

class SidecarTests(unittest.TestCase):
    def setUp(self):
        self.gap = {"version":"daily20-issuer-ca-gap-audit-v1","status":"ISSUER_DISTRIBUTIONS_2_EVENTS_HOLD",
                    "research_only":True,"production_writes":False,"strategy_promoted":False,
                    "issuer_payments_certified":0,"source_finality_verified":0,
                    "unarchived_research_leads_are_certified":False,"both_archived_sources_verified":False,"events":[]}
        self.result = {"status":"ISOLATED_CACHE_REHEARSAL_PASS","research_only":True,"production_writes":False,
                       "cache_reuse_authorized":False,"strategy_promoted":False,"issuer_payments_certified":0,
                       "source_finality_verified":0,"evidence":{}}
        for sid,(claim,url,_,_) in TARGETS.items():
            symbol, day=claim.split("|")
            current=symbol=="QLD"
            self.gap["events"].append({"symbol":symbol,"ex_date":day,"source_id":sid,"source_url":url,
                "source_body_sha256":PINS[sid] if current else None,
                "archived_evidence_status":"SOURCE_BYTES_AND_ANCHORS_VERIFIED_PAYMENT_UNCERTIFIED" if current else "SOURCE_NOT_FETCHED_HOLD",
                "research_hold":True,**{f:False for f in FLAGS}})
            self.result["evidence"][sid]={"selection":"CURRENT" if current else "PRIOR_HTTP_403",
                                         "source_sha256":PINS[sid],"archive_sha256":CURRENT_PIN if current else PRIOR_PIN}
    def test_origin_counts_and_no_mutation(self):
        before=copy.deepcopy(self.gap)
        side=make_sidecar(self.gap,"abc",self.result)
        self.assertEqual((side["current_evidence_count"],side["historical_context_count"]),(1,1))
        self.assertFalse(side["baseline_both_archived_sources_verified"])
        self.assertFalse(side["cache_reuse_authorized"])
        self.assertEqual(side["issuer_payments_certified"],0)
        self.assertEqual(self.gap,before)
    def test_no_promoted_baseline(self):
        self.gap["strategy_promoted"]=True
        with self.assertRaisesRegex(ValueError,"BASELINE_GOVERNANCE"): make_sidecar(self.gap,"abc",self.result)
    def test_no_promoted_rehearsal(self):
        self.result["cache_reuse_authorized"]=True
        with self.assertRaisesRegex(ValueError,"REHEARSAL_GOVERNANCE"): make_sidecar(self.gap,"abc",self.result)
    def test_no_duplicate_event(self):
        self.gap["events"][1]=self.gap["events"][0]
        with self.assertRaisesRegex(ValueError,"BASELINE_EVENT_SET"): make_sidecar(self.gap,"abc",self.result)
    def test_no_overwrite_current(self):
        self.gap["events"][0]["source_body_sha256"]="a"*64
        with self.assertRaisesRegex(ValueError,"PRIOR_MUST_NOT_OVERRIDE"): make_sidecar(self.gap,"abc",self.result)
    def test_no_certified_event(self):
        self.gap["events"][0]["actual_payment_certified"]=True
        with self.assertRaisesRegex(ValueError,"BASELINE_EVENT_GOVERNANCE"): make_sidecar(self.gap,"abc",self.result)
    def test_current_pin_mismatch(self):
        self.gap["events"][1]["source_body_sha256"]="a"*64
        with self.assertRaisesRegex(ValueError,"CURRENT_EVIDENCE_MISMATCH"): make_sidecar(self.gap,"abc",self.result)
    def test_unknown_origin(self):
        self.result["evidence"][next(iter(TARGETS))]["selection"]="OTHER"
        with self.assertRaisesRegex(ValueError,"UNKNOWN_ORIGIN"): make_sidecar(self.gap,"abc",self.result)

if __name__=="__main__": unittest.main()
