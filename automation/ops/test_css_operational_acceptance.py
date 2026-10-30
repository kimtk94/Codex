import datetime as dt
import unittest
from css_operational_acceptance import KST,build,fresh
NOW=dt.datetime(2026,10,30,21,30,tzinfo=KST)
def data():
    return {
      "health":[["Component","Last success KST","State"],["CSS Mail","2026-10-30 21:12:45 KST","PASS"],["CSS Mail Body","2026-10-30 21:20:00 KST","BACKFILL_ACTIVE"]],
      "lifecycle":[["Month","Actual Invoice KRW"],["2026-10","₩158,541,900","","","","48","","","","","","2026-10-30 21:13:54 KST"]],
      "net":[["Month","Issued Invoice Gross KRW (VAT incl)","Issued Net Revenue KRW (VAT excl)"],
             ["2026-10","158541900","144129000","96.086","48","","","2026-10-30 21:14:37 KST","INVOICE_FILENAME_VERIFIED_NET;PENDING_VAT_UNVERIFIED"]],
      "authority":[["Month","Source Tab","Source Role"],
                  ["2026-10","","CANONICAL_ACTUAL_GROSS","48","158541900","VAT_INCLUDED","MATCHED_TO_NET_AUDIT","YES","2026-10-30 21:16:20 KST"],
                  ["2026-10","","CANONICAL_ISSUED_NET","48","144129000","VAT_EXCLUDED","MATCHED_TO_INVOICE_SOURCE","YES","2026-10-30 21:16:20 KST"],
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
        self.assertEqual(s["Body workflow execution"],"PASS")
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
    def test_failed_body_workflow_blocks_despite_last_good_backfill_counts(self):
        d=data()
        d["health"][2][2]="FAIL_BODY_WORKFLOW"
        self.assertEqual(states(d)["Body workflow execution"],"BLOCK")
        self.assertEqual(states(d)["Body cache completeness"],"WARN")
    def test_stale_body_workflow_blocks_without_invented_success(self):
        d=data()
        d["health"][2][1]="2026-10-29 11:00:00 KST"
        self.assertEqual(states(d)["Body workflow execution"],"BLOCK")
        d=data()
        d["health"].pop()
        self.assertEqual(states(d)["Body workflow execution"],"BLOCK")
    def test_invalid_or_future_clock(self):
        self.assertFalse(fresh("2026-10-31 23:00:00 KST",NOW,6))
        self.assertFalse(fresh("not a date",NOW,6))
    def test_auth_e2e_never_assumed_from_ci(self):
        s=states(data())
        self.assertEqual(s["Owner-authenticated Preview E2E"],"BLOCK")
        self.assertEqual(s["Production READY SHA parity"],"BLOCK")
    def test_overnight_last_17_subscription_stays_pass(self):
        from css_operational_acceptance import report_due_slot, report_slot_state
        now=dt.datetime(2026,10,31,0,23,tzinfo=KST)
        d=data()
        for row in d["reports"][1:]:
            row[1]="2026-10-30 17:00:05 KST"
        self.assertEqual(report_due_slot(now).strftime("%Y-%m-%d %H:%M"),
                         "2026-10-30 17:00")
        self.assertEqual(
            {r[1]:r[2] for r in build(d,now)[1:]}["Three subscription Reports"],
            "PASS")
        self.assertEqual(report_slot_state([
            dt.datetime(2026,10,30,17,0,5,tzinfo=KST)],now)[0],"PASS")

    def test_missing_evening_report_is_not_hidden_overnight(self):
        from css_operational_acceptance import report_slot_state
        for hour,minute,expected in [(17,39,"PASS"),(17,40,"WARN"),
                                     (23,5,"BLOCK")]:
            # Test newest source 12:00: before the 17:40 due, it is current,
            # after the due it becomes missing, and then a hard data block.
            now=dt.datetime(2026,10,30,hour,minute,tzinfo=KST)
            x=dt.datetime(2026,10,30,12,0,5,tzinfo=KST)
            self.assertEqual(report_slot_state([x],now)[0],expected)
        now=dt.datetime(2026,10,31,0,23,tzinfo=KST)
        old=dt.datetime(2026,10,30,12,0,5,tzinfo=KST)
        self.assertEqual(report_slot_state([old],now)[0],"BLOCK")

    def test_november_does_not_reuse_october_verified_revenue(self):
        now=dt.datetime(2026,11,1,0,55,tzinfo=KST)
        d=data()
        states={r[1]:r[2] for r in build(d,now)[1:]}
        self.assertEqual(states["Gross/net invoice parity"],"BLOCK")
        self.assertEqual(states["Canonical vs stale legacy"],"BLOCK")

    def test_verified_zero_invoice_month_can_be_zero_not_missing(self):
        now=dt.datetime(2026,11,1,0,55,tzinfo=KST)
        d=data()
        d["lifecycle"].append(["2026-11","0","","","","0","","","","","",
                               "2026-11-01 00:53:00 KST"])
        d["net"].append(["2026-11","0","0","0.000","0","","",
                         "2026-11-01 00:53:00 KST",
                         "INVOICE_FILENAME_VERIFIED_NET;PENDING_VAT_UNVERIFIED"])
        d["authority"].extend([
            ["2026-11","","CANONICAL_ACTUAL_GROSS","0","0",
             "VAT_INCLUDED","MATCHED_TO_NET_AUDIT","YES",
             "2026-11-01 00:53:00 KST"],
            ["2026-11","","CANONICAL_ISSUED_NET","0","0",
             "VAT_EXCLUDED","MATCHED_TO_INVOICE_SOURCE","YES",
             "2026-11-01 00:53:00 KST"]
        ])
        s={r[1]:r[2] for r in build(d,now)[1:]}
        self.assertEqual(s["Gross/net invoice parity"],"PASS")
        self.assertEqual(s["Canonical vs stale legacy"],"PASS")
        self.assertEqual(s["Production acceptance"],"BLOCK")

    def test_report_success_refreshes_ledger_not_failed_reruns(self):
        from pathlib import Path
        workflow=(Path(__file__).resolve().parents[2]/".github/workflows/css-operational-acceptance.yml").read_text()
        self.assertIn('workflows: ["SFDC Three Report Mail Digestion", "CSS Web Mail Body Sync"]',workflow)
        self.assertIn("github.event.workflow_run.name == 'CSS Web Mail Body Sync'",workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'",workflow)
        self.assertIn("github.event.workflow_run.head_branch == 'main'",workflow)
        self.assertIn("run: python automation/ops/css_operational_acceptance.py",workflow)
        self.assertNotIn("request_promote",workflow)
if __name__=="__main__":unittest.main()
