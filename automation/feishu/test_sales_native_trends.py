#!/usr/bin/env python3
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from qq_mail_ingest import SafeError
import native_trend_rows as t
import sales_native_trends as s
NOW=dt.datetime(2026,11,6,12,tzinfo=ZoneInfo("Asia/Seoul"))

class TrendTests(unittest.TestCase):
    def test_monthly_net_and_gross_separate(self):
        src={t.MONTH:[{"Month":"2026-10","Net Revenue KRW Ex VAT":"1,000,000",
                         "Tax Invoice KRW Incl VAT":"1,100,000",
                         "Net Revenue K USD":"0.75","Invoice Count":"1",
                         "Coverage Status":"SOURCE_SCOPE_REVIEW"}],
             t.WEEK:[{"Week Start":"2026-11-02","Approved Quote Count":"3",
                       "Verified Quote Value KRW FX":"500000",
                       "Verified Quote Value K USD":"0.35",
                       "Unmatched Amount Count":"2","Amount Status":"VERIFIED_PARTIAL"}]}
        data=t.make(src,{t.MONTH:"https://example.com/month",t.WEEK:"https://example.com/week"},NOW)
        self.assertEqual(len(data),2)
        m,w=data
        self.assertEqual(m["Revenue KRW VAT 제외"],1000000)
        self.assertEqual(m["Invoice KRW VAT 포함"],1100000)
        self.assertEqual(m["증빙 상태"],"REVIEW")
        self.assertEqual(w["Quote 승인"],3)
        self.assertEqual(w["Quote 금액 미확인"],2)
        self.assertEqual(w["증빙 상태"],"REVIEW")

    def test_missing_numbers_not_zero(self):
        r=t.make({t.MONTH:[{"Month":"2026-10","Coverage Status":"REVIEW"}],
                  t.WEEK:[]},{t.MONTH:"source",t.WEEK:"source"},NOW)[0]
        self.assertNotIn("Revenue KRW VAT 제외",r)
        self.assertNotIn("Invoice 건수",r)

    def test_duplicate_period_fails(self):
        x={"Month":"2026-09"}
        with self.assertRaisesRegex(SafeError,"TREND_DUPLICATE_MONTH"):
            t.make({t.MONTH:[x,x],t.WEEK:[]},{t.MONTH:"",t.WEEK:""},NOW)

    def test_future_not_in_report(self):
        d=t.make({t.MONTH:[{"Month":"2026-10"},{"Month":"2027-01"}],
                  t.WEEK:[{"Week Start":"2027-05-01"}]},{t.MONTH:"",t.WEEK:""},NOW)
        self.assertEqual(len(d),1)

    def test_idempotent_numeric_comparison(self):
        sample={"원본 키":"M:2026-10","유형":"MONTHLY_REVENUE",
                "기간":"2026-10","연도":2026,"Revenue KRW VAT 제외":1000000}
        self.assertTrue(s.same({"원본 키":"M:2026-10","유형":"MONTHLY_REVENUE",
                "기간":"2026-10","연도":2026,"Revenue KRW VAT 제외":1000000.0},sample))
        self.assertFalse(s.same({"Revenue KRW VAT 제외":1100000},{"Revenue KRW VAT 제외":1000000}))

if __name__=="__main__": unittest.main()
