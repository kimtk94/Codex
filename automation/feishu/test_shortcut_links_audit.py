#!/usr/bin/env python3
"""Five homepage deep links must resolve to the correct Feishu objects."""
import unittest
from unittest import mock
import shortcut_links_audit as a
from sales_native_home import BASE_URL, SHORTCUT_KEYS

LINKS={
    "MONTHLY_TREND":(BASE_URL+"?table=blkMonthly1234","DASHBOARD_VERIFIED"),
    "WEEKLY_TREND":(BASE_URL+"?table=blkWeekly1234","DASHBOARD_VERIFIED"),
    "SIF_EVIDENCE":(BASE_URL+"?table=tblSif1234&view=vewSif1234","VIEW_VERIFIED"),
    "X_MY_PROJECTS":(BASE_URL+"?table=tblX1234&view=vewX1234","VIEW_VERIFIED"),
    "PAYMENT_FOLLOWUP":(BASE_URL+"?table=tblPayment1234&view=vewPayment1234","VIEW_VERIFIED"),
}

def records():
    return [{"fields":{"Menu Key":key,"바로가기 URL":url,
                        "바로가기":{"text":"열기","link":url}}}
            for key,(url,_) in LINKS.items()]

class LinkAuditTests(unittest.TestCase):
    def test_five_persisted_correct(self):
        output=a.verify_persisted_shortcuts(records(),LINKS)
        self.assertEqual(set(output),set(SHORTCUT_KEYS))
        for key,(url,kind) in output.items():
            self.assertEqual(LINKS[key],(url,kind))

    def test_missing_or_fake_link_rejected(self):
        rows=records()
        rows[0]["fields"]["바로가기"]=None
        with self.assertRaisesRegex(a.SafeError,"LINK_READBACK_MISMATCH"):
            a.verify_persisted_shortcuts(rows,LINKS)
        rows=records()
        rows[0]["fields"]["바로가기 URL"]=BASE_URL+"?table=tblOther"
        with self.assertRaisesRegex(a.SafeError,"LINK_READBACK_MISMATCH"):
            a.verify_persisted_shortcuts(rows,LINKS)

    def test_all_five_are_required_and_unique(self):
        with self.assertRaisesRegex(a.SafeError,"RECORDS_MISSING"):
            a.verify_persisted_shortcuts(records()[:-1],LINKS)
        with self.assertRaisesRegex(a.SafeError,"DUPLICATE_RECORD"):
            a.verify_persisted_shortcuts(records()+[records()[0]],LINKS)

    def test_url_exact_must_reject_extra_parameters(self):
        self.assertTrue(a.exact_url(BASE_URL+"?table=blkMonthly1234","blkMonthly1234"))
        self.assertFalse(a.exact_url(BASE_URL+"?table=blkMonthly1234&view=vewFake",
                                     "blkMonthly1234"))
        self.assertTrue(a.exact_url(BASE_URL+"?table=tblSif1234&view=vewSif1234",
                                    "tblSif1234","vewSif1234"))
        self.assertFalse(a.exact_url(BASE_URL+"?table=tblSif1234&view=vewSif1234&other=x",
                                    "tblSif1234","vewSif1234"))
        self.assertFalse(a.exact_url("https://outside.example/?table=tblSif1234",
                                    "tblSif1234"))

    def test_targets_must_have_actual_views(self):
        tables={"SIF Evidence Tracker":"tblSif1234",
                "X Project Registry":"tblX1234",
                "Project Progress Board":"tblPayment1234"}
        vmap=[
            {"SIF 승인 확인 필요":"vewSif1234"},
            {"내 X 프로젝트":"vewX1234"},
            {"완료 · 결제 관리":"vewPayment1234"},
        ]
        charts=[("MONTHLY_TREND","blkMonthly1234"),
                ("WEEKLY_TREND","blkWeekly1234")]
        def find(_,title):
            return "blkMonthly1234" if "월별" in title else "blkWeekly1234"
        with mock.patch.object(a,"cli",return_value=[]),\
             mock.patch.object(a,"find_named",side_effect=find),\
             mock.patch.object(a,"verify_components"),\
             mock.patch.object(a,"list_views",side_effect=vmap):
            output=a.target_routes("token","root",tables)
        self.assertEqual(output,LINKS)

if __name__=="__main__":
    unittest.main()
