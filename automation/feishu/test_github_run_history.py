#!/usr/bin/env python3
"""No private secrets, invoice totals, or customer records in run-history tests."""
import datetime as dt
import unittest
from unittest import mock

import github_run_history as h

NOW=dt.datetime(2026,11,9,11,0,tzinfo=dt.timezone.utc)
SFDC_JOB={"name":"validate-and-stage","steps":[
    {"name":"Read authorized subscription mail and conditionally stage","conclusion":"success"},
    {"name":"Check current 09/12/17 report slot after staging","conclusion":"success"},
    {"name":"Publish only SFDC Quote Review and Weekly KPI (not Payment or Monthly)","conclusion":"success"},
    {"name":"Refresh and verify native Quote trend dashboards","conclusion":"success"},
]}
FEISHU_JOBS=[{"name":name,"conclusion":"success"} for name in (
    "ingest","lifecycle","payment","monthly")]

def run(event="schedule",conclusion="success",id=42601304874):
    return {"id":id,"event":event,"status":"completed","conclusion":conclusion,
            "run_started_at":"2026-11-09T10:30:04Z",
            "updated_at":"2026-11-09T10:35:20Z",
            "html_url":"https://github.com/kimtk94/Codex/actions/runs/"+str(id),
            "head_branch":"main"}

class RunHistoryTests(unittest.TestCase):
    def test_schedule_from_workflow_cron_and_kst_day_rollover(self):
        text="on:\n  schedule:\n    - cron: '50 0,3,8 * * *'\n    - cron: '20 1,4,9,10,11 * * *'\npermissions:\n"
        slots,next_run=h.schedule_from_yaml(text,NOW)
        self.assertEqual(slots,"09:50, 10:20, 12:50, 13:20, 17:50, 18:20, 19:20, 20:20")
        self.assertEqual(next_run,"2026-11-09 20:20:00")
        text="on:\n  schedule:\n    - cron: '25 0,3,6,9,12,15,18,21 * * *'\npermissions:\n"
        slots,next_run=h.schedule_from_yaml(text,NOW)
        self.assertEqual(slots,"00:25, 03:25, 06:25, 09:25, 12:25, 15:25, 18:25, 21:25")
        self.assertEqual(next_run,"2026-11-09 21:25:00")

    def test_sf_source_sink_must_both_have_step_evidence(self):
        row=h.build_row("SFDC Report",run(),[SFDC_JOB],("09:50","2026-11-10 09:50:00"),NOW)
        self.assertEqual(row["원본 검증"],"PASS")
        self.assertEqual(row["결과 검증"],"PASS")
        self.assertEqual(row["검증 상태"],"PASS")
        self.assertEqual(row["운영 여부"],"OPERATION")
        self.assertEqual(row["실행 구분"],"예약")
        self.assertEqual(row["시작 KST"],"2026-11-09 19:30:04")
        self.assertEqual(row["실행 링크"]["link"],run()["html_url"])
        self.assertEqual(row["실제 소요 분"],5.27)

    def test_green_checkmark_without_source_evidence_is_not_verified(self):
        source,sink,verdict,_=h.result_states("SFDC Report",run(),[])
        self.assertEqual((source,sink,verdict),("NOT_EVALUATED","NOT_EVALUATED","TEST_ONLY"))
        row=h.build_row("SFDC Report",run(event="pull_request"),[],
                        ("09:50","2026-11-10 09:50:00"),NOW)
        self.assertEqual(row["운영 여부"],"TEST")
        self.assertEqual(row["검증 상태"],"TEST_ONLY")

    def test_failed_pr_is_not_an_operating_alert(self):
        row=h.build_row("SFDC Report",run(event="pull_request",conclusion="failure"),[],
                        ("09:50","2026-11-10 09:50:00"),NOW)
        self.assertEqual(row["운영 여부"],"TEST")
        self.assertEqual(row["검증 상태"],"TEST_FAILURE")

    def test_feishu_partial_payment_pass_is_not_complete_success(self):
        jobs=[{"name":"ingest","conclusion":"success"},
              {"name":"lifecycle","conclusion":"success"},
              {"name":"payment","conclusion":"success"},
              {"name":"monthly","conclusion":"failure"}]
        source,sink,verdict,parts=h.result_states("Feishu Payment·Online·Monthly",
                run(conclusion="failure"),jobs)
        self.assertEqual(source,"PASS")
        self.assertEqual(sink,"PARTIAL")
        self.assertEqual(verdict,"CHECK")
        self.assertEqual(parts["payment"],"PASS")
        self.assertEqual(parts["monthly"],"FAIL")

    def test_feishu_jobs_complete_prove_both(self):
        a=h.result_states("Feishu Payment·Online·Monthly",run(),FEISHU_JOBS)
        self.assertEqual(a[:3],("PASS","PASS","PASS"))

    def test_missing_source_stays_unverified(self):
        jobs=[{"name":"ingest","conclusion":"success"},
              {"name":"payment","conclusion":"success"}]
        a=h.result_states("Feishu Payment·Online·Monthly",run(),jobs)
        self.assertEqual(a[0],"PASS")
        self.assertEqual(a[1],"PENDING")
        self.assertNotEqual(a[2],"PASS")

    def test_filter_policies_and_utc_prefix(self):
        fields={"최근 표시":"fldRecent","검증 상태":"fldVerdict",
                "운영 여부":"fldOperation","확인 필요":"fldAlert"}
        cfg=h.filter_config((("최근 표시","RECENT"),),fields)
        self.assertEqual(cfg["conjunction"],"and")
        view={"property":{"filter_info":cfg}}
        self.assertTrue(h.matches_filter(view,(("최근 표시","RECENT"),),fields))
        self.assertFalse(h.matches_filter(view,(("최근 표시","HISTORY"),),fields))
        problems=(("확인 필요","YES"),)
        self.assertEqual(len(h.filter_config(problems,fields)["conditions"]),1)
        self.assertTrue(h.matches_filter(
            {"property":{"filter_info":h.filter_config(problems,fields)}},
            problems,fields))
        self.assertTrue(h.matches_filter({"property":{"filter_info":{"conditions":[]}}},
                                         (),fields))

    def test_readback_is_value_based_and_preserves_link(self):
        desired={"Run Key":"SFDC:123","실행 상태":"SUCCESS","실제 소요 분":5.2,
                 "실행 링크":{"text":"GitHub 실행 로그",
                              "link":"https://github.com/kimtk94/Codex/actions/runs/123"},
                 "최종 확인 KST":"now"}
        self.assertTrue(h.visible_equal(desired,desired))
        changed=dict(desired,**{"원본 검증":"FAIL"})
        self.assertFalse(h.visible_equal(desired,changed))
        wrong=dict(desired,**{"실행 링크":{"text":"GitHub 실행 로그","link":"https://example.org"}})
        self.assertFalse(h.visible_equal(desired,wrong))

    def test_unverified_external_url_is_rejected(self):
        row=run()
        row["html_url"]="https://example.net/unsafe"
        with self.assertRaisesRegex(h.SafeError,"RUN_URL_MISMATCH"):
            h.build_row("SFDC Report",row,[SFDC_JOB],
                        ("09:50","2026-11-10 09:50:00"),NOW)

    def test_operating_and_problems_views_ignore_old_runs_and_pr(self):
        self.assertEqual(h.VIEW_FILTERS[0][0],h.VIEW_MONITOR)
        self.assertEqual(h.VIEW_FILTERS[0][1],(("운영 여부","MONITOR"),))
        self.assertEqual(h.VIEW_FILTERS[1][1],(("최근 표시","RECENT"),))
        self.assertEqual(h.VIEW_FILTERS[2][1],(("확인 필요","YES"),))
        row=h.build_row("SFDC Report",run(event="pull_request",conclusion="failure"),[],
                        ("09:50","next"),NOW)
        self.assertEqual(row["최근 표시"],"HISTORY")
        self.assertEqual(row["검증 상태"],"TEST_FAILURE")

    def test_monitor_rows_show_start_middle_complete_and_next_clock(self):
        run_data=run()
        schedule=("09:50, 10:20, 12:50, 13:20, 17:50, 18:20, 19:20, 20:20",
                  "2026-11-09 20:20:00")
        with (mock.patch.object(h,"workflow_activation",return_value=
                dt.datetime(2026,11,9,10,30,tzinfo=dt.timezone.utc)),
             mock.patch.object(h,"get_jobs",return_value=[SFDC_JOB])):
            row=h.build_monitor_row("SFDC Report",
                "sfdc-three-report-email-digestion.yml",schedule,
                [run_data],[run_data],NOW)
        self.assertEqual(row["Run Key"],"MONITOR:SFDC")
        self.assertEqual(row["운영 여부"],"MONITOR")
        self.assertEqual(row["진행 단계"],"완료")
        self.assertEqual(row["진행률"],"3/3")
        self.assertEqual(row["시작 FLAG"],"PASS")
        self.assertEqual(row["완료 FLAG"],"PASS")
        self.assertEqual(row["예약 점검"],"FIRST_SLOT_PENDING")
        self.assertEqual(row["다음 예약 KST"],"2026-11-09 20:20:00")
        self.assertEqual(row["확인 필요"],"NO")

    def test_monitor_missing_slot_causes_alert_even_after_prior_success(self):
        historical=run()
        now=dt.datetime(2026,11,9,12,6,tzinfo=dt.timezone.utc)
        schedule=("09:50, 10:20, 12:50, 13:20, 17:50, 18:20, 19:20, 20:20",
                  "2026-11-10 09:50:00")
        with (mock.patch.object(h,"workflow_activation",return_value=
                dt.datetime(2026,11,9,10,30,tzinfo=dt.timezone.utc)),
             mock.patch.object(h,"get_jobs",return_value=[SFDC_JOB])):
            row=h.build_monitor_row("SFDC Report",
                "sfdc-three-report-email-digestion.yml",schedule,
                [historical],[historical],now)
        self.assertEqual(row["예약 점검"],"SCHEDULE_MISSING")
        self.assertEqual(row["확인 필요"],"YES")
        self.assertEqual(row["검증 상태"],"CHECK")
        self.assertEqual(row["완료 FLAG"],"PASS")
        self.assertEqual(row["최근 예약 슬롯 KST"],"2026-11-09 20:20:00")

    def test_latest_main_branch_runs_are_required_before_writes(self):
        with mock.patch.object(h,"schedule_map",return_value={
             "SFDC Report":("09:50","next"),
             "Feishu Payment·Online·Monthly":("00:25","next")}),\
             mock.patch.object(h,"gh",return_value={"workflow_runs":[]}):
            with self.assertRaisesRegex(h.SafeError,"NO_MAIN_BRANCH"):
                h.collect_rows(NOW)


if __name__=="__main__":
    unittest.main()
