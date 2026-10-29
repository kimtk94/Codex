"""Offline tests: never promote QQ-only invoices, stale 3-way, or bank flags as cash."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from revenue_cross_source_audit import verify

def fixture():
    monthly=[["Month","Actual Invoice KRW","Pending Verified KRW","Forecast KRW",
              "Combined KRW","Invoice Count","Open Statement","Pending Unknown",
              "Forecast Projects","Partial Reviews","Quality","Snapshot","Verified"],
             ["2026-10","₩82,137,000","₩67,743,500","₩21,152,370",
              "","","","","","","","", "149880500"]]
    legacy=[["2026-10 ACTUAL · PENDING · FORECAST RECONCILIATION","KRW"],
            ["Actual (issued invoice)","82137000"],
            ["Pending (statement verified, invoice unissued)","0"]]
    payment=[["Payment Reconciliation QC","2026-10-29"],["Invoice-level verified collected KRW","UNKNOWN"]]
    manifest=[["Source","Source Date"],["Payment Outstanding","2026-10-26"],
              ["Payment Receipt","2026-10-26"],["eTax Invoice","2026-10-26"]]
    qq=[["invoice_number","issued_month","amount_krw"],
        ["209126000001","2026-10","500"],
        ["209126000002","2026-10","250"]]
    css=[["invoice_number","invoice_month","amount_krw"],
         ["209126000001","2026-10","500 KRW"]]
    return monthly,legacy,payment,manifest,qq,css

class FinancialCrossSourceTests(unittest.TestCase):
    def test_discrepancy_preserves_verified_billing_and_flags(self):
        r=verify(*fixture(),month="2026-10")
        self.assertEqual(r["verified_billing_krw"],149880500)
        self.assertEqual(r["forecast_separate_krw"],21152370)
        self.assertEqual(r["qq_only_krw"],250)
        self.assertIn("LEGACY_3WAY_STALE_DO_NOT_PROMOTE",r["flags"])
        self.assertIn("PAYMENT_PROOF_REQUIRED",r["flags"])
        self.assertEqual(r["payment_verified_collected"],"UNKNOWN")
        self.assertEqual(r["status"],"REVIEW_REQUIRED")
    def test_matching_sources_pass(self):
        v=fixture()
        v[1][2][1]="67743500"
        v[3][1][1]="2026-10-29"
        v[2][1][1]="100"
        v[5].append(["209126000002","2026-10","250"])
        r=verify(*v,month="2026-10")
        self.assertEqual(r["status"],"PASS")
        self.assertEqual(r["payment_verified_collected"],100)
    def test_source_invoice_amount_conflict_fails(self):
        v=fixture()
        v[5][1][2]="999"
        with self.assertRaisesRegex(ValueError,"SOURCE_INVOICE_AMOUNTS_DISAGREE"):
            verify(*v,month="2026-10")
    def test_monthly_billing_mismatch_fails(self):
        v=fixture()
        v[0][1][12]="111"
        with self.assertRaisesRegex(ValueError,"VERIFIED_BILLING_SUM_MISMATCH"):
            verify(*v,month="2026-10")
    def test_conflicting_duplicate_invoice_fails(self):
        v=fixture()
        v[4].append(["209126000001","2026-10","777"])
        with self.assertRaisesRegex(ValueError,"CONFLICTING_DUPLICATE_INVOICE"):
            verify(*v,month="2026-10")
    def test_empty_receipt_evidence_status_fails(self):
        v=fixture()
        v[2][1][1]=""
        with self.assertRaisesRegex(ValueError,"PAYMENT_EVIDENCE_STATUS_MISSING"):
            verify(*v,month="2026-10")
    def test_forecast_does_not_change_verified_billing(self):
        v=fixture()
        v[0][1][3]="₩999,999,999"
        r=verify(*v,month="2026-10")
        self.assertEqual(r["verified_billing_krw"],149880500)
        self.assertEqual(r["forecast_separate_krw"],999999999)

if __name__=="__main__":
    unittest.main()
