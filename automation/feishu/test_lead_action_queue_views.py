#!/usr/bin/env python3
"""Safety regressions for isolated, derived-text Lead action queue."""
import sys
import unittest
import datetime as dt
from unittest import mock
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import lead_action_queue_views as q

def row(name="메일 발송 증거 없음", status="Open", **checks):
    return {"연락 구분":name,"Lead Status":status,
            "Lead Created":checks.get("created","2026-11-01"),
            "검토 완료":checks.get("reviewed",False),
            "메일 발송 예정":checks.get("planned",False),
            "재연락 필요":checks.get("recontact",False)}

class QueueTests(unittest.TestCase):
    def setUp(self):
        patcher=mock.patch.object(q.age,"today_kst",return_value=dt.date(2026,11,21))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_strict_precedence(self):
        self.assertEqual(q.classify(row(recontact=True,planned=True)),"recontact")
        self.assertEqual(q.classify(row(planned=True)),"planned")
        self.assertEqual(q.classify(row()),"review")
        self.assertEqual(q.classify(row(reviewed=True)),"none")
        self.assertEqual(q.classify(row(name="발송 확인 (Lead 생성 후)")),"none")
        self.assertEqual(q.classify(row(name="Lead 생성 전만 발송")),"none")

    def test_qualified_or_converted_excluded_from_new_outreach(self):
        for state in ("Qualified","Converted","Closed - Converted","Disqualified"):
            self.assertEqual(q.classify(row(status=state)),"none")
        self.assertEqual(q.classify(row(status="Converted",recontact=True)),"recontact")

    def test_partition_is_disjoint_and_exhaustive(self):
        records={"a":row(recontact=True,planned=True,reviewed=True),
                 "b":row(planned=True),"c":row(),"d":row(reviewed=True),
                 "e":row(name="발송 확인 (Lead 생성 후)")}
        self.assertEqual(q.partition(records),{
            "recontact":{"a"},"planned":{"b"},"review":{"c"},
            "none":{"d","e"},"expired":set()})

    def test_missing_checkbox_means_unchecked(self):
        self.assertEqual(q.classify(row(reviewed=None,planned=None,recontact=None)),"review")
        with self.assertRaisesRegex(RuntimeError,"NOT_BOOLEAN"):
            q.classify(row(recontact="false"))

    def test_derived_field_single_text_filter(self):
        wanted=q.filter_definition("fldPriority","review")
        self.assertEqual(wanted,{"conjunction":"and","conditions":[{
            "field_id":"fldPriority","operator":"is",
            "value":'["03 · 검토 대기"]'}]})
        self.assertTrue(q.filter_matches(wanted,wanted))
        self.assertEqual(len(q.QUEUES),3)
        self.assertNotIn(q.QUEUE_FIELD,q.lead.FIELDS)

    def test_manual_values_are_immutable(self):
        old={"id1":dict(row(recontact=True,planned=False),**{"Lead ID":"id1"})}
        new={"id1":dict(old["id1"],**{q.QUEUE_FIELD:q.QUEUE_LABELS["recontact"]})}
        self.assertEqual(q.manual_snapshot(old),q.manual_snapshot(new))
        new["id1"]["재연락 필요"]=False
        self.assertNotEqual(q.manual_snapshot(old),q.manual_snapshot(new))

    def test_label_map_contains_none_and_no_unknown_groups(self):
        self.assertEqual(set(q.QUEUE_LABELS),{"recontact","planned","review","none","expired"})
        self.assertEqual({kind for _,kind in q.QUEUES},{"recontact","planned","review"})
        with self.assertRaisesRegex(RuntimeError,"KIND_INVALID"):
            q.filter_definition("fld","bogus")

    def test_one_calendar_year_old_is_included_older_excluded_even_when_flagged(self):
        self.assertEqual(q.classify(row(created="2025-11-21")), "review")
        self.assertEqual(q.classify(row(created="2025-11-20",recontact=True,planned=True)), "expired")
        self.assertEqual(q.classify(row(created="2025-11-20",reviewed=True)), "expired")
        self.assertEqual(q.age.label(row(created="2025-11-20")), "제외 (1년 초과)")
        self.assertEqual(q.age.label(row(created="2025-11-21")), "대상 (최근 1년)")

    def test_eligibility_cutoff_moves_with_calendar_and_leap_year(self):
        self.assertEqual(q.age.cutoff_date(dt.date(2028,2,29)),dt.date(2027,2,28))
        self.assertEqual(q.age.cutoff_date(dt.date(2026,11,21)),dt.date(2025,11,21))
        with self.assertRaisesRegex(RuntimeError,"CREATED_DATE_MISSING"):
            q.classify(row(created=""))
        with self.assertRaisesRegex(RuntimeError,"CREATED_DATE_IN_FUTURE"):
            q.classify(row(created="2027-02-01"))

    def test_expired_leads_partition_separately_without_deleting(self):
        records={"old":row(created="2024-11-21",recontact=True),
                 "on_cutoff":row(created="2025-11-21"),
                 "fresh":row(created="2026-06-01")}
        result=q.partition(records)
        self.assertEqual(result["expired"],{"old"})
        self.assertEqual(result["review"],{"on_cutoff","fresh"})
        self.assertEqual(sum(map(len,result.values())),3)

    def test_id_and_manual_readback_guard(self):
        base={"id0":dict(row(),**{"Lead ID":"id0"})}
        expected={"id0":q.QUEUE_LABELS["review"]}
        with self.assertRaisesRegex(RuntimeError,"READBACK_ID_MISMATCH"):
            q.audit_snapshots(base,{},expected,base)
if __name__=="__main__":
    unittest.main()
