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
    def test_payment_trailing_duplicates_review_only(self):
        from latest_four_schema_audit import validate_header_scope
        header=["canonical_"+str(i) for i in range(1,18)]+["Formula"]*35
        _,_,pairs=header_fingerprint(header)
        self.assertEqual(len(pairs),34)
        self.assertEqual(validate_header_scope("Payment Outstanding",header,pairs),
                         "REVIEW_NONCANONICAL_TRAILING_DUPLICATES")
    def test_prepayment_tail_safe_review(self):
        from latest_four_schema_audit import validate_header_scope
        header=["Prepay"+str(i) for i in range(1,20)]+["Formula"]*33
        _,_,pairs=header_fingerprint(header)
        self.assertEqual(pairs[0],(20,21))
        self.assertEqual(validate_header_scope("Prepayments",header,pairs),
                         "REVIEW_NONCANONICAL_TRAILING_DUPLICATES")
    def test_prepayment_core_duplicate_still_blocked(self):
        from latest_four_schema_audit import validate_header_scope
        header=["Prepay"+str(i) for i in range(1,20)]+["Formula"]*33
        header[10]=header[9]
        _,_,pairs=header_fingerprint(header)
        with self.assertRaisesRegex(RuntimeError,"Duplicate nonempty header"):
            validate_header_scope("Prepayments",header,pairs)

    def test_payment_duplicate_in_core_still_fails(self):
        from latest_four_schema_audit import validate_header_scope
        header=["canonical_"+str(i) for i in range(1,18)]+["Formula"]*35
        header[4]=header[3]
        _,_,pairs=header_fingerprint(header)
        with self.assertRaisesRegex(RuntimeError,"Duplicate nonempty header"):
            validate_header_scope("Payment Outstanding",header,pairs)
    def test_payment_missing_core_header_still_fails(self):
        from latest_four_schema_audit import validate_header_scope
        header=["canonical_"+str(i) for i in range(1,18)]+["Formula"]*35
        header[16]=""
        _,_,pairs=header_fingerprint(header)
        with self.assertRaisesRegex(RuntimeError,"Missing canonical header"):
            validate_header_scope("Payment Outstanding",header,pairs)
    def test_all_four_formats_reported_even_if_receipt_blocked(self):
        import contextlib
        import io
        import os
        from unittest.mock import patch
        import latest_four_schema_audit as mod
        selections={fmt:{"sheet_id":slug} for fmt,slug in (
            ("Payment Outstanding","po"),("Payment Receipt","pr"),
            ("eTax Invoice","et"),("Prepayments","pp"))}
        headers={
            "po":["Pay"+str(i) for i in range(1,18)]+["Formula"]*35,
            "pr":["Deposit Date"]+["Repeat"]*51,
            "et":["eTax"+str(i) for i in range(1,53)],
            "pp":["Prepay"+str(i) for i in range(1,53)],
        }
        def fake_api(path,bearer=None,payload=None):
            if payload is not None:
                return {"tenant_access_token":"dummy"}
            if "sheets/query" in path:
                return {"sheets":[]}
            for slug,rows in headers.items():
                if slug+"!A1:AZ1" in path:
                    return {"valueRange":{"values":[rows]}}
            raise AssertionError("Unexpected mocked Feishu route")
        stream=io.StringIO()
        with patch.object(mod,"api",side_effect=fake_api), patch.object(
            mod,"select",return_value=(selections,0)), patch.dict(os.environ,{
            "FEISHU_APP_ID":"dummy","FEISHU_APP_SECRET":"dummy"}):
            with contextlib.redirect_stdout(stream):
                with self.assertRaisesRegex(RuntimeError,"HEADER_VALIDATION_BLOCKED_FORMATS=Payment Receipt"):
                    mod.main()
        output=stream.getvalue()
        self.assertIn("SCHEMA_HEADER_BLOCKED: Payment Receipt",output)
        self.assertIn("FORMAT: Prepayments",output)
        self.assertIn("FORMAT: eTax Invoice",output)
        self.assertIn("SCHEMA_AUDIT: REVIEW_REQUIRED",output)
        self.assertNotIn("Deposit Date",output)

    def test_other_formats_duplicate_always_fail(self):
        from latest_four_schema_audit import validate_header_scope
        header=["Date","Customer Name","Amount","CMS No.","","Date","CMS","Amount","","Date","Customer","Amount","CMS"]
        _,_,pairs=header_fingerprint(header)
        with self.assertRaisesRegex(RuntimeError,"Duplicate nonempty header"):
            validate_header_scope("Payment Receipt",header,pairs)

    def test_empty_header_still_fails(self):
        with self.assertRaisesRegex(RuntimeError,"Empty header"):
            header_fingerprint([""," ",""])
    def test_blank_columns_not_duplicates(self):
        _,n,pairs=header_fingerprint(["A","","","B"])
        self.assertEqual(n,4)
        self.assertEqual(pairs,[])

    def test_feishu_json_null_is_not_a_literal_duplicate_label(self):
        from latest_four_schema_audit import validate_header_scope
        _,width,pairs=header_fingerprint(["Deposit Date",None,None,None])
        self.assertEqual(width,4)
        self.assertEqual(pairs,[])
        with self.assertRaisesRegex(RuntimeError,"Missing canonical header"):
            validate_header_scope("Payment Receipt",["Deposit Date"]+[None]*51,pairs)

    def test_no_duplicate_still_requires_canonical_core(self):
        from latest_four_schema_audit import validate_header_scope
        header=["Unique"+str(i) for i in range(1,17)]+[""]+["Tail"]*35
        with self.assertRaisesRegex(RuntimeError,"Missing canonical header"):
            validate_header_scope("Payment Outstanding",header,[])

    def test_receipt_panels_need_all_three_identity_groups(self):
        from latest_four_schema_audit import validate_header_scope
        header=["A","B","C","D","","F","G","H","","J","","L","M"]
        with self.assertRaisesRegex(RuntimeError,"column_positions=11"):
            validate_header_scope("Payment Receipt",header,[])

    def test_etax_paid_and_issued_columns_cannot_be_missing(self):
        from latest_four_schema_audit import validate_header_scope
        header=["Core"+str(i) for i in range(1,36)]
        header[32]=None
        with self.assertRaisesRegex(RuntimeError,"column_positions=33"):
            validate_header_scope("eTax Invoice",header,[])

    def test_object_cell_is_not_converted_to_duplicate_repr(self):
        with self.assertRaisesRegex(RuntimeError,"HEADER_CELL_NON_TEXT_TYPE"):
            header_fingerprint(["A",{"text":"B"}])

if __name__=="__main__":
    unittest.main()
