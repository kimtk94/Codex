#!/usr/bin/env python3
"""The project dashboard tracks lifecycle, not a performance leaderboard."""
import unittest
from native_dashboard_cli import (
    BLOCKS, TABLE, ACTIVE_STAGE, LEGACY_PROGRESS_RANK,
    LEGACY_RAW_STAGE_CHART, legacy_dashboard_block,
)
from native_payment_dashboard_cli import PROJECT_BLOCKS


class ProgressDashboardTests(unittest.TestCase):
    def test_rankings_are_not_in_project_dashboard(self):
        self.assertFalse(any(kind=="ranking" and config.get("table_name")==TABLE
                             for _,kind,config in BLOCKS))
        self.assertNotIn(LEGACY_PROGRESS_RANK,[x[0] for x in BLOCKS])
    def test_individual_records_keep_percent_and_stage(self):
        self.assertIn(("진행률 미확인 건수","statistics"),[
            (name,kind) for name,kind,_ in BLOCKS])
        missing=next(conf for name,_,conf in BLOCKS if name=="진행률 미확인 건수")
        self.assertIn({"field_name":"Progress %","operator":"isEmpty"},
                      missing["filter"]["conditions"])
        phase=next(conf for name,_,conf in BLOCKS if name=="프로젝트 공정별 현황")
        self.assertEqual(phase["group_by"][0]["field_name"],"Progress Phase")
        self.assertEqual(phase["count_all"],True)
        self.assertIn(ACTIVE_STAGE,phase["filter"]["conditions"])
    def test_all_progress_widgets_exclude_completed_and_paid_projects(self):
        for name,kind,config in BLOCKS:
            if config.get("table_name")==TABLE:
                self.assertIn(ACTIVE_STAGE,config["filter"]["conditions"],name)
        self.assertEqual(len(PROJECT_BLOCKS),6)
        for flt in PROJECT_BLOCKS.values():
            self.assertEqual(flt["conditions"].count(ACTIVE_STAGE),1)
    def test_quote_combo_unchanged(self):
        self.assertEqual(len([x for x in BLOCKS if x[1]=="combo"]),2)
    def test_legacy_delete_only_named_typed_dashboard_block(self):
        existing={"items":[
            {"name":LEGACY_PROGRESS_RANK,"block_id":"chtRank1","type":"ranking"},
            {"name":LEGACY_RAW_STAGE_CHART,"block_id":"chtBar1","type":"bar"},
            {"name":"Other","block_id":"chtSafe","type":"statistics"},
        ]}
        self.assertEqual(legacy_dashboard_block(existing,LEGACY_PROGRESS_RANK,
                                                "ranking"),"chtRank1")
        self.assertEqual(legacy_dashboard_block(existing,LEGACY_RAW_STAGE_CHART,
                                                "bar"),"chtBar1")
        self.assertIsNone(legacy_dashboard_block(existing,"Missing","ranking"))
        with self.assertRaisesRegex(RuntimeError,"TYPE_MISMATCH"):
            legacy_dashboard_block(existing,LEGACY_PROGRESS_RANK,"bar")
        with self.assertRaisesRegex(RuntimeError,"AMBIGUOUS"):
            legacy_dashboard_block({"items":[existing["items"][0],
                {"name":LEGACY_PROGRESS_RANK,"block_id":"chtRank2","type":"ranking"}]},
                LEGACY_PROGRESS_RANK,"ranking")
if __name__=="__main__":unittest.main()
