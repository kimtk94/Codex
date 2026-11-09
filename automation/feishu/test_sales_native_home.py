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
        self.assertEqual(len(p.PINNED_KEYS),12)
        self.assertIn("PAYMENT_FOLLOWUP",p.PINNED_KEYS)
        self.assertTrue(p.PINNED_KEYS.issubset(set(keys)))

    def test_shortcut_exact_five_and_existing_twelve(self):
        self.assertEqual(p.SHORTCUT_KEYS,(
            "MONTHLY_TREND","WEEKLY_TREND","SIF_EVIDENCE",
            "X_MY_PROJECTS","PAYMENT_FOLLOWUP"))
        self.assertEqual(len(p.PINNED_KEYS),12)
        cfg=p.shortcut_filter("fldMain")
        self.assertEqual(cfg["conjunction"],"or")
        self.assertEqual(len(cfg["conditions"]),5)
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
        self.assertEqual(len(p.CURATED_ORDER),12)
        self.assertEqual(len(set(p.CURATED_ORDER)),12)
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
