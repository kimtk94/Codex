#!/usr/bin/env python3
"""Safety tests for Feishu Base internal Sales Home."""
import unittest
from unittest import mock
import sales_native_home as p

class PortalTests(unittest.TestCase):
    def test_routes_unique_and_no_vercel(self):
        keys=[x[0] for x in p.MENUS]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertTrue(all(len(x)==7 for x in p.MENUS))
        self.assertFalse(any("vercel" in str(x).lower() for x in p.MENUS))
        self.assertEqual(len(p.PINNED_KEYS),13)
        self.assertIn("PAYMENT_FOLLOWUP",p.PINNED_KEYS)
        self.assertTrue(p.PINNED_KEYS.issubset(set(keys)))

    def test_full_menu_view_filter_is_empty_and_existing_views_are_untouched(self):
        self.assertEqual(p.FULL_VIEW,"전체 메뉴")
        self.assertEqual(len(p.MENUS),36)
        self.assertIn("AUTOMATION_HISTORY",{x[0] for x in p.MENUS})
        from unittest.mock import patch
        proper={"view_name":p.FULL_VIEW,"view_type":"grid",
                "property":{"filter_info":{"conditions":[]}}}
        with patch("setup_sales_web.resolve_view",return_value=("vewFull",False)), \
             patch("setup_sales_web.get_view",return_value=proper), \
             mock.patch.object(p,"api") as api:
            self.assertEqual(p.ensure_full_view("token","/tbl"),"vewFull")
            api.assert_not_called()
        filtered={"view_name":p.FULL_VIEW,"view_type":"grid",
                  "property":{"filter_info":{"conditions":[{"field_id":"fld",
                   "operator":"is","value":'[\\"주요\\"]'}]}}}
        with patch("setup_sales_web.resolve_view",return_value=("vewFull",False)), \
             patch("setup_sales_web.get_view",side_effect=[filtered,proper]), \
             mock.patch.object(p,"api") as api:
            self.assertEqual(p.ensure_full_view("token","/tbl"),"vewFull")
            self.assertEqual(api.call_count,1)
            self.assertEqual(api.call_args.args[0],"PATCH")
            self.assertEqual(api.call_args.kwargs["data"]["property"]["filter_info"]["conditions"],[])

    def test_shortcut_exact_seven_and_existing_twelve(self):
        self.assertEqual(p.SHORTCUT_KEYS,(
            "MONTHLY_TREND","WEEKLY_TREND","SIF_EVIDENCE",
            "X_MY_PROJECTS","PAYMENT_FOLLOWUP",
            "PROJECT_ACTIVE_QUOTE","PROJECT_BILLING_QUOTE"))
        self.assertEqual(len(p.PINNED_KEYS),13)
        cfg=p.shortcut_filter("fldMain")
        self.assertEqual(cfg["conjunction"],"or")
        self.assertEqual(len(cfg["conditions"]),7)
        view={"view_name":p.SHORTCUT_VIEW,"view_type":"grid",
              "property":{"filter_info":cfg}}
        self.assertTrue(p.shortcut_filter_matches(view,"fldMain"))
        self.assertFalse(p.shortcut_filter_matches(view,"other"))
        view["property"]["filter_info"]["conditions"].append(
            {"field_id":"fldMain","operator":"is",
             "value":'["DASHBOARD"]'})
        self.assertFalse(p.shortcut_filter_matches(view,"fldMain"))

    def test_shortcut_filters_only_target_view(self):
        from unittest.mock import call
        proper={"view_name":p.SHORTCUT_VIEW,"view_type":"grid",
                "property":{"filter_info":{}}}
        with mock.patch.object(p,"list_views",return_value={p.SHORTCUT_VIEW:"vewShortcut"}), \
             mock.patch.object(p,"get_fields",return_value=[
                 {"field_name":"Menu Key","field_id":"fldMain","type":1}
             ]), mock.patch.object(p,"api",return_value={}) as api, \
             mock.patch("setup_sales_web.get_view",side_effect=[
                 proper, {"view_name":p.SHORTCUT_VIEW,"view_type":"grid",
                          "property":{"filter_info":p.shortcut_filter("fldMain")}}
             ]):
            self.assertEqual(p.ensure_shortcut_view("token","/tbl"),"vewShortcut")
            self.assertEqual(api.call_count,1)
            self.assertEqual(api.call_args.args[0],"PATCH")
            self.assertIn("/views/vewShortcut",api.call_args.args[1])

    def test_menu_order_colors_and_stable_ids(self):
        self.assertEqual(len(p.CURATED_ORDER),13)
        self.assertEqual(len(set(p.CURATED_ORDER)),13)
        self.assertEqual(p.presentation("DASHBOARD","핵심 KPI 카드",1),
                         (1,"01 · 핵심 KPI 카드","핵심 KPI"))
        self.assertEqual(p.presentation("X_URGENT","긴급",2)[2],"즉시 확인")
        self.assertEqual(p.presentation("PO_REQUIRED","PO",3)[2],"확인·증빙")
        self.assertEqual(p.presentation("PAYMENT_FOLLOWUP","결제",4)[2],"매출·결제")
        self.assertEqual(p.presentation("ACCOUNTS","기관",6),
                         (106,"기관","관리용"))
        self.assertEqual({n:c for n,c in p.MENU_COLORS}["즉시 확인"],0)
        self.assertTrue(p.PINNED_KEYS==set(p.CURATED_ORDER))

    def test_numeric_sort_fields_do_not_cause_repeated_writes(self):
        self.assertTrue(p.same({"표시순서":1.0,"화면":"01 · KPI",
                                "메뉴 구분":"핵심 KPI"},
                               {"표시순서":1,"화면":"01 · KPI",
                                "메뉴 구분":"핵심 KPI"}))

    def test_chart_shortcuts_use_real_dashboard_ids_not_grid_views(self):
        ids={"FEISHU_SHORTCUT_MONTHLY_DASHBOARD_ID":"blkMonthlyABC123",
             "FEISHU_SHORTCUT_WEEKLY_DASHBOARD_ID":"blkWeeklyXYZ987"}
        with mock.patch.dict(p.os.environ,ids):
            rows=p.source_rows("t","root",{},None)
        by_key={r["Menu Key"]:r for r in rows}
        for key,dash_id in (("MONTHLY_TREND","blkMonthlyABC123"),
                            ("WEEKLY_TREND","blkWeeklyXYZ987")):
            row=by_key[key]
            self.assertEqual(row["바로가기 URL"],p.BASE_URL+"?table="+dash_id)
            self.assertEqual(row["데이터 상태"],"DASHBOARD_PRESENT")
            self.assertEqual(row["바로가기"]["link"],row["바로가기 URL"])
            self.assertEqual(row["바로가기"]["text"],p.GRAPH_LINK_LABELS[key])
            self.assertTrue(p.valid_menu_url(key,row["바로가기 URL"]))
            self.assertFalse(p.valid_menu_url(key,p.BASE_URL+"?table=tblGrid&view=vewGrid"))
        project=by_key["X_MY_PROJECTS"]
        self.assertEqual(project["바로가기"]["text"],p.GRAPH_LINK_LABELS["X_MY_PROJECTS"])
        self.assertEqual(project["바로가기 URL"],p.BASE_URL+"?table="+p.PROJECT_OPS_DASHBOARD_ID)
        self.assertEqual(project["화면"],"07 · 프로젝트 운영 대시보드")
        for key,tid in (("PROJECT_ACTIVE_QUOTE","tblActive123"),("PROJECT_BILLING_QUOTE","tblBilling123")):
            self.assertTrue(p.valid_menu_url(key,p.BASE_URL+"?table="+tid))
            self.assertFalse(p.valid_menu_url(key,p.BASE_URL+"?table="+tid+"&view=vewWrong"))
        self.assertIsNone(p.chart_shortcut_url("MONTHLY_TREND",{}))
        self.assertFalse(p.valid_menu_url("MONTHLY_TREND",p.BASE_URL+"?table=blkInvalid&view=v"))
        self.assertEqual(len(p.SHORTCUT_KEYS),7)

    def test_real_invoice_ledger_link_is_not_monthly_summary(self):
        target=p.BASE_URL+"?table=tblInvoiceLedger1234"
        with mock.patch.object(p,"api",return_value={"items":[{"record_id":"rec"}]}):
            self.assertEqual(p.invoice_review_ledger_url("token","root",
                {"X Invoice Ledger":"tblInvoiceLedger1234"}),target)
            self.assertEqual(p.invoice_review_ledger_url("token","root",{}),"")
            rows=p.source_rows("token","root",{
                "X Invoice Ledger":"tblInvoiceLedger1234"},None)
        monthly=next(x for x in rows if x["Menu Key"]=="MONTHLY_TREND")
        self.assertEqual(monthly["바로 편집"],{
            "text":"Invoice 원장 검토 · 매출 확정 아님","link":target})

    def test_monthly_revenue_source_link_resolves_real_base_table(self):
        live=p.BASE_URL+"?table=tblRevenueMonthly123"
        self.assertEqual(p.monthly_revenue_grid_url("token","root",{
            "Monthly Tax Invoice":"tblRevenueMonthly123"}),live)
        self.assertEqual(p.monthly_revenue_grid_url("token","root",{}),"")
        with mock.patch.object(p,"list_views",return_value={"All":"vewAll"}), \
             mock.patch.object(p,"api",return_value={"items":[{"record_id":"r"}]}):
            rows=p.source_rows("token","root",{
                "Monthly Tax Invoice":"tblRevenueMonthly123"},None)
        monthly=next(x for x in rows if x["Menu Key"]=="MONTHLY_TREND")
        self.assertNotIn("바로 편집",monthly)
        self.assertNotIn("Monthly Tax Invoice", monthly["바로가기 URL"])

    def test_editable_weekly_quote_link_is_distinct_from_dashboard(self):
        base=p.BASE_URL+"?table=tblReview1234&view=vewRecent5"
        with mock.patch.object(p,"list_views",return_value={
            "그래프 연동 · 최근 5주 검토":"vewRecent5"}) as views:
            result=p.weekly_editable_grid_url("token","root",{
                "Weekly Quote Review":"tblReview1234"})
        self.assertEqual(result,base)
        self.assertEqual(views.call_count,1)
        with mock.patch.object(p,"list_views",return_value={
            "그래프 연동 · 최근 5주 검토":"vewRecent5"}), \
             mock.patch.object(p,"api",return_value={"items":[{"record_id":"recMock"}]}):
            rows=p.source_rows("token","root",{
                "Weekly Quote Review":"tblReview1234"},None)
        weekly=next(r for r in rows if r["Menu Key"]=="WEEKLY_TREND")
        self.assertEqual(weekly["바로 편집"]["link"],base)
        self.assertEqual(weekly["바로 편집"]["text"],"✎ Weekly Quote 편집 · 합산 제외")
        self.assertTrue(p.same({"바로 편집":weekly["바로 편집"]},
                               {"바로 편집":weekly["바로 편집"]}))
        self.assertFalse(p.same({"바로 편집":None},
                                {"바로 편집":weekly["바로 편집"]}))

    def test_link_and_empty_source(self):
        tables={"QQ Mail Intake":"tblMAIL","Contacts":"tblCUSTOMER"}
        with mock.patch.object(p,"list_views",side_effect=[
            {"현재 메일 · 최근 30일":"v1","과거 메일 · 2026":"v2","수신 메일":"v3","발신 메일":"v4"},
            {"한글 고객 검색":"v5"}]), mock.patch.object(p,"api",
            side_effect=[{"items":[{"record_id":"r"}]},{"items":[]}]) as api:
            desired=p.source_rows("token","root",tables,None)
            rows={r["Menu Key"]:r for r in desired}
            self.assertEqual(rows["MAIL_CURRENT"]["데이터 상태"],"DATA_PRESENT")
            self.assertIn("&view=v1",rows["MAIL_CURRENT"]["바로가기 URL"])
            self.assertEqual(rows["MAIL_CURRENT"]["바로가기"],{
                "text":"열기","link":rows["MAIL_CURRENT"]["바로가기 URL"]})
            self.assertEqual(rows["CONTACTS"]["바로가기"],{
                "text":"열기","link":rows["CONTACTS"]["바로가기 URL"]})
            self.assertEqual(rows["CONTACTS"]["데이터 상태"],"SOURCE_EMPTY")
            self.assertEqual(rows["MAIL_CURRENT"]["표시"],p.CURATED_DISPLAY)
            self.assertEqual(rows["CONTACTS"]["표시"],p.ARCHIVE_DISPLAY)
            self.assertEqual(rows["PROJECT_MAIL"]["데이터 상태"],"SOURCE_TABLE_NOT_READY")
            self.assertEqual(api.call_count,2)

    def test_missing_view_is_not_ready(self):
        with mock.patch.object(p,"list_views",return_value={}), mock.patch.object(p,"api",
            return_value={"items":[{"record_id":"r"}]}):
            rows=p.source_rows("t","root",{"QQ Mail Intake":"tbl"},None)
            result=next(r for r in rows if r["Menu Key"]=="MAIL_CURRENT")
            self.assertEqual(result["데이터 상태"],"VIEW_NOT_READY")
            self.assertEqual(result["바로가기 URL"],"")
            self.assertIsNone(result["바로가기"])

    def test_link_readback_and_schema(self):
        self.assertEqual(p.MENU_EXTRA_FIELDS["바로가기"]["type"],15)
        self.assertEqual(p.MENU_EXTRA_FIELDS["바로 편집"]["type"],15)
        link={"text":"열기","link":"https://ocnz4cb25scn.feishu.cn/base/x?table=y&view=z"}
        self.assertTrue(p.same({"바로가기":link},{"바로가기":link}))
        self.assertTrue(p.same({"바로가기":None},{"바로가기":None}))
        self.assertFalse(p.same({"바로가기":None},{"바로가기":link}))

    def test_no_writes_when_unchanged(self):
        data={"Menu Key":"TEST","데이터 상태":"DATA_PRESENT"}
        with mock.patch.object(p,"list_all",return_value=[{"record_id":"r","fields":data}]),mock.patch.object(p,"api") as api:
            p.update_home("t","path",[data])
            api.assert_not_called()

    def test_reject_wrong_base(self):
        with mock.patch.dict(p.os.environ,{"FEISHU_BASE_APP_TOKEN":"invalid"}),mock.patch.object(p,"auth") as a:
            with self.assertRaisesRegex(p.SafeError,"REFUSE_NON_SALES_BASE"):p.main()
            a.assert_not_called()

if __name__=="__main__":unittest.main()
