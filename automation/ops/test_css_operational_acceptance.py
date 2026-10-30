import datetime as dt
import unittest
from css_operational_acceptance import KST,build,fresh
NOW=dt.datetime(2026,10,30,21,30,tzinfo=KST)
def data():
    return {
      "health":[["Component","Last success KST","State"],["CSS Mail","2026-10-30 21:12:45 KST","PASS"]],
      "lifecycle":[["Month","Actual Invoice KRW"],["2026-10","₩158,541,900","","","","48","","","","","","2026-10-30 21:13:54 KST"]],
      "net":[["Month","Issued Invoice Gross KRW (VAT incl)","Issued Net Revenue KRW (VAT excl)"],
             ["2026-10","158541900","144129000","96.086","48","","","2026-10-30 21:14:37 KST","INVOICE_FILENAME_VERIFIED_NET;PENDING_VAT_UNVERIFIED"]],
      "authority":[["Month","Source Tab","Source Role"],
                  ["2026-10","","CANONICAL_ACTUAL_GROSS","","","","","YES","2026-10-30 21:16:20 KST"],
                  ["2026-10","","CANONICAL_ISSUED_NET","","","","","YES","2026-10-30 21:16:20 KST"],
                  *[["2026-10","","LEGACY_SNAPSHOT","","","","STALE_SOURCE_DO_NOT_USE","NO"] for _ in range(3)]],
      "reports":[["Entity","Source Received KST","Ingest Checked KST"],
                *[[n,"2026-10-30 12:00:05 KST","","493","493","0","0","a"*64,"PRESERVED_NO_NEW_REPORT"]
                  for n in ("Leads","Opportunities","Quotation")]],
      "mail":[["Updated At KST","State","QQ Staged Headers","Web Cached UID"],
              ["2026-10-30 19:04:22 KST","BACKFILL_ACTIVE","7915","889","793","","","3021","","","","0"]],
      "feishu":[["Source","Source Date","Synced At KST"],
                ["Online-Project","2026-10-30","2026-10-30T20:35:12+09:00","","110","BASE_FIELDS"]],
      "payment":[["Payment Reconciliation QC","2026-10-30 20:36:35 KST"],["Metric","Value"],
                 ["Invoice-level verified paid count","UNKNOWN"]]
    }
def states(d):return {x[1]:x[2] for x in build(d,NOW)[1:]}
class TestAcceptance(unittest.TestCase):
    def test_baseline(self):
        s=states(data())
        self.assertEqual(s["Inbox/Sent source"],"PASS")
        self.assertEqual(s["Gross/net invoice parity"],"PASS")
        self.assertEqual(s["Canonical vs stale legacy"],"PASS")
        self.assertEqual(s["Three subscription Reports"],"WARN")
        self.assertEqual(s["Body cache completeness"],"WARN")
        self.assertEqual(s["Online projects"],"PASS")
        self.assertEqual(s["Paid invoice evidence"],"BLOCK")
        self.assertEqual(s["Production acceptance"],"BLOCK")
    def test_revenue_cannot_masquerade_as_net(self):
        d=data();d["net"][1][1]="123"
        self.assertEqual(states(d)["Gross/net invoice parity"],"BLOCK")
    def test_unmarked_legacy_blocks(self):
        d=data();d["authority"][3][7]="YES"
        self.assertEqual(states(d)["Canonical vs stale legacy"],"BLOCK")
    def test_mail_error_blocks(self):
        d=data();d["mail"][1][11]="1"
        self.assertEqual(states(d)["Body cache completeness"],"BLOCK")
    def test_invalid_or_future_clock(self):
        self.assertFalse(fresh("2026-10-31 23:00:00 KST",NOW,6))
        self.assertFalse(fresh("not a date",NOW,6))
    def test_auth_e2e_never_assumed_from_ci(self):
        s=states(data())
        self.assertEqual(s["Owner-authenticated Preview E2E"],"BLOCK")
        self.assertEqual(s["Production READY SHA parity"],"BLOCK")
if __name__=="__main__":unittest.main()
