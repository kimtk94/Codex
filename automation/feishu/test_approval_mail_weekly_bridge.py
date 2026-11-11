#!/usr/bin/env python3
"""Offline synthetic tests for 11/11 KST approved Quote mail backfill."""
import copy
import datetime as dt
import unittest
from unittest import mock
from zoneinfo import ZoneInfo
from approval_mail_weekly_bridge import supplement,stamp

NOW=dt.datetime(2026,11,11,18,0,0,tzinfo=ZoneInfo("Asia/Seoul"))
def src():
    qids=["QID-2026-11-11-413603","QID-2026-11-11-413624","QID-2026-11-11-413635"]
    sids=["a0PTK000011pi5x","a0PTK000011r33X","a0PTK000011rRFb"]
    oids=["Opp-2026-11-11-294438","Opp-2026-10-19-290046","Opp-2026-11-11-294449"]
    times=["2026-11-11T02:35:19+00:00","2026-11-11T02:39:50+00:00",
           "2026-11-11T03:35:10+00:00"]
    return {
      "Quote Approval Dedup":[{"Approval KST":"2026-11-10 16:30:23",
                               "SFDC Record ID":"a0PTK000011krLC",
                               "Quotation Name":"QID-2026-11-10-413222"}],
      "Quotation Approval Auto":[{
        "approval_mail_at_kst":times[i],"quotation_id":"AMEA20261111"+str(i+10),
        "quotation_name":qids[i],"salesforce_record_id":sids[i],
        "approval_evidence":"APPROVED_TEXT","review_status":"APPROVED",
        "ingest_key":"INBOX:TEST:"+str(i)} for i in range(3)],
      "SFDC Email Quotation Raw":[{"SFDC Quotation ID":qids[i],"Opportunity ID":oids[i]}
                                   for i in range(3)],
      "SFDC Email Opportunities Raw":[{"Opportunity ID":oids[i],
                                       "Opportunity Owner":"Kim Taehoon"} for i in range(3)],
    }

class MailApprovalBridgeTests(unittest.TestCase):
    def test_converts_utc_to_kst(self):
        self.assertEqual(stamp("2026-11-11T03:35:10+00:00").strftime("%Y-%m-%d %H:%M:%S"),
                         "2026-11-11 12:35:10")
    def test_adds_three_verified_my_quotations_without_source_mutation(self):
        source=src()
        original=copy.deepcopy(source["Quote Approval Dedup"])
        with mock.patch("approval_mail_weekly_bridge.validate_source",return_value="SOURCE_QQ_REPORT_VERIFIED"):
            rows,stats=supplement(source,NOW)
        self.assertEqual(stats["added"],3)
        self.assertEqual(len(rows),4)
        self.assertEqual(source["Quote Approval Dedup"],original)
        latest=[r for r in rows if r["Approval KST"].startswith("2026-11-11")]
        self.assertEqual(len(latest),3)
        self.assertTrue(all(r["Week Status"]=="2026-11-06 ~ 2026-11-12" for r in latest))
        self.assertTrue(all(r["Quote Status"]=="UNKNOWN" for r in latest))
        self.assertTrue(all(not r["Verified Amount kUSD"] for r in latest))
    def test_repeat_does_not_double_count(self):
        source=src()
        with mock.patch("approval_mail_weekly_bridge.validate_source",return_value="SOURCE_QQ_REPORT_VERIFIED"):
            first,_=supplement(source,NOW)
            source["Quote Approval Dedup"]=first
            second,stats=supplement(source,NOW)
        self.assertEqual(len(second),len(first))
        self.assertEqual(stats["added"],0)
    def test_not_my_opportunity_is_skipped(self):
        source=src()
        source["SFDC Email Opportunities Raw"][1]["Opportunity Owner"]="Someone Else"
        with mock.patch("approval_mail_weekly_bridge.validate_source",return_value="SOURCE_QQ_REPORT_VERIFIED"):
            rows,stats=supplement(source,NOW)
        self.assertEqual(stats["added"],2)
    def test_email_only_does_not_override_unverified_report(self):
        source=src()
        with mock.patch("approval_mail_weekly_bridge.validate_source",return_value="WITHHELD_3REPORT_STALE"):
            rows,stats=supplement(source,NOW)
        self.assertEqual(stats["added"],0)
        self.assertEqual(len(rows),1)
    def test_duplicate_id_conflict_blocks(self):
        source=src()
        source["Quote Approval Dedup"].append({
          "SFDC Record ID":"a0PTK000011pi5x","Quotation Name":"QID-2026-11-11-UNSAFE"})
        with mock.patch("approval_mail_weekly_bridge.validate_source",return_value="SOURCE_QQ_REPORT_VERIFIED"):
            with self.assertRaisesRegex(RuntimeError,"CONFLICT"):
                supplement(source,NOW)
    def test_mail_without_approval_evidence_is_not_counted(self):
        source=src()
        source["Quotation Approval Auto"][0]["approval_evidence"]="ALERT_ONLY"
        with mock.patch("approval_mail_weekly_bridge.validate_source",return_value="SOURCE_QQ_REPORT_VERIFIED"):
            _,stats=supplement(source,NOW)
        self.assertEqual(stats["added"],2)

if __name__=="__main__":unittest.main()
