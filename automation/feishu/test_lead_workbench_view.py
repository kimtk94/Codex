#!/usr/bin/env python3
import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).parent))
import lead_workbench_view as w
import lead_action_queue_views as q

def row(created="2026-10-01", desc="있음", sent="메일 발송 증거 없음"):
    return {"Lead Created": created, "Description 있음": desc,
            "연락 구분": sent, "Lead Status": "New",
            "검토 완료": False, "메일 발송 예정": False,
            "재연락 필요": False, "Lead 업무 우선순위 (자동)": q.QUEUE_LABELS["review"],
            "Lead 연락 대상 (자동)": "대상 (최근 1년)"}

class LeadWorkbenchTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(w.age, "today_kst", return_value=dt.date(2026, 11, 21))
        p.start()
        self.addCleanup(p.stop)

    def test_cutoff_inclusive_and_all_mail_types(self):
        fresh = row(created="2025-11-21")
        previous = row(created="2025-11-20")
        sent = row(sent="발송 확인 (Lead 생성 후)")
        self.assertEqual(w.expected_ids({"a": fresh, "b": previous, "c": sent}), {"a", "c"})

    def test_filter_exactly_recent_one_year(self):
        filt = w.filter_definition("fldEligibility")
        self.assertEqual(filt["conditions"], [{
            "field_id": "fldEligibility", "operator": "is",
            "value": '["대상 (최근 1년)"]',
        }])
        self.assertTrue(w.filter_matches(filt, filt))

    def test_reviewed_or_sent_still_visible_in_overview(self):
        sent = row(sent="발송 확인 (Lead 생성 후)")
        sent[q.QUEUE_FIELD] = q.QUEUE_LABELS["none"]
        reviewed = row()
        reviewed["검토 완료"] = True
        reviewed[q.QUEUE_FIELD] = q.QUEUE_LABELS["none"]
        self.assertEqual(w.expected_ids({"a": sent, "b": reviewed}), {"a", "b"})
        self.assertEqual(w.verify_rows({**{str(i): row() for i in range(448)}, "a": sent, "b": reviewed}), 450)

    def test_schema_checks_option_and_checkbox_types(self):
        names = [w.age.ELIGIBILITY_FIELD, q.QUEUE_FIELD, "연락 구분",
                 "Description 있음", "Lead Status", *q.manual.MANUAL]
        fields = [{"field_name": name, "field_id": str(i),
                  "type": 7 if name in q.manual.MANUAL else
                          1 if name in (w.age.ELIGIBILITY_FIELD, q.QUEUE_FIELD) else 3}
                  for i, name in enumerate(names)]
        self.assertEqual(w.validate_schema(fields), "0")
        fields[2]["type"] = 1
        with self.assertRaisesRegex(RuntimeError, "SELECT_FIELD_TYPE"):
            w.validate_schema(fields)

    def test_stale_derived_priority_blocks_view_mutation(self):
        rows = {str(i): row() for i in range(450)}
        self.assertEqual(w.verify_rows(rows), 450)
        rows["0"][q.QUEUE_FIELD] = "not updated"
        with self.assertRaisesRegex(RuntimeError, "QUEUE_STALE"):
            w.verify_rows(rows)

if __name__ == "__main__":
    unittest.main()
