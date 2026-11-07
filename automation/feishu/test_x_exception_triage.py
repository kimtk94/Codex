#!/usr/bin/env python3
import datetime as dt
import unittest
from x_exception_triage import (
    classify,latest_dated_note,parse_remaining,EXCEPTION_SCHEMA
)
from x_project_lineage import build,LINK_SCHEMAS
from test_x_project_lineage import fixtures

ASOF=dt.date(2026,11,7)
def triage(status="Sample QC",details="",tat="10",remark=""):
    return classify({
        "Project Status":status,"Progression Details":details,
        "Remaining Lead Time-Calendar Days":tat,"remark":remark
    },ASOF)

class XExceptionTriageTests(unittest.TestCase):
    def test_no_reliably_observed_last_update_date(self):
        z=triage("Sample QC","index 261013_LH0050 CML150032090")
        self.assertEqual(z["Note Date Basis"],"NO_DATED_EVENT")
        self.assertIsNone(z["Note Age Days"])
        self.assertEqual(z["Dated Note Age Flag"],"NO_DATED_NOTE")
        self.assertNotIn("DATED_NOTE_30D",z["Exception Codes"])
    def test_dated_note_text_is_weak_signal_only(self):
        z=triage("Resending Sample","9.11--sample, 9.14-2P4F-等回复",tat="")
        self.assertEqual(z["Last Dated Note"],"2026-09-14")
        self.assertEqual(z["Note Age Days"],54)
        self.assertEqual(z["Note Date Basis"],"YEAR_INFERRED_FROM_SNAPSHOT")
        self.assertEqual(z["Dated Note Age Flag"],"DATED_NOTE_30D_PLUS")
        self.assertIn("DATED_NOTE_30D",z["Exception Codes"])
        self.assertEqual(z["Exception Priority"],"P1_REVIEW")
        self.assertIn("실제 마지막 수정일",z["Suggested Check"])
    def test_tat_negative_and_abnormal_are_urgent_but_not_proved_overdue(self):
        neg=triage("Resending Sample","2026-09-15 recheck",tat="-23")
        self.assertEqual(neg["TAT Risk"],"TAT_NEGATIVE")
        self.assertEqual(neg["Exception Priority"],"P0_URGENT")
        self.assertIn("실제 약속 TAT",neg["Suggested Check"])
        abnormal=triage("Abnormal","10.21-产率很低-重定量加测",tat="5")
        self.assertEqual(abnormal["Exception Priority"],"P0_URGENT")
        self.assertIn("QC_RISK_NOTE",abnormal["Exception Codes"])
    def test_raw_status_case_insensitive(self):
        self.assertIn("WAITING_SEQUENCING",
            triage("Waiting Sequencing","10.14-库检完成未上机")["Exception Codes"])
        self.assertIn("START_CONFIRM_PENDING",
            triage("Awaiting Feedback(Project Start)","10.5-等回复",tat="")["Exception Codes"])
    def test_bif_po_and_statement_are_separate(self):
        self.assertIn("BIF_PENDING",
            triage("Awaiting Feedback(BI form)","10.14-跟进")["Exception Codes"])
        self.assertIn("PO_PAYMENT_PENDING",
            triage("Waiting PO/payment","10.9-无PO",tat="0")["Exception Codes"])
        self.assertIn("STATEMENT_PENDING",
            triage("Waiting for Settlement","10.17-final")["Exception Codes"])
    def test_settled_label_is_not_receipt_verification(self):
        z=triage("Settled","9.9-add seq",tat="-30")
        self.assertNotIn("TAT_NEGATIVE",z["Exception Codes"])
        self.assertEqual(z["Exception Priority"],"P2_WATCH")
        self.assertIn("증빙과 별개",z["Primary Reason"])
    def test_no_arbitrary_inference_from_incomplete_date(self):
        found,basis=latest_dated_note("261013_LH001 2026-13-42 10.45",ASOF)
        self.assertIsNone(found)
        self.assertEqual(basis,"NO_DATED_EVENT")
        found,basis=latest_dated_note("2026-10-21 completed",ASOF)
        self.assertEqual(found,dt.date(2026,10,21))
        self.assertEqual(basis,"EXPLICIT_DATE_IN_NARRATIVE")
    def test_future_month_uses_last_year_only_as_inference(self):
        found,basis=latest_dated_note("12.12-older note",ASOF)
        self.assertEqual(found,dt.date(2025,12,12))
        self.assertEqual(basis,"YEAR_INFERRED_FROM_SNAPSHOT")
    def test_empty_tat_never_assumed_zero(self):
        self.assertIsNone(parse_remaining(""))
        self.assertEqual(parse_remaining("-23"),-23)
        self.assertEqual(parse_remaining("0"),0)
        self.assertIsNone(parse_remaining("1 week"))
    def test_traces_are_scoped_to_real_x(self):
        base=fixtures()
        base["Feishu Source Manifest"]=[{"Source":"Online-Project",
                                         "Source Date":"2026-11-07"}]
        base["Feishu Latest Online"][0].update({
            "Project Status":"Abnormal",
            "Remaining Lead Time-Calendar Days":"-23",
            "Progression Details":"9.14-2P4F-等回复"
        })
        rows,audit=build(base)
        x=rows["X Project Registry"][0]
        self.assertEqual(x["Exception Priority"],"P0_URGENT")
        self.assertEqual(x["Remaining TAT Days"],-23.0)
        self.assertEqual(x["Last Dated Note"],"2026-09-14")
        self.assertEqual(x["Note Age Days"],54)
        self.assertEqual(audit["my_attention_urgent"],1)
        self.assertTrue(set(x).issubset({c for c,_ in LINK_SCHEMAS["X Project Registry"]}))
        self.assertGreaterEqual(len(EXCEPTION_SCHEMA),10)
    def test_age_is_not_progress_rank_or_claim_of_stall(self):
        z=triage("Sample QC","10.9-sample QC",tat="15")
        self.assertEqual(z["Exception Priority"],"P2_WATCH")
        self.assertNotIn("진행 지연 확정",str(z))
        self.assertNotIn("Progress %",z)
if __name__=="__main__":unittest.main()
