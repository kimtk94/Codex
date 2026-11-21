#!/usr/bin/env python3
"""Regression tests for safely isolated Feishu Lead action queues."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import lead_action_queue_views as q

def row(name="메일 발송 증거 없음", **checks):
    return {"연락 구분": name,
            "검토 완료": checks.get("reviewed",False),
            "메일 발송 예정": checks.get("planned",False),
            "재연락 필요": checks.get("recontact",False)}

class QueueTests(unittest.TestCase):
    def test_expected_priorities(self):
        self.assertEqual(q.classify(row(recontact=True,planned=True)), "recontact")
        self.assertEqual(q.classify(row(planned=True)), "planned")
        self.assertEqual(q.classify(row()), "review")
        self.assertEqual(q.classify(row(reviewed=True)), "none")
        self.assertEqual(q.classify(row(name="발송 확인 (Lead 생성 후)")), "none")
        self.assertEqual(q.classify(row(name="Lead 생성 전만 발송")), "none")

    def test_priorities_remain_mutually_exclusive(self):
        records={
            "a":row(recontact=True,planned=True,reviewed=True),
            "b":row(planned=True),
            "c":row(),
            "d":row(reviewed=True),
            "e":row(name="발송 확인 (Lead 생성 후)"),
        }
        partition=q.assert_queue_partition(records)
        self.assertEqual(partition, {
            "recontact":{"a"}, "planned":{"b"}, "review":{"c"},
            "none":{"d","e"}})

    def test_checked_none_is_false(self):
        self.assertEqual(q.classify(row(reviewed=None,planned=None,recontact=None)), "review")

    def test_checkbox_type_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,"NOT_BOOLEAN"):
            q.classify(row(recontact="false"))

    def test_filter_definitions_true_false_and_mail(self):
        f={n:"fld"+str(i) for i,n in enumerate(q.REQUIRED)}
        rec=q.queue_filter(f,"recontact")
        planned=q.queue_filter(f,"planned")
        review=q.queue_filter(f,"review")
        self.assertEqual(len(rec["conditions"]),1)
        self.assertEqual(len(planned["conditions"]),2)
        self.assertEqual(len(review["conditions"]),4)
        self.assertEqual([x["operator"] for x in planned["conditions"]],
                         ["isNot","is"])
        self.assertEqual([x["operator"] for x in review["conditions"]],
                         ["isNot","isNot","isNot","is"])
        self.assertEqual(review["conditions"][-1]["value"],
                         '["메일 발송 증거 없음"]')

    def test_filters_compare_without_ids_or_order(self):
        f={n:"fld"+str(i) for i,n in enumerate(q.REQUIRED)}
        expected=q.queue_filter(f,"review")
        actual={"conjunction":"and","conditions":[
            dict(c,condition_id="server-id",field_type=7)
            for c in reversed(expected["conditions"])]}
        self.assertTrue(q.conditions_equal(actual,expected))
        self.assertFalse(q.conditions_equal(
            dict(actual,conjunction="or"),expected))
        altered=[dict(c) for c in actual["conditions"]]
        altered[0]["operator"]="is"
        self.assertFalse(q.conditions_equal(
            {"conjunction":"and","conditions":altered},expected))

    def test_view_names_are_distinct_and_scoped(self):
        self.assertEqual(len(q.QUEUES),3)
        self.assertEqual({kind for _,kind in q.QUEUES},
                         {"recontact","planned","review"})
        self.assertEqual(q.EXPECTED_TABLE_ID, "tblanxghmeeKJGRO")

    def test_unrecognized_category_blocks(self):
        f={n:"fld"+str(i) for i,n in enumerate(q.REQUIRED)}
        with self.assertRaisesRegex(RuntimeError,"UNKNOWN_QUEUE_KIND"):
            q.queue_filter(f,"unknown")

if __name__ == "__main__":
    unittest.main()
