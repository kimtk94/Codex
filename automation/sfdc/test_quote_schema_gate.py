import unittest

from quote_schema_gate import missing_quotation_columns, validate_quotation_columns

OPPORTUNITY_HEADERS = [
    "Opportunity Name", "Account Name", "Main Contact",
    "Opportunity Currency", "Close Date", "Service Line",
    "Amount", "Stage", "Forecast Category",
    "Progress Description", "Amount (converted) Currency",
]

VALID_QUOTE_HEADERS = [
    "SFDC Quotation ID", "Quotation ID", "Opportunity ID",
    "Active", "Quotation Name", "Opportunity Name",
]


class QuoteSourceSchemaTests(unittest.TestCase):
    def test_reject_actual_opportunity_shaped_source(self):
        missing = missing_quotation_columns(OPPORTUNITY_HEADERS)
        self.assertEqual(len(missing), 4)
        with self.assertRaisesRegex(ValueError, "refusing downstream Sheet writes"):
            validate_quotation_columns(OPPORTUNITY_HEADERS)

    def test_accept_valid_export_columns(self):
        self.assertTrue(validate_quotation_columns(VALID_QUOTE_HEADERS))
        self.assertEqual(missing_quotation_columns(VALID_QUOTE_HEADERS), [])

    def test_accept_explicit_equivalent_names(self):
        sample = ["Salesforce Quotation ID", "AMEA No.",
                  "OpportunityId", "IsActive"]
        self.assertTrue(validate_quotation_columns(sample))

    def test_header_matching_ignores_spaces_and_case(self):
        sample = [" sfDC Quotation ID ", " quotation id ",
                  " opportunity id ", " is active "]
        self.assertTrue(validate_quotation_columns(sample))

    def test_reject_opportunity_rows_with_fake_quote_label_only(self):
        invalid = OPPORTUNITY_HEADERS + ["Quotation Name"]
        self.assertIn("SFDC quotation record ID", missing_quotation_columns(invalid))
        with self.assertRaises(ValueError):
            validate_quotation_columns(invalid)

    def test_reject_missing_active_status(self):
        invalid = [x for x in VALID_QUOTE_HEADERS if x != "Active"]
        self.assertIn("active checkbox", missing_quotation_columns(invalid))

    def test_reject_missing_opportunity_link(self):
        invalid = [x for x in VALID_QUOTE_HEADERS if x != "Opportunity ID"]
        self.assertIn("related opportunity ID", missing_quotation_columns(invalid))

    def test_reject_blank_source(self):
        with self.assertRaises(ValueError):
            validate_quotation_columns([])


if __name__ == "__main__":
    unittest.main()
