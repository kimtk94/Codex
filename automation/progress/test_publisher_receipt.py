import unittest
from publish_evidence import validate_readback

class WriteReceiptTest(unittest.TestCase):
    def test_exact_cell_readback(self):
        self.assertEqual(["F6","H6"],validate_readback(
            [("F6","https://github.com/kimtk94/Codex/pull/297"),("H6","2026-10-26 20:00 KST")],
            [{"values":[["https://github.com/kimtk94/Codex/pull/297"]]},{"values":[["2026-10-26 20:00 KST"]]}]))
    def test_mismatch_rejects(self):
        with self.assertRaises(RuntimeError):
            validate_readback([("F6","correct")],[{"values":[["incorrect"]]}])
    def test_short_response_rejects(self):
        with self.assertRaises(RuntimeError):
            validate_readback([("F6","correct")],[])
if __name__ == "__main__":
    unittest.main()
