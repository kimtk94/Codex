"""Synthetic 48-contact cohort accounting, no real customer data."""
import unittest
from audit_korean_contact_cohort_private import summarize_cohort


def rows(n):
    return [{"contact_id":f"003{i:012d}AAA"} for i in range(n)]


class CohortAuditTests(unittest.TestCase):
    def test_all_48_partition(self):
        base=rows(48)
        approved=[{"contact_id":r["contact_id"]} for r in base[:15]]
        ledger=[{"contact_id":r["contact_id"],"status":"PASS_ALL_IDENTITY_CHECKS"}
                for r in base[10:15]] + [
                {"contact_id":r["contact_id"],"status":"HOLD_CONTACT_DETAIL_DISPLAY"}
                for r in base[15:20]]
        out=summarize_cohort(base,approved,ledger)
        self.assertEqual(out["cohort_count"],48)
        self.assertEqual(out["verified"],15)
        self.assertEqual(out["hold"],5)
        self.assertEqual(out["untested"],28)
        self.assertFalse(out["save_allowed"])

    def test_legacy_unlogged_hold_not_counted_as_unchecked(self):
        base=rows(12)
        out=summarize_cohort(base,[{"contact_id":r["contact_id"]} for r in base[:7]],[],legacy_first=10)
        self.assertEqual(out["hold_legacy"],3)
        self.assertEqual(out["untested"],2)

    def test_repeat_deterministic(self):
        v=[summarize_cohort(rows(10),[],[],legacy_first=10) for _ in range(3)]
        self.assertEqual(v[0],v[1])
        self.assertEqual(v[1],v[2])

    def test_duplicate_contact_id_fails(self):
        with self.assertRaises(ValueError):
            summarize_cohort([rows(1)[0],rows(1)[0]],[],[])

    def test_bad_input_fails(self):
        with self.assertRaises(ValueError):
            summarize_cohort({},[],[])

    def test_verified_external_id_is_flagged(self):
        r=summarize_cohort(rows(2),[{"contact_id":"003999999999999AAA"}],[],legacy_first=0)
        self.assertEqual(r["verified_outside_cohort"],1)


if __name__=="__main__":
    unittest.main()
