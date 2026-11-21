#!/usr/bin/env python3
"""Deterministic offline safety tests for Feishu-only Lead queue delta sync."""
import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).parent))
import lead_action_delta_sync as d

def row(id, priority=None, review=False, planned=False, recontact=False,
        stamp="2026-11-20T16:39:00+09:00"):
    return {
        "Lead ID":id, "Lead Status":"Open",
        "연락 구분":"메일 발송 증거 없음",
        "메일 원본 확인시각":stamp,
        "검토 완료":review,"메일 발송 예정":planned,"재연락 필요":recontact,
        d.queue.QUEUE_FIELD:priority,
    }

class DeltaTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,11,21,1,0,tzinfo=dt.timezone.utc)

    def test_source_stamps_must_be_fresh_and_timezoned(self):
        sample={"a":row("a")}
        self.assertEqual(d.source_stamps_fresh(sample,self.now),1)
        sample["a"]["메일 원본 확인시각"]="2026-11-17T10:00:00+09:00"
        with self.assertRaisesRegex(RuntimeError,"SOURCE_STALE"):
            d.source_stamps_fresh(sample,self.now)
        sample["a"]["메일 원본 확인시각"]="2026-11-20T00:00:00"
        with self.assertRaisesRegex(RuntimeError,"NAIVE"):
            d.source_stamps_fresh(sample,self.now)
        sample["a"]["메일 원본 확인시각"]="2030-01-01T00:00:00+09:00"
        with self.assertRaisesRegex(RuntimeError,"FUTURE"):
            d.source_stamps_fresh(sample,self.now)

    def test_plan_writes_only_derived_field_and_changed_rows(self):
        records={str(i):{"record_id":"rec"+str(i),
                         "fields":row(str(i),d.queue.QUEUE_LABELS["review"])}
                 for i in range(450)}
        records["42"]["fields"]["메일 발송 예정"]=True
        records["100"]["fields"]["재연락 필요"]=True
        changes=d.plan_changes(records)
        self.assertEqual(len(changes),2)
        self.assertEqual([x["record_id"] for x in changes],["rec42","rec100"])
        self.assertTrue(all(set(x["fields"])=={d.queue.QUEUE_FIELD} for x in changes))
        self.assertEqual(changes[0]["fields"][d.queue.QUEUE_FIELD],
                         d.queue.QUEUE_LABELS["planned"])
        self.assertEqual(changes[1]["fields"][d.queue.QUEUE_FIELD],
                         d.queue.QUEUE_LABELS["recontact"])

    def test_no_changes_is_valid_idempotent_case(self):
        records={str(i):{"record_id":"rec"+str(i),
                         "fields":row(str(i),d.queue.QUEUE_LABELS["review"])}
                 for i in range(450)}
        self.assertEqual(d.plan_changes(records),[])
        self.assertEqual(d.guard_delta_size([],450),112)

    def test_large_bulk_change_fails_without_writes(self):
        with self.assertRaisesRegex(RuntimeError,"TOO_MANY_CHANGES"):
            d.guard_delta_size([1]*113,450)
        self.assertEqual(d.guard_delta_size([1]*112,450),112)

    def test_schema_requires_only_exact_text_and_checkbox_fields(self):
        expected={
            "Lead ID":1, "Lead Status":1, "연락 구분":1,
            "메일 원본 확인시각":1,d.queue.QUEUE_FIELD:1,
            **{name:7 for name in d.manual.MANUAL}
        }
        fields=[{"field_name":name,"type":typ,"field_id":"fld"+str(i)}
                for i,(name,typ) in enumerate(expected.items())]
        self.assertTrue(d.schema_check(fields).startswith("fld"))
        bad=[dict(x) for x in fields]
        bad[-1]["type"]=1
        with self.assertRaisesRegex(RuntimeError,"SCHEMA_CONFLICT"):
            d.schema_check(bad)

    def test_manual_flags_immutable_after_priority_update(self):
        r=row("a", d.queue.QUEUE_LABELS["review"])
        original={"a":{"record_id":"recA","fields":dict(r)}}
        after={"a":{"record_id":"recA","fields":dict(r)}}
        verified=d.check_preservation(original,after)
        self.assertIn("a",verified)
        after["a"]["fields"]["검토 완료"]=True
        with self.assertRaisesRegex(RuntimeError,"MANUAL_FIELD_CHANGED"):
            d.check_preservation(original,after)

    def test_source_field_mismatch_is_blocking(self):
        r=row("a",d.queue.QUEUE_LABELS["review"])
        original={"a":{"record_id":"recA","fields":dict(r)}}
        after={"a":{"record_id":"recA","fields":dict(r)}}
        after["a"]["fields"]["Lead Status"]="Converted"
        with self.assertRaisesRegex(RuntimeError,"SOURCE_FIELD_CHANGED"):
            d.check_preservation(original,after)

    def test_readback_priority_mismatch_blocks(self):
        r=row("a",d.queue.QUEUE_LABELS["none"])
        original={"a":{"record_id":"recA","fields":dict(r)}}
        after={"a":{"record_id":"recA","fields":dict(r)}}
        with self.assertRaisesRegex(RuntimeError,"PRIORITY_READBACK_MISMATCH"):
            d.check_preservation(original,after)

    def test_view_id_mismatch_detected(self):
        fields={"a":row("a",d.queue.QUEUE_LABELS["review"])}
        views={title:"view"+kind for title,kind in d.queue.QUEUES}
        with mock.patch.object(d.queue,"read_view_ids",return_value={"bogus"}):
            with self.assertRaisesRegex(RuntimeError,"VIEW_IDS_MISMATCH"):
                d.verify_view_ids("/root","token",fields,views)

if __name__=="__main__":
    unittest.main()
