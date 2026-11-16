"""Synthetic-only native 2026 Salesforce CreatedDate UTC ↔ QQ KST guard."""
import unittest
from quote_2026_createddate_kst_guard import verify_createddate_utc_kst


class NativeCreatedDateKstTests(unittest.TestCase):
    def test_late_utc_day_exactly_matches_qq_next_calendar_day_in_kst(self):
        q="QID-2026-08-18-123456"
        result=verify_createddate_utc_kst(q,"2026-08-18","2026-08-19",
                                          "2026-08-18T23:55:19.000Z")
        self.assertEqual(result["status"],"PASS_NATIVE_CREATED_DATE_UTC_KST")
        self.assertEqual(result["crm_writes"],0)
        self.assertIs(result["price_auto_apply"],False)

    def test_only_true_native_timestamp_allows_day_shift(self):
        q="QID-2026-03-29-123456"
        with self.assertRaisesRegex(ValueError,"NATIVE_UTC_TIMESTAMP_MISSING"):
            verify_createddate_utc_kst(q,"2026-03-29","2026-03-30","")
        with self.assertRaisesRegex(ValueError,"NATIVE_UTC_TIMESTAMP_MISSING"):
            verify_createddate_utc_kst(q,"2026-03-29","2026-03-30",
                                          "2026-03-29T22:36:46+00:00")
        with self.assertRaisesRegex(ValueError,"QQ_CREATED_DATE_NOT_KST"):
            verify_createddate_utc_kst(q,"2026-03-29","2026-03-30",
                                          "2026-03-29T14:55:19.000Z")

    def test_does_not_edit_qid_date_or_tolerate_wrong_qq_date(self):
        with self.assertRaisesRegex(ValueError,"QUOTE_QID_SOURCE_DAY_UNVERIFIED"):
            verify_createddate_utc_kst("QID-2026-08-18-123456","2026-08-19",
                                          "2026-08-19","2026-08-18T23:55:19.000Z")
        with self.assertRaisesRegex(ValueError,"QQ_CREATED_DATE_NOT_KST"):
            verify_createddate_utc_kst("QID-2026-08-18-123456","2026-08-18",
                                          "2026-08-20","2026-08-18T23:55:19.000Z")
        with self.assertRaisesRegex(ValueError,"NOT_A_ONE_DAY"):
            verify_createddate_utc_kst("QID-2026-08-18-123456","2026-08-18",
                                          "2026-08-18","2026-08-18T03:55:19.000Z")

    def test_native_timestamp_utc_day_mismatch_blocks(self):
        with self.assertRaisesRegex(ValueError,"NATIVE_CREATED_DATE_DOES_NOT_MATCH_QID"):
            verify_createddate_utc_kst("QID-2026-08-18-123456","2026-08-18",
                                          "2026-08-19","2026-08-19T00:20:19.000Z")

    def test_no_guess_from_invalid_data(self):
        with self.assertRaisesRegex(ValueError,"CREATED_DATE_NOT_ISO"):
            verify_createddate_utc_kst("QID-2026-08-18-123456","2026-08-18",
                                          "not a date","2026-08-18T23:55:19.000Z")
        with self.assertRaisesRegex(ValueError,"NATIVE_UTC_TIMESTAMP_MISSING"):
            verify_createddate_utc_kst("QID-2026-08-18-123456","2026-08-18",
                                          "2026-08-19","2026-08-18T99:55:19.000+09:00")


if __name__=="__main__":
    unittest.main()
