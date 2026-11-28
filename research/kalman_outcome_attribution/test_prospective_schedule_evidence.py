import copy
import unittest
import exchange_calendars as xc

from prospective_schedule_evidence import (
    audit_pair, SLOTS, MODES, STATUSES, SEAL_STATUS, WORKFLOW_ID, WORKFLOW_PATH,
)


class ScheduledEvidenceContracts(unittest.TestCase):
    def setUp(self):
        self.cal=xc.get_calendar("XNYS",start="2026-01-01",end="2028-02-01")
        self.identity={"session":"2026-11-25","source_run":10,
                       "source_sha":"a"*40,"snapshot_sha256":"b"*64}
        self.pair=[]
        for i,slot in enumerate(SLOTS):
            self.pair.append({"run_id":10+i,"workflow_id":WORKFLOW_ID,"path":WORKFLOW_PATH,
                "event":"schedule","head_branch":"main","status":"completed",
                "conclusion":"success","run_attempt":1,"head_sha":"a"*40,
                "slot":slot,"session":"2026-11-25","mode":MODES[i],
                "created_at":f"2026-11-26T0{2+2*i}:40:00Z",
                "research_started_at":f"2026-11-26T0{2+2*i}:50:00Z",
                "publisher_completed_at":f"2026-11-26T0{3+2*i}:10:00Z",
                "missing_successful_jobs":[],"log_access_error_codes":[],
                "post":{"session":"2026-11-25","mode":MODES[i],"status":STATUSES[i],
                        "new":"60" if i==0 else "0","changed":"False"},
                "remote_drive_readback":True,
                "first_seal_readback":{"session":"2026-11-25","status":SEAL_STATUS,
                    "current":True,"deep":1,"original_run":10,"snapshot_sha256":"b"*64}})

    def run_pair(self,pair):
        return audit_pair(self.identity,pair,self.cal)

    def reject(self,pair,code):
        report=self.run_pair(pair)
        self.assertEqual(report["scheduled_evidence_status"],"HOLD")
        self.assertIn(code,report["problem_codes"])
        self.assertFalse(report["primary_study_admitted"])

    def test_clean_distinct_pair_only_schedule_evidence_not_approval(self):
        r=self.run_pair(self.pair)
        self.assertEqual(r["scheduled_evidence_status"],"PASS")
        self.assertFalse(r["source_finality_certified"])
        self.assertFalse(r["primary_study_admitted"])
        self.assertFalse(r["approved_live"])

    def test_drift_with_all_jobs_green_is_rejected(self):
        self.pair[1]["post"]["changed"]="True"
        self.pair[1]["post"]["status"]="SAME_SESSION_REPLAY_DRIFT_RESEARCH_HOLD"
        self.reject(self.pair,"REPLAY_INPUTS_CHANGED_OR_UNKNOWN")
        self.reject(self.pair,"REPLAY_POSTFLIGHT_MISMATCH")

    def test_duplicate_and_missing_slot(self):
        self.reject(self.pair[:1],"REPLAY_MISSING")
        self.reject([], "FIRST_MISSING")
        self.reject(self.pair+[copy.deepcopy(self.pair[1])],"REPLAY_AMBIGUOUS")
        self.reject(self.pair+[copy.deepcopy(self.pair[1])],"DUPLICATE_OR_INVALID_RUN")

    def test_manual_substitute_commit_and_original_snapshot_changes(self):
        self.pair[0]["event"]="workflow_dispatch"
        self.pair[0]["run_id"]=9
        self.pair[1]["head_sha"]="c"*40
        self.pair[1]["first_seal_readback"]["snapshot_sha256"]="d"*64
        for code in ("WRONG_WORKFLOW_EVENT_OR_BRANCH","FIRST_NOT_ORIGINAL_CAPTURE",
                     "REPLAY_CODE_SHA_MISMATCH","REPLAY_ARCHIVE_READBACK_ANCHOR_MISMATCH"):
            self.reject(self.pair,code)

    def test_readback_after_next_open_or_before_first_readback(self):
        self.pair[1]["publisher_completed_at"]="2026-11-27T14:30:00Z"
        self.reject(self.pair,"REPLAY_NOT_PREOPEN_SCHEDULED_CAPTURE")
        self.pair[1]["publisher_completed_at"]="2026-11-26T06:00:00Z"
        self.pair[0]["publisher_completed_at"]="2026-11-26T05:00:00Z"
        self.reject(self.pair,"REPLAY_RESEARCH_STARTED_BEFORE_FIRST_READBACK")

    def test_wrong_counts_missing_logs_and_rerun_attempt(self):
        self.pair[0]["post"]["new"]="0"
        self.pair[1]["log_access_error_codes"]=["MISSING_LOG"]
        self.pair[1]["run_attempt"]=2
        self.reject(self.pair,"FIRST_POSTFLIGHT_MISMATCH")
        self.reject(self.pair,"REPLAY_RUN_OR_JOB_UNVERIFIED")


if __name__=="__main__":
    unittest.main()
