import unittest
from diagnose_one_to_one_quote_parent_hold_private import classify_three_passes


def source():
    return {"quote_id":"a0P000000000001AAA",
            "opportunity_id":"006000000000001AAA"}


def outcome(count=1,ok=True):
    c=source()
    return {"status":"QUOTE_NATIVE_PARENT_MATCH_REVIEW_COMPLETE" if ok else "HOLD_RELATED_COUNT_NOT_EXACTLY_ONE",
            "quote_id_verified":bool(ok),"parent_verified":bool(ok),
            "quotation_id_private":c["quote_id"] if ok else None,
            "opportunity_id_private":c["opportunity_id"] if ok else None,
            "observed_related_quote_count":count}


class HoldDiagnosticTests(unittest.TestCase):
    def test_three_independent_pass_requires_manual_review_not_promotion(self):
        self.assertEqual(classify_three_passes(source(),[outcome(),outcome(),outcome()]),
                         "REVIEW_RECOVERED_3_OF_3_NO_AUTO_PROMOTION")

    def test_stable_two_related_is_hold(self):
        self.assertEqual(classify_three_passes(source(),[outcome(2,False) for _ in range(3)]),
                         "HOLD_RELATED_COUNT_STABLE_NOT_ONE")

    def test_stable_zero_related_is_hold(self):
        self.assertEqual(classify_three_passes(source(),[outcome(0,False) for _ in range(3)]),
                         "HOLD_RELATED_COUNT_STABLE_NOT_ONE")

    def test_one_success_two_fail_still_hold(self):
        self.assertEqual(classify_three_passes(source(),[outcome(),outcome(None,False),outcome()]),
                         "HOLD_INCONSISTENT_OR_INCOMPLETE_READBACK")

    def test_only_two_checks_cannot_certify(self):
        self.assertEqual(classify_three_passes(source(),[outcome(),outcome()]),
                         "HOLD_NOT_THREE_INDEPENDENT_READBACKS")

    def test_mismatched_quote_id_never_promotes(self):
        bad=outcome()
        bad["quotation_id_private"]="a0P000000000002AAA"
        self.assertEqual(classify_three_passes(source(),[outcome(),bad,outcome()]),
                         "HOLD_NATIVE_ID_CONFLICT")


if __name__=="__main__":
    unittest.main()
