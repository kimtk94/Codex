#!/usr/bin/env python3
import datetime as dt
import unittest
import run_monitor_flags as f

UTC=dt.timezone.utc

def run(status="in_progress",conclusion=None):
    return {"status":status,"conclusion":conclusion}

class PhaseFlagTests(unittest.TestCase):
    def test_sfdc_started_mid_and_done(self):
        job={"steps":[]}
        start=f.stage_flags("SFDC Report",run("queued"),[job],"PENDING","PENDING")
        self.assertEqual(start["진행 단계"],"시작")
        self.assertEqual(start["시작 FLAG"],"WAIT")
        job["steps"]=[{"name":"Read authorized subscription mail and conditionally stage",
                       "status":"in_progress"}]
        mid=f.stage_flags("SFDC Report",run(),[job],"PENDING","PENDING")
        self.assertEqual(mid["중간 FLAG"],"RUNNING")
        self.assertEqual(mid["완료 FLAG"],"WAIT")
        done=f.stage_flags("SFDC Report",run("completed","success"),
                           [job],"PASS","PASS")
        self.assertEqual((done["진행 단계"],done["진행률"],done["완료 FLAG"]),
                         ("완료","3/3","PASS"))
    def test_success_with_sink_mismatch_is_blocked(self):
        r=f.stage_flags("SFDC Report",run("completed","success"),[],"PASS","FAIL")
        self.assertEqual(r["진행 단계"],"차단")
        self.assertEqual(r["완료 FLAG"],"BLOCK")
    def test_feishu_parallel_stages_are_visible(self):
        jobs=[{"name":"tests","conclusion":"success"},
              {"name":"ingest","conclusion":"success"},
              {"name":"payment","status":"in_progress"},
              {"name":"monthly","status":"in_progress"},
              {"name":"lifecycle","conclusion":"success"}]
        stages=f.stage_flags("Feishu Payment·Online·Monthly",run(),jobs,"PASS","PENDING")
        self.assertEqual(stages["진행 단계"],"중간")
        self.assertEqual(stages["중간 FLAG"],"PASS")
        self.assertIn("payment",stages["현재 작업"])
        self.assertIn("monthly",stages["현재 작업"])
    def test_failed_branch_blocks_complete(self):
        jobs=[{"name":"ingest","conclusion":"success"},
              {"name":"monthly","conclusion":"failure"}]
        flags=f.stage_flags("Feishu Payment·Online·Monthly",
                            run("completed","failure"),jobs,"PASS","PARTIAL")
        self.assertEqual(flags["완료 FLAG"],"BLOCK")
        self.assertIn("monthly",flags["현재 작업"])

class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,11,9,11,10,tzinfo=UTC) # KST 20:10
        self.activation=dt.datetime(2026,11,9,10,30,tzinfo=UTC)
        self.slots="09:50, 10:20, 12:50, 13:20, 17:50, 18:20, 19:20, 20:20"
    def test_future_slot_after_deployment_not_missing(self):
        status,slot,_=f.watch_schedule(self.now,self.activation,self.slots,[])
        self.assertEqual((status,slot),("WAIT_FIRST_SLOT",None))
    def test_start_at_2020_allows_grace(self):
        now=dt.datetime(2026,11,9,11,30,tzinfo=UTC)
        state,slot,_=f.watch_schedule(now,self.activation,self.slots,[])
        self.assertEqual(state,"DUE_WAITING")
        self.assertEqual(slot.strftime("%H:%M"),"20:20")
        late=dt.datetime(2026,11,9,12,6,tzinfo=UTC)
        state,slot,_=f.watch_schedule(late,self.activation,self.slots,[])
        self.assertEqual(state,"SCHEDULE_MISSING")
    def test_dispatch_does_not_cover_missing_schedule(self):
        now=dt.datetime(2026,11,9,12,6,tzinfo=UTC)
        manual={"event":"workflow_dispatch","head_branch":"main",
                "created_at":"2026-11-09T11:25:00Z"}
        self.assertEqual(f.watch_schedule(now,self.activation,self.slots,[manual])[0],
                         "SCHEDULE_MISSING")
    def test_schedule_late_and_failed(self):
        now=dt.datetime(2026,11,9,12,7,tzinfo=UTC)
        base={"event":"schedule","head_branch":"main",
              "status":"completed","conclusion":"success",
              "created_at":"2026-11-09T12:05:00Z"}
        self.assertEqual(f.watch_schedule(now,self.activation,self.slots,[base])[0],
                         "LATE")
        base["conclusion"]="failure"
        self.assertEqual(f.watch_schedule(now,self.activation,self.slots,[base])[0],
                         "RUN_FAILED")

if __name__=="__main__":
    unittest.main()
