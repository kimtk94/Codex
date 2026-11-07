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
        self.assertEqual(len(calls),len(m.COUNT_FIELD_FORMATS['Weekly Quote KPI']))
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
        shown=[r for r in rows if r["Chart Window"]=="RECENT_4_PLUS_CURRENT"]
        self.assertEqual(len(shown),5)
        self.assertEqual([r["Chart Week Label"] for r in sorted(
            shown,key=lambda r:r["Week Start"])],
            ["Oct W2","Oct W3","Oct W4","Nov W1","Nov W2 · 진행 중"])
        self.assertIn("2026-11-06",[r["Week Start"] for r in shown])
        self.assertEqual(rows[0]["Chart Window"],"RECENT_4_PLUS_CURRENT")
        self.assertEqual(rows[0]["Chart Week Label"],"Nov W2 · 진행 중")
        self.assertEqual(rows[-1]["Chart Window"],"HISTORY")
        self.assertTrue(all(r["Approved Quote Count"]==5 for r in shown))
        self.assertTrue(all(r["Verified Quote Value K USD"] is None for r in shown))
        self.assertTrue(all(r["Amount Status"]=="WITHHELD_QUOTE_OBJECT_EXPORT_MISSING" for r in shown))
    def test_chart_label_requires_friday_start(self):
        self.assertEqual(m.quote_chart_week_label("2026-10-30"),"Nov W1")
        self.assertEqual(m.quote_chart_week_label("2026-10-09"),"Oct W2")
        self.assertEqual(m.quote_chart_week_label("2026-11-06"),"Nov W2")
        self.assertEqual(m.quote_chart_week_label("2026-11-07"),"")
        self.assertEqual(m.quote_chart_week_label("not-a-date"),"")

    def _verified_quote_fixture(self, count=3):
        sf15="a0PAbCdEfGhIjKl"
        return {"SFDC Weekly Overview":[{"week_start":"2026-10-30",
                    "week_end":"2026-11-05","quotation_approvals":str(count),
                    "approvals_created_in_week":"2","weekly_basis":"FRI_THU_CSS_EXISTING",
                    "krw_per_usd":"1500"}],
                "Quote Approval Dedup":[{"Approval KST":"2026-11-05 12:00:00",
                    "SFDC Record ID":sf15,"Quotation Name":"Quotation"}],
                "SFDC Quote Export":[{"Salesforce Record ID":sf15+"XYZ",
                    "IsActive":"1","Exclude Tax After Discount USD":"1000",
                    "CurrencyIsoCode":"USD","Opportunity ID":"006OPP",
                    "Exported At KST":"2026-11-07 12:00:08 KST"}],
                "SFDC Email Opportunities Raw":[{"Opportunity ID":"006OPP",
                    "Opportunity Owner":"Kim Taehoon"}],
                "SFDC Email Ingest Audit":[{"Entity":"Opportunities",
                    "Source Received KST":"2026-11-07 12:00:24 KST",
                    "State":"STAGED_NOT_PROMOTED"}]}
    def _now(self):
        return m.dt.datetime(2026,11,7,16,0,tzinfo=m.KST)

    def test_count_survives_stale_quote_export_and_old_quote_portfolio(self):
        source=self._verified_quote_fixture(count=1)
        source["SFDC Quote Export"][0]["Exported At KST"]="2026-10-24 18:00:08 KST"
        source["Quote Portfolio"]=[{"Salesforce Quote ID (18)":"a0PAbCdEfGhIjKlXYZ",
                                   "Active":"ACTIVE","Quote USD":"2500000"}]
        row=m.weekly_rows(source,now=self._now())[0]
        self.assertEqual(row["Approved Quote Count"],1)
        self.assertEqual(row["Verified Amount Quote Count"],0)
        self.assertEqual(row["Unmatched Amount Count"],1)
        self.assertEqual(row["Amount Status"],"WITHHELD_QUOTE_OBJECT_EXPORT_STALE")
        self.assertIsNone(row["Verified Quote Value KRW FX"])
        self.assertIsNone(row["Verified Quote Value M KRW FX"])
        self.assertIsNone(row["Verified Quote Value K USD"])

    def test_quote_object_partial_and_money_value(self):
        source=self._verified_quote_fixture(count=3)
        # Need complete approval evidence for the 3 weekly approved records.
        for char in ("A","B"):
            sid="a0P"+char*12
            source["Quote Approval Dedup"].append(
                {"Approval KST":"2026-11-05 13:00:00","SFDC Record ID":sid})
        row=m.weekly_rows(source,now=self._now())[0]
        self.assertEqual(row["Verified Amount Quote Count"],1)
        self.assertEqual(row["Unmatched Amount Count"],2)
        self.assertEqual(row["Amount Status"],"VERIFIED_PARTIAL")
        self.assertEqual(row["Verified Quote Value KRW FX"],1500000)
        self.assertEqual(row["Verified Quote Value M KRW FX"],1.5)
        self.assertEqual(row["Verified Quote Value K USD"],1)
        self.assertIsInstance(row["Verified Quote Value K USD"],int)

    def test_sf_15_18_id_join_with_case_sensitivity(self):
        source=self._verified_quote_fixture(count=1)
        sf15=source["Quote Approval Dedup"][0]["SFDC Record ID"]
        self.assertEqual(m.salesforce_id15(sf15+"XYZ"),sf15)
        row=m.weekly_rows(source,now=self._now())[0]
        self.assertEqual(row["Amount Status"],"VERIFIED_ALL")
        self.assertEqual(row["Verified Amount Quote Count"],1)
        self.assertEqual(row["Verified Quote Value KRW FX"],1500000)
        source["Quote Approval Dedup"][0]["SFDC Record ID"]=sf15.swapcase()
        row=m.weekly_rows(source,now=self._now())[0]
        self.assertEqual(row["Amount Status"],"WITHHELD_APPROVAL_COUNT_MISMATCH")
        self.assertIsNone(row["Verified Quote Value KRW FX"])

    def test_incomplete_approvals_and_wrong_owner_cannot_publish_money(self):
        source=self._verified_quote_fixture(count=2)
        row=m.weekly_rows(source,now=self._now())[0]
        self.assertEqual(row["Amount Status"],"WITHHELD_APPROVAL_COUNT_MISMATCH")
        self.assertIsNone(row["Verified Quote Value K USD"])
        source["SFDC Weekly Overview"][0]["quotation_approvals"]="1"
        source["SFDC Email Opportunities Raw"][0]["Opportunity Owner"]="Other Sales"
        row=m.weekly_rows(source,now=self._now())[0]
        self.assertEqual(row["Amount Status"],"NO_QUOTE_VALUE")
        self.assertEqual(row["Unmatched Amount Count"],1)
        self.assertIsNone(row["Verified Quote Value K USD"])

    def test_stale_owner_snapshot_fails_closed(self):
        source=self._verified_quote_fixture(count=1)
        source["SFDC Email Ingest Audit"][0]["Source Received KST"]="2026-10-24 12:00:24 KST"
        row=m.weekly_rows(source,now=self._now())[0]
        self.assertEqual(row["Amount Status"],"WITHHELD_OPPORTUNITY_OWNER_SNAPSHOT_STALE")
        self.assertIsNone(row["Verified Quote Value K USD"])

    def test_no_quote_price_cannot_be_zero(self):
        source={"SFDC Weekly Overview":[{"week_start":"2026-10-30",
                    "week_end":"2026-11-05","quotation_approvals":"3",
                    "approvals_created_in_week":"3","krw_per_usd":"1500"}],
                "Quote Approval Dedup":[]}
        row=m.weekly_rows(source,now=self._now())[0]
        self.assertEqual(row["Amount Status"],"WITHHELD_QUOTE_OBJECT_EXPORT_MISSING")
        self.assertEqual(row["Unmatched Amount Count"],3)
        self.assertIsNone(row["Verified Quote Value KRW FX"])


    def test_quote_process_price_calculation_is_separate_from_verified_money(self):
        import test_quote_process_amount as fixture
        source=fixture.finalize(fixture.fixture(count=1))
        source["SFDC Quote Export"]=[]  # stale/missing object does not erase process estimate
        row=m.weekly_rows(source,now=fixture.NOW)[0]
        self.assertEqual(row["Approved Quote Count"],1)
        self.assertEqual(row["Calculated Quote Count"],1)
        self.assertEqual(row["Quote Amount Exception Count"],0)
        self.assertEqual(row["Calculated Quote Value K USD"],0.154)
        self.assertEqual(row["Calculated Quote Value M KRW FX"],0.231)
        self.assertEqual(row["Amount Status"],"PROCESS_PRICE_CALCULATED_COMPLETE")
        self.assertEqual(row["Quote Calculation Source"],
            "PROCESS_PRICE_CALCULATED_COMPLETE / SOURCE_QQ_REPORT_VERIFIED / count=IMMUTABLE_APPROVAL_DEDUP")
        self.assertIsNone(row["Verified Quote Value K USD"])
        self.assertIsNone(row["Verified Quote Value KRW FX"])

    def test_partial_price_with_missing_owner_and_count_kept(self):
        import test_quote_process_amount as fixture
        source=fixture.fixture(count=2)
        source["Quote Approval Dedup"].append({
            "Approval KST":"2026-11-04 12:00:00",
            "SFDC Record ID":"a0P"+"B"*12,
            "Quotation Name":"QID-2026-11-02-45678"})
        source=fixture.finalize(source)
        row=m.weekly_rows(source,now=fixture.NOW)[0]
        self.assertEqual(row["Approved Quote Count"],2)
        self.assertEqual(row["Calculated Quote Count"],1)
        self.assertEqual(row["Quote Amount Exception Count"],1)
        self.assertEqual(row["Amount Status"],"PROCESS_PRICE_CALCULATED_PARTIAL")
        self.assertEqual(row["Calculated Quote Value K USD"],0.154)

    def test_stale_or_bad_quotation_source_wipes_calculated_estimates(self):
        import test_quote_process_amount as fixture
        source=fixture.finalize(fixture.fixture(count=1))
        source["SFDC Email Quotation Raw"][0]["Unit Price USD"]="9999.99"
        row=m.weekly_rows(source,now=fixture.NOW)[0]
        self.assertEqual(row["Approved Quote Count"],1)
        self.assertEqual(row["Calculated Quote Count"],0)
        self.assertEqual(row["Quote Amount Exception Count"],1)
        self.assertIsNone(row["Calculated Quote Value K USD"])
        self.assertIn("WITHHELD_3REPORT_SHA_MISMATCH",row["Quote Calculation Source"])

    def test_monthly_revenue_unchanged_by_quote_process_logic(self):
        # This mutation is read-only and must not alter VAT exclusion logic.
        self.assertEqual(m.currency(m.D("1100")/m.D("1.1")),1000)
        self.assertEqual(m.scaled_m_krw(1000000),1)
        self.assertEqual(m.scaled_k_usd(1000),1)

    def test_zero_approval_period_no_keyerror_and_no_price(self):
        import test_quote_process_amount as fixture
        source=fixture.finalize(fixture.fixture(count=1))
        source["SFDC Weekly Overview"].append({
            "week_start":"2026-11-06","week_end":"2026-11-12",
            "quotation_approvals":"0","approvals_created_in_week":"0",
            "weekly_basis":"FRI_THU_IN_PROGRESS","krw_per_usd":"1500"})
        items={r["Week Start"]:r for r in m.weekly_rows(source,now=fixture.NOW)}
        zero=items["2026-11-06"]
        self.assertEqual(zero["Approved Quote Count"],0)
        self.assertEqual(zero["Calculated Quote Count"],0)
        self.assertEqual(zero["Quote Amount Exception Count"],0)
        self.assertIn("NO_APPROVALS",zero["Quote Calculation Source"])
        self.assertIsNone(zero["Calculated Quote Value K USD"])
        self.assertEqual(zero["Chart Window"],"RECENT_4_PLUS_CURRENT")
        self.assertIn("진행 중",zero["Chart Week Label"])
        self.assertEqual(items["2026-10-30"]["Calculated Quote Count"],1)

    def test_shifted_weekly_count_repaired_from_dedup(self):
        import test_quote_process_amount as fixture
        source=fixture.finalize(fixture.fixture(count=1))
        # The historical Weekly Overview column was one week behind.
        source["SFDC Weekly Overview"][0]["quotation_approvals"]="0"
        source["SFDC Weekly Overview"][0]["approvals_created_in_week"]="0"
        row=m.weekly_rows(source,now=fixture.NOW)[0]
        self.assertEqual(row["Approved Quote Count"],1)
        self.assertEqual(row["Created In Week Count"],1)
        self.assertEqual(row["Calculated Quote Count"],1)
        self.assertEqual(row["Quote Amount Exception Count"],0)
        self.assertIn("count=IMMUTABLE_APPROVAL_DEDUP",row["Quote Calculation Source"])
        self.assertEqual(row["Calculated Quote Value K USD"],0.154)

    def test_corrected_counts_keep_zero_unseen_current_week(self):
        import test_quote_process_amount as fixture
        source=fixture.finalize(fixture.fixture(count=1))
        source["SFDC Weekly Overview"][0]["quotation_approvals"]="0"
        source["SFDC Weekly Overview"].append({
            "week_start":"2026-11-06","week_end":"2026-11-12",
            "quotation_approvals":"0","approvals_created_in_week":"0",
            "weekly_basis":"FRI_THU_IN_PROGRESS","krw_per_usd":"1500"})
        found={r["Week Start"]:r for r in m.weekly_rows(source,now=fixture.NOW)}
        self.assertEqual(found["2026-10-30"]["Approved Quote Count"],1)
        self.assertEqual(found["2026-11-06"]["Approved Quote Count"],0)
        self.assertIsNone(found["2026-11-06"]["Calculated Quote Value K USD"])

    def test_missing_historical_quote_count_is_retained_not_zero(self):
        source={"SFDC Weekly Overview":[{
            "week_start":"2025-04-25","week_end":"2025-05-01",
            "weekly_basis":"FRI_THU_CSS_EXISTING",
            "quotation_approvals":"","approvals_created_in_week":"",
            "krw_per_usd":""}], "Quote Approval Dedup":[],
            "SFDC Quote Export":[]}
        rows=m.weekly_rows(source)
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual(row["Source Key"],"QUOTE:2025-04-25")
        self.assertIsNone(row["Approved Quote Count"])
        self.assertIsNone(row["Quote Amount Exception Count"])
        self.assertIsNone(row["Created In Week Count"])
        self.assertIsNone(row["Calculated Quote Value K USD"])
        self.assertIsNone(row["Verified Quote Value K USD"])
        self.assertEqual(row["Amount Status"],
                         "WITHHELD_WEEKLY_APPROVAL_COUNT_MISSING")
        self.assertIn("Zero must not",row["Evidence"])
        self.assertEqual(row["Chart Window"],"RECENT_4_PLUS_CURRENT")

    def test_95_week_coverage_survives_ten_blank_count_slots(self):
        first=m.dt.date(2025,1,10)
        weeks=[]
        for n in range(95):
            start=first+m.dt.timedelta(days=7*n)
            week=start.isoformat()
            weeks.append({"week_start":week,
                          "week_end":(start+m.dt.timedelta(days=6)).isoformat(),
                          "weekly_basis":"FRI_THU_CSS_EXISTING",
                          "quotation_approvals":"" if n in set(range(0,10)) else "2",
                          "approvals_created_in_week":"",
                          "krw_per_usd":"1500"})
        source={"SFDC Weekly Overview":weeks,
                "Quote Approval Dedup":[],"SFDC Quote Export":[]}
        rows=m.weekly_rows(source)
        self.assertEqual(len(rows),95)
        self.assertEqual(sum(r["Approved Quote Count"] is None for r in rows),10)
        self.assertEqual(sum(r["Approved Quote Count"]==2 for r in rows),85)
        self.assertEqual(len({r["Source Key"] for r in rows}),95)
        self.assertTrue(all(r["Approved Quote Count"] is None
                        or isinstance(r["Approved Quote Count"],int) for r in rows))

    def test_malformed_weekly_approval_count_must_fail_not_disappear(self):
        source={"SFDC Weekly Overview":[{
            "week_start":"2025-04-25","week_end":"2025-05-01",
            "weekly_basis":"FRI_THU_CSS_EXISTING",
            "quotation_approvals":"unknown"}],
            "Quote Approval Dedup":[],"SFDC Quote Export":[]}
        with self.assertRaisesRegex(SafeError,"WEEKLY_APPROVAL_COUNT_NOT_NUMERIC"):
            m.weekly_rows(source)

    def test_existing_stale_week_count_is_cleared_and_readback_verified(self):
        old={"record_id":"rec1","fields":{
            "Source Key":"QUOTE:2025-04-25","Approved Quote Count":5,
            "Amount Status":"VERIFIED_ALL","Last Sync KST":"2026-10-01"}}
        cleared={"record_id":"rec1","fields":{
            "Source Key":"QUOTE:2025-04-25","Approved Quote Count":None,
            "Amount Status":"WITHHELD_WEEKLY_APPROVAL_COUNT_MISSING"}}
        desired={"Source Key":"QUOTE:2025-04-25",
                 "Approved Quote Count":None,
                 "Amount Status":"WITHHELD_WEEKLY_APPROVAL_COUNT_MISSING"}
        with mock.patch.object(m,"list_all",side_effect=[[old],[cleared]]) as listing,\
             mock.patch.object(m,"api") as api:
            result=m.sync_table("token","/tables/weekly",[desired],120)
        self.assertEqual(result,(0,1,0))
        self.assertEqual(listing.call_count,2)
        api.assert_called_once()
        self.assertIn("metric_record_update",str(api.call_args))

    def test_quote_readback_rejects_old_non_null_count_after_clear(self):
        old={"record_id":"rec1","fields":{
            "Source Key":"QUOTE:2025-04-25","Approved Quote Count":5}}
        desired={"Source Key":"QUOTE:2025-04-25",
                 "Approved Quote Count":None}
        with mock.patch.object(m,"list_all",side_effect=[[old],[old]]),\
             mock.patch.object(m,"api"):
            with self.assertRaisesRegex(SafeError,"QUOTE_KPI_READBACK_MISMATCH"):
                m.sync_table("token","/tables/weekly",[desired],120)

    def test_equivalent_numeric_and_text_ignores_timestamp(self):
        old={"Invoice Count":2.0,"Source Key":[{"text":"INVOICE:2026-10"}],
             "Last Sync KST":"old"}
        new={"Invoice Count":2,"Source Key":"INVOICE:2026-10","Last Sync KST":"new"}
        self.assertTrue(m.equivalent(old,new))
        self.assertFalse(m.equivalent(old,{**new,"Invoice Count":3}))
        self.assertFalse(m.equivalent({"Verified Quote Value K USD":12.4},
                                     {"Verified Quote Value K USD":None}))
        self.assertTrue(m.equivalent({"Verified Quote Value K USD":None},
                                    {"Verified Quote Value K USD":None}))


if __name__=="__main__":
    unittest.main()
