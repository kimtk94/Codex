#!/usr/bin/env python3
"""Source evidence and numeric correctness tests for Feishu KPI pages."""
import unittest

import sales_metrics_sync as m
from qq_mail_ingest import SafeError


class MetricsTests(unittest.TestCase):
    def test_sif_number_alone_is_not_submission(self):
        source={
            "CSS Project Dashboard":[{"project_id":"AMEA2026012345","institution":"U",
                "customer_name":"Customer","current_stage":"Sample QC","progress_percent":"20"}],
            "CSS Contract-SIF Tracker":[{
                "record_id":"123","Institution":"U","AMEA No.":"AMEA2026012345",
                "SIF No.":"SIF123","Status":"Contract Ready",
                "sif_first_seen_at":"", "Contract No.":"CX",
            }],
            "BI Project Lifecycle Overview":[],
        }
        row=m.project_rows(source)[0]
        self.assertEqual(row["SIF State"],"NUMBER_ONLY_REVIEW")
        self.assertEqual(row["SIF Approved"],"NOT_VERIFIED")
        source["CSS Contract-SIF Tracker"][0]["sif_first_seen_at"]="2026-11-04"
        row=m.project_rows(source)[0]
        self.assertEqual(row["SIF State"],"SUBMITTED_EVIDENCE")

    def test_sif_approved_is_separate_evidence(self):
        source={
            "CSS Project Dashboard":[{"project_id":"AMEA2026012345","institution":"U",
                "customer_name":"Customer","current_stage":"Sample QC","progress_percent":"20"}],
            "CSS Contract-SIF Tracker":[{
                "record_id":"124","AMEA No.":"AMEA2026012345","SIF No.":"SIF123",
                "Status":"SIF Approved","sif_first_seen_at":"2026-11-01"
            }],
            "BI Project Lifecycle Overview":[{"AMEA":"AMEA2026012345",
                "CSS Progress %":"30","Feishu Status (latest)":"Sample QC"}]
        }
        row=m.project_rows(source)[0]
        self.assertEqual(row["SIF State"],"APPROVED")
        self.assertEqual(row["Progress %"],20.0)

    def test_monthly_dedup_and_vat_separated(self):
        source={
            "Revenue Invoice Base":[
                {"Invoice No":"I1","Year-Month":"2026-10",
                 "Revenue KRW (Tax Invoice)":"1,100","Net Revenue KRW (VAT excl; per invoice)":"1,000"},
                {"Invoice No":"I1","Year-Month":"2026-10",
                 "Revenue KRW (Tax Invoice)":"1,100","Net Revenue KRW (VAT excl; per invoice)":"1,000"},
                {"Invoice No":"I2","Year-Month":"2026-10",
                 "Revenue KRW (Tax Invoice)":"2,200","Net Revenue KRW (VAT excl; per invoice)":"2,000"},
            ],
            "CSS Invoice Monthly Summary":[{"invoice_month":"2026-10",
                "invoice_count":"2","total_amount_krw":"3,300 KRW"}],
        }
        row=m.monthly_rows(source)[0]
        self.assertEqual(row["Invoice Count"],2)
        self.assertEqual(row["Tax Invoice KRW Incl VAT"],3300)
        self.assertEqual(row["Net Revenue KRW Ex VAT"],3000)
        self.assertEqual(row["Coverage Status"],"SOURCE_SCOPE_MATCH")

    def test_conflicting_invoice_key_blocks_all(self):
        source={
            "Revenue Invoice Base":[
                {"Invoice No":"I1","Year-Month":"2026-10",
                 "Revenue KRW (Tax Invoice)":"1100","Net Revenue KRW (VAT excl; per invoice)":"1000"},
                {"Invoice No":"I1","Year-Month":"2026-10",
                 "Revenue KRW (Tax Invoice)":"2200","Net Revenue KRW (VAT excl; per invoice)":"2000"},
            ],
            "CSS Invoice Monthly Summary":[],
        }
        with self.assertRaisesRegex(SafeError,"MONTHLY_CONFLICTING_INVOICE_ID"):
            m.monthly_rows(source)

    def test_quote_value_partial_not_claimed_complete(self):
        source={
            "SFDC Weekly Overview":[{"week_start":"2026-10-30","week_end":"2026-11-05",
                "quotation_approvals":"3","approvals_created_in_week":"2",
                "weekly_basis":"FRI_THU_IN_PROGRESS","krw_per_usd":"1500"}],
            "Quotation Approval List":[{"week_start":"2026-10-30",
                "salesforce_record_id":"SF001","quotation_id":"QID1"}],
            "Quote Portfolio":[{"Salesforce Quote ID (18)":"SF001","Quote QID":"QID1",
                "Active":"YES","Quote USD":"1000"}],
        }
        row=m.weekly_rows(source)[0]
        self.assertEqual(row["Verified Amount Quote Count"],1)
        self.assertEqual(row["Unmatched Amount Count"],2)
        self.assertEqual(row["Amount Status"],"VERIFIED_PARTIAL")
        self.assertEqual(row["Verified Quote Value KRW FX"],1500000)
        self.assertEqual(row["Verified Quote Value K USD"],1.0)

    def test_no_quote_price_cannot_be_zero(self):
        source={
            "SFDC Weekly Overview":[{"week_start":"2026-10-30","week_end":"2026-11-05",
                "quotation_approvals":"3","approvals_created_in_week":"3","krw_per_usd":"1500"}],
            "Quotation Approval List":[],
            "Quote Portfolio":[],
        }
        row=m.weekly_rows(source)[0]
        self.assertEqual(row["Amount Status"],"NO_QUOTE_VALUE")
        self.assertNotIn("Verified Quote Value KRW FX",row)

    def test_equivalent_numeric_and_text_ignores_timestamp(self):
        old={"Invoice Count":2.0,"Source Key":[{"text":"INVOICE:2026-10"}],
             "Last Sync KST":"old"}
        new={"Invoice Count":2,"Source Key":"INVOICE:2026-10","Last Sync KST":"new"}
        self.assertTrue(m.equivalent(old,new))
        self.assertFalse(m.equivalent(old,{**new,"Invoice Count":3}))


if __name__=="__main__":
    unittest.main()
