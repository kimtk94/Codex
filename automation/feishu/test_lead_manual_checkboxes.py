#!/usr/bin/env python3
"""Safety tests: manually owned Feishu Lead state is never overwritten."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import lead_manual_checkboxes as m

class ManualCheckboxTests(unittest.TestCase):
    def test_only_three_manually_owned_checkboxes(self):
        self.assertEqual(m.MANUAL, ("검토 완료", "메일 발송 예정", "재연락 필요"))
        self.assertEqual(m.CHECKBOX_TYPE, 7)
        self.assertTrue(set(m.MANUAL).isdisjoint(set(m.lead.FIELDS)))

    def test_boolean_validation(self):
        self.assertTrue(m.checked(True))
        self.assertFalse(m.checked(False))
        self.assertFalse(m.checked(None))
        with self.assertRaisesRegex(RuntimeError, "NOT_BOOLEAN"):
            m.checked("false")

    def test_create_missing_only(self):
        schema = [
            {"field_name": "검토 완료", "type": 7},
            {"field_name": "Account (고객 입력 원문)", "type": 1},
        ]
        self.assertEqual(m.verify_schema(schema),
                         ("메일 발송 예정", "재연락 필요"))
        with self.assertRaisesRegex(RuntimeError, "TYPE_CONFLICT"):
            m.verify_schema([{"field_name":"검토 완료","type":1}])
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE_FIELD"):
            m.verify_schema([{"field_name":"검토 완료","type":7},
                             {"field_name":"검토 완료","type":7}])

    def test_preserve_checked_and_unchecked(self):
        before = {"id1": {"검토 완료": True, "메일 발송 예정": False},
                  "id2": {"검토 완료": False, "메일 발송 예정": True}}
        after = {key: dict(value) for key,value in before.items()}
        after["id1"]["재연락 필요"] = False
        after["id2"]["재연락 필요"] = False
        m.assert_unchanged(before, after)
        after["id1"]["검토 완료"] = False
        with self.assertRaisesRegex(RuntimeError, "SELECTION_CHANGED"):
            m.assert_unchanged(before, after)

    def test_row_integrity_cannot_silently_drop_manual_decision(self):
        before = {"id1": {"검토 완료": True}}
        with self.assertRaisesRegex(RuntimeError, "ROW_SET_CHANGED"):
            m.assert_unchanged(before, {"id2": {"검토 완료": True}})

if __name__=="__main__":
    unittest.main()
