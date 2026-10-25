import unittest
from nba_preserve_decisions import merge_decisions


class PreserveDecisionsTests(unittest.TestCase):
    def test_decisions_follow_id_not_row(self):
        previous = [
            {"Source": "CSS", "Record ID": "ACT-1", "완료 체크": "TRUE"},
            {"Source": "LEAD", "Record ID": "Lead-2", "완료 체크": "FALSE"},
        ]
        incoming = [
            {"Source": "LEAD", "Record ID": "Lead-2", "완료 체크": "FALSE"},
            {"Source": "CSS", "Record ID": "ACT-1", "완료 체크": "FALSE"},
            {"Source": "CSS", "Record ID": "ACT-3", "완료 체크": ""},
        ]
        merged, audit = merge_decisions(previous, incoming)
        self.assertEqual([r["완료 체크"] for r in merged], ["FALSE", "TRUE", "FALSE"])
        self.assertEqual(audit["preserved"], 1)

    def test_absent_completed_item_tracked(self):
        merged, audit = merge_decisions(
            [{"Source": "CSS", "Record ID": "old", "완료 체크": "TRUE"}],
            [{"Source": "CSS", "Record ID": "new", "완료 체크": "FALSE"}],
        )
        self.assertEqual(merged[0]["완료 체크"], "FALSE")
        self.assertEqual(audit["completed_not_in_new_snapshot"], 1)

    def test_duplicate_identifier_rejected(self):
        with self.assertRaises(ValueError):
            merge_decisions([], [
                {"Source": "CSS", "Record ID": "a"},
                {"Source": "css", "Record ID": "A"},
            ])

    def test_same_id_different_source(self):
        rows, _ = merge_decisions(
            [{"Source": "CSS", "Record ID": "1", "완료 체크": "TRUE"}],
            [
                {"Source": "CSS", "Record ID": "1"},
                {"Source": "LEAD", "Record ID": "1"},
            ],
        )
        self.assertEqual([x["완료 체크"] for x in rows], ["TRUE", "FALSE"])


if __name__ == "__main__":
    unittest.main()
