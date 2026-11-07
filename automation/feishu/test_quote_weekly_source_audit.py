#!/usr/bin/env python3
"""Offline synthetic tests for read-only source audit."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
import quote_weekly_source_audit as audit

class QuoteWeeklyAuditTests(unittest.TestCase):
    def source(self, export_date="2026-11-06 10:00:00 KST"):
        return {
          "dedup":[["Approval KST","SFDC Record ID","Week Status","Approval Evidence",
                    "Approved AND Active","Quote Status","Currency","Verified Amount kUSD"],
                   ["2026-11-05 13:00:00","a0P"+"A"*12,"2026-10-30 ~ 2026-11-05",
                    "APPROVED_TEXT","UNVERIFIED","UNKNOWN","","12.3"]],
          "weekly":[["week_start","quotation_approvals"],["2026-10-30","0"]],
          "export":[["Salesforce Record ID","Exported At KST"],
                    ["a0P"+"A"*12,export_date]],
          "legacy":[["week_start","salesforce_record_id"],
                    ["2026-10-09","a0P"+"B"*12]],
          "cssweekly":[["week_start","quotation_count"],["2026-10-09","15"]],
        }
    def now(self):
        return dt.datetime(2026,11,7,15,0,tzinfo=ZoneInfo("Asia/Seoul"))
    def test_four_completed_friday_to_thursday_weeks(self):
        self.assertEqual(audit.last_four_completed(self.now().date()),
            ["2026-10-30","2026-10-23","2026-10-16","2026-10-09"])
        self.assertEqual(audit.evidence_week("2026-11-05 13:00:00"),
                         "2026-10-30")
    def test_nonblank_amount_is_not_verified_without_active_evidence(self):
        result=audit.summarize(self.source(),now=self.now())
        latest=result["weeks"][-1]
        self.assertEqual(latest["approval_rows"],1)
        self.assertEqual(latest["distinct_salesforce_ids"],1)
        self.assertEqual(latest["sfdc_weekly_count"],0)
        self.assertEqual(latest["nonblank_money_cells"],1)
        self.assertEqual(latest["eligible_value_rows"],0)
        self.assertIn("WEEKLY_SOURCE_COUNT_DIVERGENCE",result["blockers"])
        self.assertIn("MONETARY_CELLS_LACK_CURRENT_ACTIVE_PROOF",result["blockers"])
        self.assertTrue(result["source_export_fresh"])
    def test_stale_export_blocks_even_current_active(self):
        data=self.source(export_date="2026-10-24 18:00:08 KST")
        data["dedup"][1][4:7]=["YES","ACTIVE","USD"]
        result=audit.summarize(data,now=self.now())
        self.assertFalse(result["source_export_fresh"])
        self.assertIn("SFDC_QUOTE_EXPORT_STALE_OR_MISSING",result["blockers"])
        self.assertEqual(result["weeks"][-1]["eligible_value_rows"],0)
    def test_duplicate_id_disallowed_and_no_identifier_printed(self):
        data=self.source()
        data["weekly"][1][1]="2"
        data["dedup"].append(list(data["dedup"][1]))
        result=audit.summarize(data,now=self.now())
        row=result["weeks"][-1]
        self.assertEqual(row["duplicate_id_rows"],1)
        self.assertEqual(row["distinct_salesforce_ids"],1)
        self.assertNotIn("a0P"+"A"*12,audit.summary_markdown(result))
    def test_source_requires_exact_header(self):
        self.assertEqual(audit.number("12.3"),12.3)
        self.assertIsNone(audit.number(""))
        self.assertEqual(audit.normalized_id("a0P"+"A"*12+"xyz"),"a0P"+"A"*12)
        with self.assertRaisesRegex(ValueError,"SCHEMA"):
            audit.sheet_rows([["Approval Date"],["2026-11-07"]],["Approval KST"])

if __name__=="__main__":
    unittest.main()
