"""Offline falsification tests. Synthetic dates/prices do NOT certify real cash."""
from __future__ import annotations

import csv
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
from io import StringIO
import unittest

from historical_ca_alignment_audit import (
    FIELDS, PINNED_SHA256, TARGETS, VERSION, checked_csv, evaluate,
)


def generated():
    dates = [(date(2018, 6, 18) - timedelta(days=k)).isoformat()
             for k in reversed(range(1, 262))]
    dates += ["2018-06-18", "2023-09-19", "2023-09-20", "2023-09-21"]
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    qld, qqq = Decimal("10"), Decimal("100")
    for i, day in enumerate(dates):
        close_qld = qld * Decimal("1.001")
        close_qqq = qqq * Decimal("1.0005")
        r_qld = close_qld / qld - 1
        r_qqq = close_qqq / qqq - 1
        row = {key: "1" for key in FIELDS}
        row["date_ny"] = day
        row["close_qld"] = str(close_qld)
        row["close_qqq"] = str(close_qqq)
        row["return_1d_qld"] = str(r_qld) if i else ""
        row["return_1d_qqq"] = str(r_qqq) if i else ""
        row["relative_return_qld_minus_2x_qqq"] = (
            str(r_qld - 2*r_qqq) if i else "")
        writer.writerow(row)
        qld, qqq = close_qld, close_qqq
    return output.getvalue().encode()


class HistoricalCAAlignmentTests(unittest.TestCase):
    def test_simulated_study_is_descriptive_research_hold(self):
        body = generated()
        result = evaluate(body, pinned=False)
        self.assertEqual(result["version"], VERSION)
        self.assertEqual([x["event_ex_date"] for x in result["events"]],
                         ["2018-06-18", "2023-09-20"])
        self.assertEqual(result["source_sha256"], sha256(body).hexdigest())
        self.assertEqual(result["source_rows"], 265)
        self.assertTrue(result["research_hold"])
        self.assertFalse(result["issuer_cash_payment_certified"])
        self.assertFalse(result["issuer_nonpayment_certified"])
        self.assertFalse(result["independent_factor_certified"])
        self.assertFalse(result["independent_official_regular_close_certified"])
        self.assertTrue(all(
            e["same_source_data_cannot_disambiguate_cash_vs_adjustment"]
            for e in result["events"]
        ))

    def test_ranks_use_prior_252_only_no_future_lookahead(self):
        a = evaluate(generated(), pinned=False)
        for e in a["events"]:
            self.assertEqual(e["prior_252_abs_residual_count"], 252)
            self.assertGreaterEqual(e["prior_252_abs_residual_empirical_percentile"], 0)
            self.assertLessEqual(e["prior_252_abs_residual_empirical_percentile"], 100)

    def test_changed_pinned_hash_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "ORIGINAL_DRIVE_EXPORT_SHA256_MISMATCH"):
            evaluate(generated(), pinned=True)
        self.assertEqual(len(PINNED_SHA256), 64)

    def test_schema_misordered_fails_closed(self):
        body = generated()
        mangled = body.replace(b"date_ny,open_qld", b"newdate,open_qld", 1)
        with self.assertRaisesRegex(ValueError, "CSV_SCHEMA_CHANGED"):
            evaluate(mangled, pinned=False)

    def test_duplicate_date_fails_closed(self):
        lines = generated().splitlines(keepends=True)
        # One duplicate at last record, no need to recompute close arithmetic.
        split = lines[-1].split(b",")
        split[0] = b"2023-09-20"
        lines[-1] = b",".join(split)
        with self.assertRaisesRegex(ValueError, "CSV_UNSORTED_OR_DUPLICATE_DATE"):
            evaluate(b"".join(lines), pinned=False)

    def test_close_price_changed_without_return_recompute_fails(self):
        lines = generated().splitlines(keepends=True)
        parts = lines[100].split(b",")
        pos = FIELDS.index("close_qld")
        parts[pos] = b"9999"
        lines[100] = b",".join(parts)
        with self.assertRaisesRegex(ValueError, "CSV_RETURN_DOES_NOT_RECONCILE_CLOSE"):
            evaluate(b"".join(lines), pinned=False)

    def test_relative_residual_changed_without_returns_fails(self):
        lines = generated().splitlines(keepends=True)
        parts = lines[-1].split(b",")
        pos = FIELDS.index("relative_return_qld_minus_2x_qqq")
        parts[pos] = b"0.42\r\n"
        lines[-1] = b",".join(parts)
        with self.assertRaisesRegex(ValueError, "CSV_RESIDUAL_DOES_NOT_RECONCILE"):
            evaluate(b"".join(lines), pinned=False)

    def test_missing_an_event_date_fails(self):
        rows = generated().splitlines(keepends=True)
        # Remove the last QLD event and replace its day with an unrelated later day.
        rows[-2] = rows[-2].replace(b"2023-09-20", b"2023-09-18", 1)
        with self.assertRaisesRegex(ValueError, "CSV_UNSORTED_OR_DUPLICATE_DATE"):
            evaluate(b"".join(rows), pinned=False)

    def test_nonfinite_number_fails(self):
        lines = generated().splitlines(keepends=True)
        parts = lines[2].split(b",")
        parts[FIELDS.index("close_qqq")] = b"NaN"
        lines[2] = b",".join(parts)
        with self.assertRaisesRegex(ValueError, "CSV_CLOSE_MISSING"):
            evaluate(b"".join(lines), pinned=False)

    def test_future_observations_cannot_make_same_source_certified(self):
        r = evaluate(generated(), pinned=False)
        for e in r["events"]:
            self.assertIs(e["issuer_cash_payment_certified"], False)
            self.assertIs(e["dividend_nonpayment_certified"], False)
            self.assertIs(e["independent_adjustment_factor_certified"], False)
            self.assertIs(e["independent_16et_exchange_close_certified"], False)

    def test_first_row_return_nonempty_rejected(self):
        lines = generated().splitlines(keepends=True)
        p = lines[1].split(b",")
        p[FIELDS.index("return_1d_qld")] = b"0.1"
        lines[1] = b",".join(p)
        with self.assertRaisesRegex(ValueError, "FIRST_ROW_RETURNS_MUST_BE_EMPTY"):
            evaluate(b"".join(lines), pinned=False)

    def test_out_of_order_rows_fail(self):
        lines = generated().splitlines(keepends=True)
        lines[2], lines[3] = lines[3], lines[2]
        with self.assertRaisesRegex(ValueError, "CSV_UNSORTED_OR_DUPLICATE_DATE"):
            evaluate(b"".join(lines), pinned=False)


if __name__ == "__main__":
    unittest.main()
