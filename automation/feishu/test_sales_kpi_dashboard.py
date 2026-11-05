#!/usr/bin/env python3
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from qq_mail_ingest import SafeError
from native_kpi_compute import compute,SRC
from native_kpi_financial import financial,latest
from sales_kpi_dashboard import equal

NOW=dt.datetime(2026,11,6,0,0,tzinfo=ZoneInfo("Asia/Seoul"))
KEY="a"*64

def fixture():
    return {
        SRC[0]:[{"Mail Key":KEY,"Received At":"2026-11-05T09:00:00+09:00","Direction":"INBOUND"}],
        SRC[1]:[{"Mail Key":KEY,"Relationship Status":"LINKED","Followup Pool":"THREAD_REVIEW_REQUIRED",
                 "Contact Link":"EMAIL_EXACT_CONTACT","Project Link":"PROJECT_ID_EXACT"}],
        SRC[2]:[{"SIF State":"APPROVED"}],
        SRC[3]:[{"Month":"2026-11","Coverage Status":"SOURCE_SCOPE_REVIEW",
                 "Net Revenue KRW Ex VAT":1000000,"Net Revenue K USD":0.7,
                 "Tax Invoice KRW Incl VAT":1100000,"Invoice Count":1}],
        SRC[4]:[{"Week Start":"2026-11-02","Amount Status":"VERIFIED_PARTIAL",
                 "Approved Quote Count":3,"Verified Quote Value KRW FX":500000,
                 "Verified Quote Value K USD":0.36,"Unmatched Amount Count":2}],
    }

class DashboardTests(unittest.TestCase):
    def test_identity_and_unanswered_not_assumed(self):
        src=fixture()
        rows=compute(src,{k:"https://feishu.example/"+k for k in SRC},NOW)
        d={r["KPI Key"]:r for r in rows}
        self.assertEqual(d["MAIL_ALL"]["값"],1)
        self.assertEqual(d["IDENTITY_POOL_THREAD_REVIEW_REQUIRED"]["값"],1)
        self.assertEqual(d["IDENTITY_CONTACT"]["값"],1)
        self.assertEqual(d["SIF_APPROVED"]["값"],1)

    def test_vat_invoice_and_quote_separate(self):
        src=fixture()
        f={x["KPI Key"]:x for x in financial(src,{k:"src" for k in SRC},NOW)}
        self.assertEqual(f["MONTH_NET_KRW"]["값"],1000000)
        self.assertEqual(f["MONTH_GROSS"]["값"],1100000)
        self.assertEqual(f["MONTH_NET_KRW"]["검증 상태"],"REVIEW")
        self.assertEqual(f["WEEK_KRW"]["값"],500000)
        self.assertEqual(f["WEEK_KRW"]["검증 상태"],"REVIEW")

    def test_source_missing_period_does_not_invent_amount(self):
        self.assertIsNone(latest([],"Month",NOW))
        self.assertTrue(equal({"값":500000},{"값":500000.0}))

    def test_duplicate_source_mail_fails(self):
        src=fixture()
        src[SRC[0]].append(src[SRC[0]][0])
        with self.assertRaisesRegex(SafeError,"BAD_MAIL_KEY"):
            compute(src,{k:"a" for k in SRC},NOW)

if __name__=="__main__":unittest.main()
