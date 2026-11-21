#!/usr/bin/env python3
"""Evidence classification tests; never use production Lead IDs or emails."""
import datetime as dt
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import lead_delta_evidence as e

SOURCE = (
    'LEAD_DELTA_SOURCE_EVIDENCE={"earliest_mail_checked_at":"2026-11-20T07:39:00+00:00",'
    '"latest_mail_checked_at":"2026-11-20T07:39:00+00:00",'
    '"feishu_snapshot_at":"2026-11-21T02:00:00+00:00",'
    '"records":1050,"distinct_source_stamps":1}'
)
PLAN = (
    'LEAD_DELTA_PLAN={"records":1050,"source_stamps":1,"pending_updates":0,'
    '"allowed_max":262,"counts_before":{"recontact":0,"planned":0,"review":734,"none":316},'
    '"apply":true}'
)
NO_CHANGE = (
    'LEAD_DELTA_NO_NEW_DATA=1 {"checked":1050,"views_verified":3,'
    '"counts":{"recontact":0,"planned":0,"review":734,"none":316},' +
    '"writes":0,"second_snapshot_verified":true}'
)
READBACK = (
    'LEAD_DELTA_READBACK_PASS={"records":1050,"changed":1,'
    '"counts_after":{"recontact":1,"planned":0,"review":733,"none":316},'
    '"manual_selections_preserved":true,"other_tables_touched":false}'
)

class EvidenceTests(unittest.TestCase):
    def snapshot(self, preview, apply=None):
        return e.evidence(preview,apply,{
            "GITHUB_RUN_ID":"1234", "GITHUB_REPOSITORY":"example/Repo",
            "GITHUB_SHA":"abc", "GITHUB_RUN_ATTEMPT":"1",
        }, dt.datetime(2026,11,21,2,1,tzinfo=dt.timezone.utc))

    def test_no_new_data_status_requires_all_three_verified_views(self):
        result=self.snapshot(SOURCE+"\n"+PLAN+"\nLEAD_DELTA_READ_ONLY_PASS=1",
                             SOURCE+"\n"+PLAN+"\n"+NO_CHANGE)
        self.assertEqual(result["result"],"NO_NEW_DATA")
        self.assertEqual(result["no_new_data"]["writes"],0)
        self.assertEqual(result["no_new_data"]["views_verified"],3)
        self.assertEqual(result["plan"]["records"],1050)

    def test_actual_delta_success_evidence(self):
        changed_plan=PLAN.replace('"pending_updates":0','"pending_updates":1')
        result=self.snapshot(SOURCE+"\n"+changed_plan+"\nLEAD_DELTA_READ_ONLY_PASS=1",
                             SOURCE+"\n"+changed_plan+"\nLEAD_DELTA_PREWRITE_SNAPSHOT_PASS=1050 pending=1\n"
                             "LEAD_DELTA_APPLY_PROGRESS=1/1\n"+READBACK)
        self.assertEqual(result["result"],"PASS")
        self.assertTrue(result["prewrite_snapshot_checked"])
        self.assertEqual(result["readback"]["changed"],1)
        self.assertEqual(result["applied_batches"],1)
        self.assertEqual(result["run_url"],"https://github.com/example/Repo/actions/runs/1234")

    def test_stale_source_is_not_no_new_data(self):
        result=self.snapshot(SOURCE+"\nLEAD_DELTA_FAILED=LEAD_DELTA_SOURCE_STALE")
        self.assertEqual(result["result"],"STALE")
        self.assertEqual(result["error_class"],"SOURCE_STALE")

    def test_missing_feishu_api_is_source_unavailable(self):
        result=self.snapshot("LEAD_DELTA_FAILED=HTTP 401 from /open-apis/bitable/v1/apps/example")
        self.assertEqual(result["result"],"SOURCE_UNAVAILABLE")

    def test_readback_mismatch_is_sink_lag(self):
        result=self.snapshot(SOURCE+"\n"+PLAN+"\nLEAD_DELTA_READ_ONLY_PASS=1",
                             SOURCE+"\n"+PLAN+"\nLEAD_DELTA_FAILED=LEAD_DELTA_VIEW_IDS_MISMATCH")
        self.assertEqual(result["result"],"SINK_LAG")

    def test_concurrent_change_is_block(self):
        result=self.snapshot("LEAD_DELTA_READ_ONLY_PASS=1",
                             "LEAD_DELTA_FAILED=LEAD_DELTA_CONCURRENT_MANUAL_CHANGE")
        self.assertEqual(result["result"],"BLOCK")
        self.assertEqual(result["error_class"],"CONCURRENT_CHANGE")

    def test_read_only_not_marked_as_applied(self):
        result=self.snapshot(SOURCE+"\n"+PLAN+"\nLEAD_DELTA_READ_ONLY_PASS=1")
        self.assertEqual(result["result"],"READ_ONLY")
        self.assertIsNone(result["readback"])

    def test_sensitive_text_not_copied_to_evidence(self):
        input_log=SOURCE+"\n"+PLAN+"\nLEAD_DELTA_READ_ONLY_PASS=1\nCustomer: hidden@example.com ID 00Q-secret"
        data=self.snapshot(input_log)
        import json
        encoded=json.dumps(data,ensure_ascii=False)
        self.assertNotIn("hidden@example.com",encoded)
        self.assertNotIn("00Q-secret",encoded)
        self.assertIn("원천 QQ·SFDC 직접 재조회가 아닌 Feishu", e.render_summary(data))

    def test_readback_without_prewrite_or_apply_is_not_pass(self):
        changed_plan=PLAN.replace('"pending_updates":0','"pending_updates":1')
        preview=SOURCE+"\n"+changed_plan+"\nLEAD_DELTA_READ_ONLY_PASS=1"
        result=self.snapshot(preview,SOURCE+"\n"+changed_plan+"\n"+READBACK)
        self.assertEqual(result["result"],"BLOCK")
        result=self.snapshot(preview,SOURCE+"\n"+changed_plan+
            "\nLEAD_DELTA_PREWRITE_SNAPSHOT_PASS=1050 pending=1\n"+READBACK)
        self.assertEqual(result["result"],"BLOCK")

    def test_readback_with_inconsistent_counts_or_changed_rows_is_not_pass(self):
        changed_plan=PLAN.replace('"pending_updates":0','"pending_updates":1')
        preview=SOURCE+"\n"+changed_plan+"\nLEAD_DELTA_READ_ONLY_PASS=1"
        base=SOURCE+"\n"+changed_plan+"\nLEAD_DELTA_PREWRITE_SNAPSHOT_PASS=1050 pending=1\nLEAD_DELTA_APPLY_PROGRESS=1/1\n"
        self.assertEqual(self.snapshot(preview,base+READBACK.replace('"changed":1','"changed":0'))["result"],"BLOCK")
        self.assertEqual(self.snapshot(preview,base+READBACK.replace('"review":733','"review":700'))["result"],"BLOCK")
        self.assertEqual(self.snapshot(preview,base+READBACK.replace('"changed":1','"changed":2'))["result"],"BLOCK")

    def test_readback_does_not_override_unverified_preview(self):
        changed_plan=PLAN.replace('"pending_updates":0','"pending_updates":1')
        applied=SOURCE+"\n"+changed_plan+"\nLEAD_DELTA_PREWRITE_SNAPSHOT_PASS=1050 pending=1\nLEAD_DELTA_APPLY_PROGRESS=1/1\n"+READBACK
        result=self.snapshot(SOURCE+"\n"+changed_plan,applied)
        self.assertEqual(result["result"],"BLOCK")

    def test_incomplete_no_change_not_pass(self):
        result=self.snapshot("LEAD_DELTA_READ_ONLY_PASS=1",
            'LEAD_DELTA_NO_NEW_DATA=1 {"checked":1050,"views_verified":2,"writes":0}')
        self.assertEqual(result["result"],"BLOCK")

    def test_no_new_data_requires_second_snapshot_and_consistent_partition(self):
        preview=SOURCE+"\n"+PLAN+"\nLEAD_DELTA_READ_ONLY_PASS=1"
        missing_snapshot=NO_CHANGE.replace('"second_snapshot_verified":true',
                                            '"second_snapshot_verified":false')
        self.assertEqual(self.snapshot(preview,SOURCE+"\n"+PLAN+"\n"+missing_snapshot)["result"],
                         "BLOCK")
        bad_counts=NO_CHANGE.replace('"review":734','"review":733')
        self.assertEqual(self.snapshot(preview,SOURCE+"\n"+PLAN+"\n"+bad_counts)["result"],
                         "BLOCK")
        changed_plan=PLAN.replace('"pending_updates":0','"pending_updates":1')
        self.assertEqual(self.snapshot(preview,SOURCE+"\n"+changed_plan+"\n"+NO_CHANGE)["result"],
                         "BLOCK")

    def test_simulated_change_is_separate_from_actual_pass(self):
        sim=('LEAD_DELTA_SIMULATED_ONE_CHANGE_PASS={"mode":"SIMULATION_ONLY",'
             '"source_records":1050,"simulated_checkbox_flips":1,'
             '"expected_derived_field_updates":1,"real_feishu_writes":0,'
             '"manual_selection_preserved":true,'
             '"Lead ID":"should-not-be-exported"}')
        result=e.evidence(SOURCE+"\n"+PLAN+"\nLEAD_DELTA_READ_ONLY_PASS=1",
                          SOURCE+"\n"+PLAN+"\n"+NO_CHANGE,
                          simulation_log=sim)
        self.assertEqual(result["result"],"NO_NEW_DATA")
        self.assertEqual(result["simulated_one_checkbox"]["result"],"SIMULATION_PASS")
        self.assertNotIn("should-not-be-exported",str(result))
        self.assertIn("실제 Feishu 쓰기 0건",e.render_summary(result))

    def test_invalid_canary_cannot_be_called_simulation_pass(self):
        sim=('LEAD_DELTA_SIMULATED_ONE_CHANGE_PASS={"mode":"SIMULATION_ONLY",'
             '"simulated_checkbox_flips":1,"expected_derived_field_updates":1,'
             '"real_feishu_writes":1,"manual_selection_preserved":true}')
        self.assertEqual(e.parse_simulation(sim)["result"],"BLOCK")

if __name__=="__main__":
    unittest.main()
