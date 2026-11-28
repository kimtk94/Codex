import copy
import unittest
from cache_rehearsal import PINS, select
from evidence_review import VERIFIED

class CacheTests(unittest.TestCase):
    def setUp(self):
        self.q,self.l = PINS
        self.prior = {"sources":{sid:{"state":VERIFIED,"sha256":pin,
                    "independent_anchors_verified":True} for sid,pin in PINS.items()}}
        self.now = copy.deepcopy(self.prior)
        self.now["sources"][self.q] = {"state":"TRANSIENT_UNAVAILABLE_HOLD",
             "fetch_status":"HTTP_403_SOURCE_HOLD","sha256":None}
    def test_known_outage(self):
        self.assertEqual(select(self.now,self.prior),{self.q:"PRIOR_HTTP_403",self.l:"CURRENT"})
    def test_missing_prior_pair(self):
        self.prior["sources"][self.l]["state"]="SOURCE_MISSING_HOLD"
        with self.assertRaisesRegex(ValueError,"PRIOR_PAIR_NOT_VERIFIED"):
            select(self.now,self.prior)
    def test_prior_anchor_false(self):
        self.prior["sources"][self.q]["independent_anchors_verified"]=False
        with self.assertRaisesRegex(ValueError,"PRIOR_SOURCE_NOT_PINNED"):
            select(self.now,self.prior)
    def test_prior_pin_wrong(self):
        self.prior["sources"][self.q]["sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"PRIOR_SOURCE_NOT_PINNED"):
            select(self.now,self.prior)
    def test_current_changed(self):
        self.now["sources"][self.l]["sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"SOURCE_REUSE_DENIED"):
            select(self.now,self.prior)
    def test_other_status_denied(self):
        self.now["sources"][self.q]["fetch_status"]="HTTP_429_SOURCE_HOLD"
        with self.assertRaisesRegex(ValueError,"SOURCE_REUSE_DENIED"):
            select(self.now,self.prior)
    def test_tamper_denied(self):
        self.now["sources"][self.q]["state"]="SOURCE_BYTES_MISMATCH_HOLD"
        with self.assertRaisesRegex(ValueError,"SOURCE_REUSE_DENIED"):
            select(self.now,self.prior)
    def test_no_outage(self):
        self.assertEqual(select(self.prior,self.prior),{sid:"CURRENT" for sid in PINS})

if __name__ == "__main__":
    unittest.main()
