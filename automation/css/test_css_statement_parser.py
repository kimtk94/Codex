import unittest
from css_statement_parser import parse_statement, unique_observations


class StatementParserTests(unittest.TestCase):
    def setUp(self):
        self.mail = {
            "Mail UID": "inbox:34725",
            "Subject": "❗️Action Required: Final Report & Statement Ready For Confirmation – J001-X209SC26082826-Z01 - H209SC26082826 - AMEA2026073102",
            "Body Text": (
                "PO No. SQ-AMEA2026073102\n"
                "Item Description Quantity Unit Price Amount Currency\n"
                "NovaSeq X Plus RNA extraction mRNA library preparation 6.00 220000.00 1320000.00 KRW\n"
                "Total Amount 1320000.00 KRW"
            ),
        }

    def test_identifiers_and_amount(self):
        x = parse_statement(self.mail)
        self.assertEqual(x["amea"], ["AMEA2026073102"])
        self.assertEqual(x["contracts"], ["H209SC26082826"])
        self.assertEqual(x["subprojects"], ["X209SC26082826-Z01"])
        self.assertEqual(x["statement_total"], "1320000.00")
        self.assertEqual(x["revenue_effect"], "NONE")
        self.assertEqual(x["attribution"], "REVIEW_ONLY")
        self.assertIsNone(x["invoice_number"])

    def test_duplicate_mail_is_idempotent(self):
        self.assertEqual(len(unique_observations([self.mail, self.mail])), 1)

    def test_invalid_arithmetic_not_booked(self):
        bad = dict(self.mail)
        bad["Body Text"] = bad["Body Text"].replace("6.00 220000.00 1320000.00", "6.00 220000.00 1300000.00")
        x = parse_statement(bad)
        self.assertIsNone(x["statement_total"])
        self.assertEqual(x["revenue_effect"], "NONE")

    def test_unrelated_mail_skipped(self):
        self.assertIsNone(parse_statement({"Subject": "Invoice Issued", "Body Text": "Total Amount 1000 KRW"}))

    def test_missing_uid_rejected(self):
        invalid = dict(self.mail)
        invalid.pop("Mail UID")
        with self.assertRaises(ValueError):
            unique_observations([invalid])


if __name__ == "__main__":
    unittest.main()
