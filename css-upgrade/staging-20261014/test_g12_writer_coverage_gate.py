"""No-I/O synthetic G12 writer source coverage gate regression."""
import copy
import unittest
from g12_writer_coverage_gate import analyze, fixture, SITES, baseline_digest

class GateTests(unittest.TestCase):
    def test_exact_pinned_inventory_is_still_blocked(self):
        outcome=analyze(fixture())
        self.assertEqual(outcome["candidate_count"],28)
        self.assertEqual(outcome["counts_by_risk"],
                         {"APPEND":1,"STRUCTURAL":8,"UNKNOWN":19})
        self.assertEqual(outcome["decision"],
                         "BLOCKED_MISSING_WRITER_ISOLATION_EVIDENCE")
        self.assertFalse(outcome["release_authorized"])

    def test_changed_source_blocks(self):
        data=fixture()
        data["source_sha256"]="wrong"
        self.assertEqual(analyze(data)["decision"],"BLOCKED_SOURCE_FINGERPRINT")

    def test_missing_callsite_blocks(self):
        data=fixture()
        data["sites"].pop()
        self.assertEqual(analyze(data)["decision"],"BLOCKED_CALL_SITES_CHANGED")

    def test_duplicate_callsite_blocks(self):
        data=fixture()
        data["sites"].append(copy.deepcopy(data["sites"][0]))
        self.assertEqual(analyze(data)["decision"],"BLOCKED_DUPLICATE_CALL_SITES")

    def test_new_unreviewed_callsite_blocks(self):
        data=fixture()
        data["sites"][0]["line"]=99999
        self.assertEqual(analyze(data)["decision"],"BLOCKED_CALL_SITES_CHANGED")

    def test_reordered_sites_blocks(self):
        data=fixture()
        data["sites"]=list(reversed(data["sites"]))
        self.assertEqual(analyze(data)["decision"],"BLOCKED_CALL_SITES_CHANGED")

    def test_truncated_inventory_blocks(self):
        data=fixture()
        data["sites_truncated"]=True
        self.assertEqual(analyze(data)["decision"],"BLOCKED_INCOMPLETE_INVENTORY")

    def test_unknown_risk_code_blocks(self):
        data=fixture()
        data["sites"][0]["risk"]="REVIEWED_SAFE"
        self.assertEqual(analyze(data)["decision"],"BLOCKED_MALFORMED_INVENTORY")

    def test_fabricated_safe_flag_is_not_accepted(self):
        data=fixture()
        data["safe"]=True
        data["production_deploy_authorized"]=True
        out=analyze(data)
        self.assertFalse(out["release_authorized"])
        self.assertEqual(out["confirmed_safe_sites"],0)

    def test_empty_and_bad_schema_block(self):
        self.assertEqual(analyze({})["decision"],"BLOCKED_SOURCE_FINGERPRINT")
        self.assertEqual(analyze(None)["decision"],"BLOCKED_SOURCE_FINGERPRINT")

    def test_unknown_candidate_count_blocks(self):
        data=fixture()
        data["candidate_count"]=None
        self.assertEqual(analyze(data)["decision"],"BLOCKED_CALL_SITES_CHANGED")

    def test_baseline_integrity(self):
        self.assertEqual(len(SITES),len(set(SITES)))
        self.assertEqual(len(baseline_digest()),64)

if __name__=="__main__":
    unittest.main()
