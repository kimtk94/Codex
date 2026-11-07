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
