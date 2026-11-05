"""Safety tests: local review template must be blank/unapproved by default."""
import unittest

from make_existing_change_template import blank_request

SF = "006000000000000AAA"
OPP = "Opp-2099-01-01-333333"
IDS = {
    "account_record_id": "001000000000000AAA",
    "contact_record_id": "003000000000000AAA",
}
CURRENT = {
    "Opportunity Name": "Synthetic Prior Deal",
    "Amount": "100.00",
    "Close Date": "2099-02-03",
}


class PrivateDraftTemplateTests(unittest.TestCase):
    def test_default_template_is_unapproved_and_no_change(self):
        d = blank_request(SF, OPP, IDS, CURRENT, "REQ-synthetic-001")
        self.assertFalse(d["reviewed_current_deal_values"])
        self.assertFalse(d["save_allowed"])
        self.assertEqual(d["changes"], {})
        self.assertEqual(d["expected_before_values"], {})
        self.assertEqual(d["observed_current_values_reference_only"], CURRENT)
        self.assertEqual(d["expected_account_record_id"], IDS["account_record_id"])
        self.assertEqual(d["expected_contact_record_id"], IDS["contact_record_id"])

    def test_missing_current_amount_fails(self):
        with self.assertRaises(ValueError):
            blank_request(SF, OPP, IDS,
                          {"Opportunity Name": "Synthetic", "Close Date": "2099-01-01"},
                          "REQ-synthetic-002")

    def test_missing_current_name_fails(self):
        x = dict(CURRENT)
        x["Opportunity Name"] = ""
        with self.assertRaises(ValueError):
            blank_request(SF, OPP, IDS, x, "REQ-synthetic-003")

    def test_missing_id_fails(self):
        with self.assertRaises(ValueError):
            blank_request("", OPP, IDS, CURRENT, "REQ-synthetic-004")
        with self.assertRaises(ValueError):
            blank_request(SF, "", IDS, CURRENT, "REQ-synthetic-005")

    def test_reference_values_not_copied_to_changes(self):
        d = blank_request(SF, OPP, IDS, CURRENT, "REQ-synthetic-006")
        self.assertNotIn("Amount", d["changes"])
        self.assertNotIn("Close Date", d["changes"])
        self.assertNotIn("Opportunity Name", d["expected_before_values"])


if __name__ == "__main__":
    unittest.main()
