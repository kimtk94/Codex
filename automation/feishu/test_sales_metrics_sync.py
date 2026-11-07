#!/usr/bin/env python3
"""Source evidence and numeric correctness tests for Feishu KPI pages."""
import unittest
from unittest import mock

import sales_metrics_sync as m
from qq_mail_ingest import SafeError


class MetricsTests(unittest.TestCase):
    def test_payment_views_are_exact_owner_scoped(self):
        definitions=m.VIEW_SPECS["Project Progress Board"]
        views={row[0]:row for row in definitions}
        for name,lane in (("완료 · 결제 관리","PAYMENT_FOLLOWUP"),
                          ("결제 완료 · 보관","PAID_ARCHIVED")):
            self.assertEqual(views[name][1:],
                ("Workflow Lane",lane,"Payment Owner Scope","MY_VERIFIED"))
        self.assertIn(("Payment Owner Scope",1),
                      m.SCHEMAS["Project Progress Board"])

    def test_sif_number_alone_is_not_submission(self):
        source={
            "CSS Project Dashboard":[{"project_id":"AMEA2026012345","institution":"U",
                "customer_name":"Customer","current_stage":"Sample QC","progress_percent":"20"}],
            "CSS Contract-SIF Tracker":[{
                "record_id":"123","project_id":"AMEA2026012345","Institution":"U","AMEA No.":"AMEA2026012345",
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
                "record_id":"124","project_id":"AMEA2026012345","AMEA No.":"AMEA2026012345","SIF No.":"SIF123",
                "Status":"SIF Approved","sif_first_seen_at":"2026-11-01"
            }],
            "BI Project Lifecycle Overview":[{"AMEA":"AMEA2026012345",
                "CSS Progress %":"30","Feishu Status (latest)":"Sample QC"}]
        }
        row=m.project_rows(source)[0]
        self.assertEqual(row["SIF State"],"APPROVED")
        self.assertEqual(row["Progress %"],20.0)

    def test_prepayment_waives_sif_and_submitted_advances(self):
        pid="AMEA2026100751"
        base={"CSS Project Dashboard":[{"project_id":pid,"current_stage":"SIF requested",
             "progress_percent":"10","latest_action_required":"Please submit SIF"}],
              "CSS Contract-SIF Tracker":[{"project_id":pid,"Prepayment":"TRUE",
               "Status":"SIF requested","Next Action":"SIF 제출 확인"}],
              "BI Project Lifecycle Overview":[],"Feishu Latest Prepayments":[]}
        r=m.project_rows(base)[0]
        self.assertEqual(r["SIF State"],"WAIVED_PREPAYMENT")
        self.assertIn("SIF 제출 필수 아님",r["Next Action"])
        base["CSS Contract-SIF Tracker"][0].update(
            {"Status":"SIF received","sif_first_seen_at":"2026-11-06"})
        r=m.project_rows(base)[0]
        self.assertEqual(r["SIF State"],"SUBMITTED_EVIDENCE")
        self.assertIn("후속 공정",r["Next Action"])

    def test_exact_quotation_prepayment_waives_without_css_tracker(self):
        pid="AMEA2026100751"
        data={"CSS Project Dashboard":[{"project_id":pid,"current_stage":"SIF requested",
             "progress_percent":"10","latest_action_required":"SIF 제출 확인"}],
              "CSS Contract-SIF Tracker":[],"BI Project Lifecycle Overview":[],
              "Feishu Latest Prepayments":[{"Quotation Number":pid}]}
        r=m.project_rows(data)[0]
        self.assertEqual(r["SIF State"],"WAIVED_PREPAYMENT")
        self.assertIn("SIF 제출 필수 아님",r["Next Action"])

    def test_board_unchanged_does_not_repeat_405_row_readback(self):
        row={"Source Key":"PROJECT:AMEA2026100751","AMEA":"AMEA2026100751",
             "Progress %":40,"Quote Full Name":"Full Quote"}
        old={"record_id":"r1","fields":{**row,"Last Sync KST":"previous"}}
        with mock.patch.object(m,"list_all",return_value=[old]) as listing, mock.patch.object(m,"api") as api:
            result=m.sync_board_table("token","/tables/t1",[row])
        self.assertEqual(result,(0,0,1))
        listing.assert_called_once()
        api.assert_not_called()

    def test_transient_503_readback_retries_but_bad_schema_does_not(self):
        with mock.patch.object(m,"list_all",side_effect=[
                SafeError("project_board_readback_HTTP_503"),[{"record_id":"r1"}]
             ]) as listing,mock.patch.object(m.time,"sleep") as sleep:
            values=m.board_list_with_retry("token","/tables/t","project_board_readback")
        self.assertEqual(len(values),1)
        self.assertEqual(listing.call_count,2)
        sleep.assert_called_once()
        with mock.patch.object(m,"list_all",side_effect=SafeError("SHEETS_SCHEMA_MISMATCH")) as listing,\
             mock.patch.object(m.time,"sleep") as sleep:
            with self.assertRaisesRegex(SafeError,"SCHEMA_MISMATCH"):
                m.board_list_with_retry("token","/tables/t","project_board_readback")
            listing.assert_called_once()
            sleep.assert_not_called()

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
        self.assertEqual(row["Net Revenue M KRW"],0.003)
        self.assertEqual(row["Coverage Status"],"SOURCE_SCOPE_MATCH")

    def test_integer_field_formatter_only_touches_count_fields(self):
        fields=[{"field_name":name,"field_id":"fld"+str(i),"type":2,
                 "property":{"formatter":"0.0"},"ui_type":"Number"}
                for i,name in enumerate(sorted(
                    m.COUNT_FIELD_FORMATS["Weekly Quote KPI"]))]
        calls=[]
        def fake_api(method,url,token,data,action):
            calls.append((method,url,data,action))
            return {"field":{"field_name":data["field_name"],
                             "property":data["property"]}}
        updated=[{**r,"property":{"formatter":"0"}} for r in fields]
        with mock.patch.object(m,"api",side_effect=fake_api), \
             mock.patch.object(m,"list_all",return_value=updated):
            m.ensure_integer_field_display("tok","/tables/t",
                                           "Weekly Quote KPI",fields)
        self.assertEqual(len(calls),4)
        self.assertTrue(all(c[0]=="PUT" and
                            c[2]["property"]=={"formatter":"0"}
                            for c in calls))
        self.assertTrue(all("Value" not in c[2]["field_name"]
                            for c in calls))
        with mock.patch.object(m,"api") as mutate, \
             mock.patch.object(m,"list_all",return_value=updated):
            m.ensure_integer_field_display("tok","/tables/t",
                "Weekly Quote KPI",updated)
            mutate.assert_not_called()

    def test_money_units_and_integer_display_without_mutating_raw(self):
        self.assertEqual(m.scaled_m_krw(125000000),125)
        self.assertIsInstance(m.scaled_m_krw(125000000),int)
        self.assertEqual(m.scaled_m_krw(125500000),125.5)
        self.assertEqual(m.scaled_m_krw(12345678),12.3457)
        self.assertEqual(m.scaled_k_usd(39000),39)
        self.assertEqual(m.scaled_k_usd(39100),39.1)
        self.assertEqual(m.scaled_k_usd(1000),1)
        self.assertIsInstance(m.scaled_k_usd(1000),int)
        self.assertIn(("Net Revenue M KRW",2),m.SCHEMAS["Monthly Tax Invoice"])
        self.assertIn(("Verified Quote Value M KRW FX",2),m.SCHEMAS["Weekly Quote KPI"])
        self.assertIn(("Invoice Gross M KRW",2),m.SCHEMAS["Project Progress Board"])
        self.assertIn(("Outstanding Balance M KRW",2),m.SCHEMAS["Project Progress Board"])

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

    def test_korea_chart_last_four_completed_and_oct_nov_labels(self):
        fridays=["2026-10-02","2026-10-09","2026-10-16",
                 "2026-10-23","2026-10-30","2026-11-06"]
        source={
            "SFDC Weekly Overview":[{
                "week_start":week,
                "week_end":(m.dt.date.fromisoformat(week)+
                            m.dt.timedelta(days=6)).isoformat(),
                "weekly_basis":"FRI_THU_IN_PROGRESS" if week=="2026-11-06"
                               else "FRI_THU_CSS_EXISTING",
                "quotation_approvals":"5",
                "approvals_created_in_week":"4",
                "krw_per_usd":"1500",
            } for week in fridays],
            "Quotation Approval List":[],
            "Quote Portfolio":[],
        }
        rows=m.weekly_rows(source)
        shown=[r for r in rows if r["Chart Window"]=="RECENT_4_COMPLETED"]
        self.assertEqual(len(shown),4)
        self.assertEqual([r["Chart Week Label"] for r in sorted(
            shown,key=lambda r:r["Week Start"])],
            ["10/12","10/19","10/26","11/02"])
        self.assertNotIn("2026-11-06",[r["Week Start"] for r in shown])
        self.assertEqual(rows[0]["Chart Window"],"HISTORY")
        self.assertEqual(rows[0]["Chart Week Label"],"11/09")
        self.assertEqual(rows[-1]["Chart Window"],"HISTORY")
        self.assertTrue(all(r["Approved Quote Count"]==5 for r in shown))
        self.assertTrue(all("Verified Quote Value K USD" not in r for r in shown))
    def test_chart_label_requires_friday_start(self):
        self.assertEqual(m.quote_chart_week_label("2026-10-30"),"11/02")
        self.assertEqual(m.quote_chart_week_label("2026-10-09"),"10/12")
        self.assertEqual(m.quote_chart_week_label("2026-11-06"),"11/09")
        self.assertEqual(m.quote_chart_week_label("2026-11-07"),"")
        self.assertEqual(m.quote_chart_week_label("2026-12-25"),"12/28")
        self.assertEqual(m.quote_chart_week_label("2027-01-01"),"01/04")
        self.assertEqual(m.quote_chart_week_label("not-a-date"),"")

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
        self.assertEqual(row["Verified Quote Value M KRW FX"],1.5)
        self.assertEqual(row["Verified Quote Value K USD"],1)
        self.assertIsInstance(row["Verified Quote Value K USD"],int)

    def test_sf_15_18_id_join_with_case_sensitivity(self):
        sf15="a0PAbCdEfGhIjKl"
        sf18=sf15+"XYZ"
        source={
            "SFDC Weekly Overview":[{"week_start":"2026-10-30",
                "week_end":"2026-11-05","quotation_approvals":"1",
                "approvals_created_in_week":"1","weekly_basis":"FRI_THU",
                "krw_per_usd":"1500"}],
            "Quotation Approval List":[{"week_start":"2026-10-30",
                "salesforce_record_id":sf15,"quotation_id":"AMEA2026012345"}],
            "Quote Portfolio":[{"Salesforce Quote ID (18)":sf18,
                "Quote QID":"QID-OTHER","Active":"YES","Quote USD":"2000"}],
        }
        self.assertEqual(m.salesforce_id15(sf18),sf15)
        row=m.weekly_rows(source)[0]
        self.assertEqual(row["Amount Status"],"VERIFIED_ALL")
        self.assertEqual(row["Verified Amount Quote Count"],1)
        self.assertEqual(row["Verified Quote Value KRW FX"],3000000)
        source["Quotation Approval List"][0]["salesforce_record_id"]=sf15.swapcase()
        row=m.weekly_rows(source)[0]
        self.assertEqual(row["Amount Status"],"NO_QUOTE_VALUE")
        self.assertNotIn("Verified Quote Value KRW FX",row)

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
