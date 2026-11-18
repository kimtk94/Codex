#!/usr/bin/env python3
import unittest

from revenue_monthly_retention_plan import compare_existing, old_only_status, numeric
from revenue_lifecycle_monthly import HEAD


def row(month, actual=0, pending=0, forecast=0, invoices=0, open_j=0,
        unknown=0, forecast_projects=0):
    r = [""] * len(HEAD)
    r[0], r[1], r[2], r[3] = month, actual, pending, forecast
    r[5], r[6], r[7], r[8] = invoices, open_j, unknown, forecast_projects
    return r


class RevenueMonthRetentionTests(unittest.TestCase):
    def test_forecast_only_month_can_be_retired_without_affecting_actual(self):
        old = [HEAD, row("2026-10", actual=100, invoices=1),
               row("2026-11", actual=200, invoices=2),
               row("2027-02", forecast=50, forecast_projects=1)]
        new = [HEAD, row("2026-10", actual=100, invoices=1),
               row("2026-11", actual=200, invoices=2)]
        result = compare_existing(old, new)
        self.assertEqual(result["old_only"], 1)
        self.assertEqual(result["old_only_forecast_only"], 1)
        self.assertEqual(result["old_only_protected"], 0)

    def test_real_actual_or_pending_removal_is_blocked(self):
        self.assertEqual(old_only_status(row("2026-11", actual=22, invoices=1)),
                         "FINANCIAL_PROOF_PRESENT_BLOCK")
        self.assertEqual(old_only_status(row("2026-11", pending=11, open_j=1)),
                         "FINANCIAL_PROOF_PRESENT_BLOCK")
        self.assertEqual(old_only_status(row("2026-11", unknown=1)),
                         "FINANCIAL_PROOF_PRESENT_BLOCK")

    def test_duplicate_month_block(self):
        old = [HEAD, row("2026-10"), row("2026-10")]
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE"):
            compare_existing(old, [HEAD, row("2026-10")])

    def test_numeric_malformed_negative_never_retired(self):
        with self.assertRaisesRegex(RuntimeError, "NON_NUMERIC"):
            numeric("PRIVATE")
        with self.assertRaisesRegex(RuntimeError, "INVALID_AMOUNT"):
            numeric("-100")
        self.assertEqual(numeric("1,000"), 1000)


if __name__ == "__main__":
    unittest.main()
