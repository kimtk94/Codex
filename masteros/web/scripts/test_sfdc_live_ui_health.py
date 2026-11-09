import unittest
from sfdc_live_ui_health import summarize

class SalesforceLiveHealthTests(unittest.TestCase):
    def test_all_pass(self):
        out = summarize({"lead": True, "opportunity": True, "quote": True})
        self.assertEqual(out["status"], "PASS")
        self.assertTrue(out["read_only"])
        self.assertFalse(out["crm_write_verified"])
    def test_partial_does_not_pass(self):
        r = summarize({"lead": True, "opportunity": True, "quote": False})
        self.assertEqual(r["status"], "BLOCK")
        self.assertEqual(r["quote_view"], "BLOCK")
    def test_missing_checks_do_not_pass(self):
        self.assertEqual(summarize({})["status"], "BLOCK")
        self.assertEqual(summarize({"lead": "PASS"})["lead_view"], "BLOCK")

if __name__ == "__main__":
    unittest.main()
