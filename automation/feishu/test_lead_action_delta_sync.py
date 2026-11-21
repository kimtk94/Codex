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

    def test_prewrite_snapshot_detects_concurrent_manual_change(self):
        original={"a":{"record_id":"recA","fields":row("a",d.queue.QUEUE_LABELS["review"])}}
        same={"a":{"record_id":"recA","fields":dict(original["a"]["fields"])}}
        self.assertEqual(d.validate_prewrite_snapshot(original,same),1)
        same["a"]["fields"]["메일 발송 예정"]=True
        with self.assertRaisesRegex(RuntimeError,"CONCURRENT_MANUAL_CHANGE"):
            d.validate_prewrite_snapshot(original,same)

    def test_prewrite_snapshot_detects_concurrent_source_change(self):
        original={"a":{"record_id":"recA","fields":row("a",d.queue.QUEUE_LABELS["review"])}}
        changed={"a":{"record_id":"recA","fields":dict(original["a"]["fields"])}}
        changed["a"]["fields"]["연락 구분"]="발송 확인 (Lead 생성 후)"
        with self.assertRaisesRegex(RuntimeError,"CONCURRENT_SOURCE_CHANGE"):
            d.validate_prewrite_snapshot(original,changed)

    def _fake_environment(self, flags_changed):
        # Simulate Feishu's API with 450 distinct records, but no actual user
        # records or email operations. Return immutable snapshots for each GET.
        from copy import deepcopy
        store={str(i):{"record_id":"rec"+str(i),
                        "fields":row(str(i),d.queue.QUEUE_LABELS["review"])}
               for i in range(450)}
        if flags_changed:
            store["42"]["fields"]["메일 발송 예정"]=True
        writes=[]
        def request(method,path,token=None,body=None):
            if method != "POST" or not path.endswith("/records/batch_update"):
                raise AssertionError("Unexpected API write: "+method+" "+path)
            writes.append(deepcopy(body))
            for changed in body["records"]:
                for key in store:
                    if store[key]["record_id"]==changed["record_id"]:
                        if set(changed["fields"])!={d.queue.QUEUE_FIELD}:
                            raise AssertionError("Unapproved Feishu field write")
                        store[key]["fields"].update(changed["fields"])
                        break
                else:
                    raise AssertionError("Unknown Lead record")
            return {"code":0,"data":{}}
        def pages(path, token):
            if path.endswith("/tables"):
                return iter([{"name":d.lead.TABLE,
                              "table_id":d.queue.EXPECTED_TABLE_ID}])
            if path.endswith("/fields"):
                return iter([])
            raise AssertionError("Unexpected Feishu list: "+path)
        views={title:"view-"+kind for title,kind in d.queue.QUEUES}
        return store,writes,request,pages,views

    def test_real_apply_path_simulated_manual_change_updates_exactly_one(self):
        from copy import deepcopy
        store,writes,request,pages,views=self._fake_environment(True)
        initial_manual=d.queue.manual_snapshot(
            {key:rec["fields"] for key,rec in store.items()})
        with mock.patch.object(d.lead,"auth",return_value="token"), \
             mock.patch.object(d,"pages",side_effect=pages), \
             mock.patch.object(d,"schema_check",return_value="fldPriority"), \
             mock.patch.object(d.queue,"load_records",side_effect=lambda root, token: deepcopy(store)), \
             mock.patch.object(d,"source_stamps_fresh",return_value=1), \
             mock.patch.object(d,"validate_views",return_value=views), \
             mock.patch.object(d,"verify_view_ids",return_value={
                 "recontact":0,"planned":1,"review":449,"none":0}), \
             mock.patch.object(d,"request",side_effect=request):
            d.main(apply=True)
        self.assertEqual(len(writes),1)
        self.assertEqual(len(writes[0]["records"]),1)
        self.assertEqual(writes[0]["records"][0]["record_id"],"rec42")
        self.assertEqual(
            store["42"]["fields"][d.queue.QUEUE_FIELD],
            d.queue.QUEUE_LABELS["planned"])
        self.assertEqual(initial_manual, d.queue.manual_snapshot(
            {key:rec["fields"] for key,rec in store.items()}))

    def test_no_change_path_checks_view_ids_without_writing(self):
        from copy import deepcopy
        store,writes,request,pages,views=self._fake_environment(False)
        with mock.patch.object(d.lead,"auth",return_value="token"), \
             mock.patch.object(d,"pages",side_effect=pages), \
             mock.patch.object(d,"schema_check",return_value="fldPriority"), \
             mock.patch.object(d.queue,"load_records",return_value=deepcopy(store)), \
             mock.patch.object(d,"source_stamps_fresh",return_value=1), \
             mock.patch.object(d,"validate_views",return_value=views), \
             mock.patch.object(d,"verify_view_ids",return_value={
                 "recontact":0,"planned":0,"review":450,"none":0}) as verify, \
             mock.patch.object(d,"request",side_effect=request):
            d.main(apply=True)
            verify.assert_called_once()
        self.assertEqual(writes,[])

    def test_one_real_shape_checkbox_simulated_without_any_external_writes(self):
        records={str(i):{"record_id":"rec"+str(i),
                         "fields":row(str(i),d.queue.QUEUE_LABELS["review"])}
                 for i in range(450)}
        original_manual=d.queue.manual_snapshot(
            {k:rec["fields"] for k,rec in records.items()})
        result=d.simulate_single_manual_change(records)
        self.assertEqual(result["mode"],"SIMULATION_ONLY")
        self.assertEqual(result["source_records"],450)
        self.assertEqual(result["simulated_checkbox_flips"],1)
        self.assertEqual(result["expected_derived_field_updates"],1)
        self.assertEqual(result["real_feishu_writes"],0)
        self.assertEqual(result["scenario_after"]["review"],449)
        self.assertEqual(result["scenario_after"]["planned"],1)
        self.assertEqual(original_manual,d.queue.manual_snapshot(
            {k:rec["fields"] for k,rec in records.items()}))
        self.assertEqual(d.plan_changes(records),[])

    def test_one_checkbox_simulation_refuses_dirty_baseline(self):
        records={str(i):{"record_id":"rec"+str(i),
                         "fields":row(str(i),d.queue.QUEUE_LABELS["review"])}
                 for i in range(450)}
        records["42"]["fields"]["메일 발송 예정"]=True
        with self.assertRaisesRegex(RuntimeError,"BASELINE_NOT_CLEAN"):
            d.simulate_single_manual_change(records)

if __name__=="__main__":
    unittest.main()
