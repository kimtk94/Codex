"""Safe Feishu header diagnostics; no Feishu API access or values."""
import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from latest_four_schema_audit import header_fingerprint

class HeaderDiagnosticTests(unittest.TestCase):
    def test_duplicates_report_positions_without_values(self):
        fingerprint,width,pairs=header_fingerprint(["Invoice","Balance","Invoice",""])
        self.assertEqual(width,4)
        self.assertEqual(pairs,[(1,3)])
        self.assertEqual(len(fingerprint),16)
        self.assertNotIn("Invoice",fingerprint)
    def test_casefold_and_spaces_are_duplicate(self):
        _,_,pairs=header_fingerprint([" amount ","AMOUNT","Unique"])
        self.assertEqual(pairs,[(1,2)])
    def test_empty_header_still_fails(self):
        with self.assertRaisesRegex(RuntimeError,"Empty header"):
            header_fingerprint([""," ",""])
    def test_blank_columns_not_duplicates(self):
        _,n,pairs=header_fingerprint(["A","","","B"])
        self.assertEqual(n,4)
        self.assertEqual(pairs,[])

if __name__=="__main__":
    unittest.main()
