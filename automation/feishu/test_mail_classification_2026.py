#!/usr/bin/env python3
"""Offline safety regression for QQ Mail 2026 classification."""
import unittest
from datetime import datetime, timezone
import mail_classification_2026 as m


class Classification2026Tests(unittest.TestCase):
    def mail(self, subject, **overrides):
        row = {"Subject": subject, "Direction": "INBOUND",
               "From": "Novogene <css@novogene-amea.com>",
               "To": "taehoon.kim@novogene.com",
               "Received At": "2026-11-05T09:00:00+09:00"}
        row.update(overrides)
        return row

    def test_only_2026_or_later_dates_in_kst(self):
        self.assertFalse(m.since_2026("2025-12-31T14:59:59Z"))
        self.assertTrue(m.since_2026("2025-12-31T15:00:00Z"))
        self.assertTrue(m.since_2026("2026-11-05T09:00:00+09:00"))
        self.assertFalse(m.since_2026("2026-01-01"))
        self.assertFalse(m.since_2026("garbage"))

    def test_official_original_invoice_requires_pdf_filename(self):
        sub = "❗️Notice: Invoice Issued & Statement Confirmed"
        row = self.mail(sub)
        p = m.classify(row, ["TAX INVOICE-209126000999-H209SC26065705-A1-AMEA2026042239-KRW 1100000.00.pdf"],
                       inspected=True, user_email="taehoon.kim@novogene.com")
        self.assertEqual(p["Primary Category"], "TAX_INVOICE")
        self.assertEqual(p["Invoice Number"], "209126000999")
        self.assertEqual(p["Tax Invoice Gross KRW"], 1100000)
        self.assertEqual(p["Finance Classification"], "ACTUAL_INVOICE")
        self.assertEqual(p["Direct Recipient"], "YES")
        self.assertEqual(p["Ownership"], "NOT_VERIFIED")

    def test_invoice_without_verified_filename_not_booked(self):
        p = m.classify(self.mail("❗️Notice: Invoice Issued & Statement Confirmed"))
        self.assertEqual(p["Finance Classification"], "NONE")
        self.assertIsNone(p["Tax Invoice Gross KRW"])
        self.assertEqual(p["Milestone"], "INVOICE_NOTICE_UNVERIFIED")

    def test_forward_is_never_invoice_value(self):
        p = m.classify(self.mail("Re: ❗️Notice: Invoice Issued & Statement Confirmed"),
                       ["TAX INVOICE-209126000999-H209SC26065705-A1-AMEA2026042239-KRW 1100000.00.pdf"],
                       inspected=True)
        self.assertNotEqual(p["Finance Classification"], "ACTUAL_INVOICE")

    def test_statement_not_invoice(self):
        p = m.classify(self.mail("Final Report & Statement Ready for Confirmation J001-X209SC26065705-Z01"))
        self.assertEqual(p["Primary Category"], "STATEMENT")
        self.assertEqual(p["Finance Classification"], "PENDING_UNPRICED")
        self.assertIsNone(p["Tax Invoice Gross KRW"])

    def test_sif_request_not_submitted_and_css_received_approved(self):
        self.assertEqual(m.classify(self.mail("Please Submit SIF"))["SIF Evidence"], "REQUEST_ONLY")
        self.assertEqual(m.classify(self.mail("SIF Received"))["SIF Evidence"], "RECEIVED")
        self.assertEqual(m.classify(self.mail("SIF Approved"))["SIF Evidence"], "APPROVED")
        outside = self.mail("SIF Approved", **{"From": "customer@university.edu"})
        self.assertNotEqual(m.classify(outside)["SIF Evidence"], "APPROVED")

    def test_quote_value_always_unverified(self):
        p = m.classify(self.mail("For Approval Quotation Alert AMEA2026042239"))
        self.assertEqual(p["Primary Category"], "QUOTE")
        self.assertEqual(p["Quote Amount Status"], "NOT_VERIFIED")

    def test_inbound_not_assumed_unanswered(self):
        p = m.classify(self.mail("Sample QC"))
        self.assertEqual(p["Reply Status"], "THREAD_REVIEW_REQUIRED")

    def test_system_report_not_quote(self):
        p = m.classify(self.mail("Report results (Leads)"))
        self.assertEqual(p["Primary Category"], "SYSTEM_REPORT")

    def test_data_deletion_urgent(self):
        p = m.classify(self.mail("Data Deletion in 10 Days"))
        self.assertEqual(p["Priority"], "URGENT")


if __name__ == "__main__":
    unittest.main()
