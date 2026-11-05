import unittest
from retry_transient_contact_holds_private import select_transient_holds


def row(i):
    return {"contact_id":f"003{i:012d}AAA","opportunity_id":f"006{i:012d}AAA"}


class RetryTransientOnlyTests(unittest.TestCase):
    def test_timeout_only_is_eligible(self):
        candidates=[row(i) for i in range(4)]
        attempts=[{"contact_id":row(0)["contact_id"],"status":"HOLD_TimeoutError"},
                  {"contact_id":row(1)["contact_id"],"status":"HOLD_CONTACT_DETAIL_DISPLAY"},
                  {"contact_id":row(2)["contact_id"],"status":"HOLD_CONTACT_EMAIL_IDENTITY"},
                  {"contact_id":row(3)["contact_id"],"status":"HOLD_ACCOUNT_ID_DIFFERENT"}]
        self.assertEqual(select_transient_holds(candidates,[],attempts),[row(0)])

    def test_approved_contact_not_retried(self):
        attempts=[{"contact_id":row(0)["contact_id"],"status":"HOLD_TimeoutError"}]
        self.assertEqual(select_transient_holds([row(0)],[{"contact_id":row(0)["contact_id"]}],attempts),[])

    def test_latest_status_takes_precedence_over_old_hold(self):
        attempts=[{"contact_id":row(0)["contact_id"],"status":"HOLD_TimeoutError"},
                  {"contact_id":row(0)["contact_id"],"status":"HOLD_CONTACT_DETAIL_DISPLAY"}]
        self.assertEqual(select_transient_holds([row(0)],[],attempts),[])

    def test_repeated_same_candidate_deduped_by_source_cohort(self):
        attempts=[{"contact_id":row(0)["contact_id"],"status":"HOLD_TimeoutError"}]
        self.assertEqual(select_transient_holds([row(0)],[],attempts),[row(0)])

    def test_unknown_reason_fails_closed(self):
        attempts=[{"contact_id":row(0)["contact_id"],"status":"HOLD_SUSPICIOUS"}]
        self.assertEqual(select_transient_holds([row(0)],[],attempts),[])

    def test_three_round_deterministic_no_implicit_retry_of_mismatch(self):
        c=[row(0),row(1)]
        a=[{"contact_id":row(0)["contact_id"],"status":"HOLD_TimeoutError"},
           {"contact_id":row(1)["contact_id"],"status":"HOLD_ACCOUNT_ID_DIFFERENT"}]
        s=[select_transient_holds(c,[],a) for _ in range(3)]
        self.assertEqual(s[0],s[1])
        self.assertEqual(s[1],s[2])
        self.assertEqual(s[0],[row(0)])

    def test_invalid_limit(self):
        with self.assertRaises(ValueError):
            select_transient_holds([],[],[],limit=9)


if __name__=="__main__":
    unittest.main()
