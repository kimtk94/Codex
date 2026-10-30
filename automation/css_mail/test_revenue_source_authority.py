import datetime as dt
import unittest
from revenue_source_authority import build, krw

NOW=dt.datetime(2026,10,30,21,0,tzinfo=dt.timezone(dt.timedelta(hours=9)))
L=[["Month","Actual Invoice KRW","Pending Verified KRW","Forecast KRW",
     "Combined KRW (verified + estimate)","Invoice Count"],
   ["2026-10","₩158,541,900","₩0","₩21,152,370","₩179,694,270","48"]]
N=[["Month","Issued Invoice Gross KRW (VAT incl)",
     "Issued Net Revenue KRW (VAT excl)","Issued Net Revenue kUSD @1500",
     "Issued Invoice Count","Verified Pending KRW (VAT basis unverified)",
     "Forecast KRW (estimate, separate)","Verified At KST","Evidence State"],
   ["2026-10","158541900","144129000","96.086","48","0","21152370",
    "2026-10-30 19:02:57 KST",
    "INVOICE_FILENAME_VERIFIED_NET;PENDING_VAT_UNVERIFIED"]]
H=[["2026-10 ACTUAL · PENDING · FORECAST RECONCILIATION","KRW","Interpretation"],
   ["Actual (issued invoice)","82137000","35 original invoice filename records; not payments"]]
Q=[["invoice_month","invoice_count","project_count","total_amount_krw"],
   ["2026-10","24","23","56,633,500 KRW"]]
C=[["TAX INVOICE COMPLETENESS AUDIT","Value","Interpretation"],
   ["October invoice count","24","Count original invoice numbers"]]

class SourceAuthorityTests(unittest.TestCase):
    def test_legacy_snapshot_explicitly_non_authoritative(self):
        r=build(L,N,H,Q,C,NOW)
        self.assertEqual(len(r),6)
        self.assertEqual(r[1][7],"YES")
        self.assertEqual(r[2][7],"YES")
        self.assertEqual(r[2][4],144129000)
        self.assertTrue(all(x[7]=="NO" for x in r[3:]))
        self.assertTrue(all(x[6]=="STALE_SOURCE_DO_NOT_USE" for x in r[3:]))
        self.assertEqual([x[3] for x in r[3:]],[35,24,24])
    def test_net_and_gross_mismatch_fails_closed(self):
        v=[x.copy() for x in N];v[1][1]="158541899"
        with self.assertRaisesRegex(ValueError,"PARITY"):build(L,v,H,Q,C,NOW)
    def test_no_legacy_does_not_invent_clean_sources(self):
        r=build(L,N,[],[],[],NOW)
        self.assertEqual(r[-1][6],"REVIEW_REQUIRED")
        self.assertEqual(r[-1][7],"NO")
    def test_gross_vat_excluded_separate_and_strict(self):
        self.assertEqual(krw("₩158,541,900"),158541900)
        self.assertEqual(krw("56,633,500 KRW"),56633500)
        with self.assertRaisesRegex(ValueError,"UNVERIFIED"):krw("UNKNOWN")

if __name__=="__main__":unittest.main()
