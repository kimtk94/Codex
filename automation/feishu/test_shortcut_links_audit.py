#!/usr/bin/env python3
"""Seven Feishu Sales Home deep links must resolve to the correct native objects."""
import unittest
from unittest import mock
import shortcut_links_audit as a
from sales_native_home import BASE_URL, SHORTCUT_KEYS, GRAPH_LINK_LABELS, PROJECT_OPS_DASHBOARD_ID

LINKS={
    "MONTHLY_TREND":(BASE_URL+"?table=blkMonthly1234","DASHBOARD_VERIFIED"),
    "WEEKLY_TREND":(BASE_URL+"?table=blkWeekly1234","DASHBOARD_VERIFIED"),
    "SIF_EVIDENCE":(BASE_URL+"?table=tblSif1234&view=vewSif1234","VIEW_VERIFIED"),
    "X_MY_PROJECTS":(BASE_URL+"?table="+PROJECT_OPS_DASHBOARD_ID,"DASHBOARD_VERIFIED"),
    "PAYMENT_FOLLOWUP":(BASE_URL+"?table=tblPayment1234&view=vewPayment1234","VIEW_VERIFIED"),
    "PROJECT_ACTIVE_QUOTE":(BASE_URL+"?table=tblActive1234","PROJECT_TABLE_VERIFIED"),
    "PROJECT_BILLING_QUOTE":(BASE_URL+"?table=tblBilling1234","PROJECT_TABLE_VERIFIED"),
}

def records():
    return [{"fields":{"Menu Key":key,
                        "바로가기 URL":url if not key.startswith("PROJECT_") else "",
                        "바로가기":{"text":GRAPH_LINK_LABELS.get(key,"열기"),"link":url}}}
            for key,(url,_) in LINKS.items()]

class LinkAuditTests(unittest.TestCase):
    def test_seven_persisted_correct(self):
        output=a.verify_persisted_shortcuts(records(),LINKS)
        self.assertEqual(set(output),set(SHORTCUT_KEYS))
        for key,(url,kind) in output.items():
            self.assertEqual(LINKS[key],(url,kind))

    def test_weekly_native_grid_edit_link_is_real_and_clickable(self):
        editor=BASE_URL+"?table=tbl4mcccUgVHpUvO&view=vewNmLWcUF"
        source=records()
        target=next(row["fields"] for row in source
                    if row["fields"]["Menu Key"]=="WEEKLY_TREND")
        target["바로 편집"]={"text":"✎ Weekly Quote 편집 · 합산 제외",
                              "link":editor}
        output=a.verify_persisted_shortcuts(source,LINKS,editor)
        self.assertIn("WEEKLY_TREND",output)
        target["바로 편집"]["link"]=BASE_URL+"?table=tblWrong"
        with self.assertRaisesRegex(a.SafeError,"WEEKLY_EDITOR_CLICKABLE_LINK_MISMATCH"):
            a.verify_persisted_shortcuts(source,LINKS,editor)

    def test_missing_or_fake_link_rejected(self):
        rows=records()
        rows[0]["fields"]["바로가기"]=None
        with self.assertRaisesRegex(a.SafeError,"LINK_READBACK_MISMATCH"):
            a.verify_persisted_shortcuts(rows,LINKS)
        rows=records()
        rows[0]["fields"]["바로가기 URL"]=BASE_URL+"?table=tblOther"
        with self.assertRaisesRegex(a.SafeError,"LINK_READBACK_MISMATCH"):
            a.verify_persisted_shortcuts(rows,LINKS)
        rows=records()
        rows[0]["fields"]["바로가기"]["text"]="열기"
        with self.assertRaisesRegex(a.SafeError,"LINK_READBACK_MISMATCH"):
            a.verify_persisted_shortcuts(rows,LINKS)

    def test_all_seven_required_unique(self):
        with self.assertRaisesRegex(a.SafeError,"RECORDS_MISSING"):
            a.verify_persisted_shortcuts(records()[:-1],LINKS)
        with self.assertRaisesRegex(a.SafeError,"DUPLICATE_RECORD"):
            a.verify_persisted_shortcuts(records()+[records()[0]],LINKS)

    def test_url_exact_must_reject_extra_parameters(self):
        self.assertTrue(a.exact_url(BASE_URL+"?table=blkMonthly1234","blkMonthly1234"))
        self.assertFalse(a.exact_url(BASE_URL+"?table=blkMonthly1234&view=vewFake","blkMonthly1234"))
        self.assertTrue(a.exact_url(BASE_URL+"?table=tblSif1234&view=vewSif1234",
                                    "tblSif1234","vewSif1234"))
        self.assertFalse(a.exact_url(BASE_URL+"?table=tblSif1234&view=vewSif1234&other=x",
                                     "tblSif1234","vewSif1234"))
        self.assertFalse(a.exact_url("https://outside.example/?table=tblSif1234","tblSif1234"))

    def test_targets_must_have_actual_views_and_dashboard(self):
        tables={
            "SIF Evidence Tracker":"tblSif1234",
            "Project Progress Board":"tblPayment1234",
            "프로젝트 운영 · 진행 중 (Quote)":"tblActive1234",
            "프로젝트 운영 · 완료·결제 (Quote)":"tblBilling1234"
        }
        vmap=[
            {"SIF 승인 확인 필요":"vewSif1234"},
            {"완료 · 결제 관리":"vewPayment1234"},
        ]
        def find(_,title):
            if title=="Novogene 프로젝트 운영 대시보드":return PROJECT_OPS_DASHBOARD_ID
            return "blkMonthly1234" if "월별" in title else "blkWeekly1234"
        with mock.patch.object(a,"cli",return_value=[]),\
             mock.patch.object(a,"find_named",side_effect=find),\
             mock.patch.object(a,"verify_components"),\
             mock.patch.object(a,"list_views",side_effect=vmap),\
             mock.patch.object(a,"list_all",return_value=[{"record_id":"rec1"}]):
            output=a.target_routes("token","root",tables)
        self.assertEqual(output,LINKS)

if __name__=="__main__":
    unittest.main()
