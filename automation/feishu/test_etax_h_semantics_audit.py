#!/usr/bin/env python3
"""Read-only eTax semantic classification must not leak raw status/customer fields."""
import unittest
from unittest import mock
from qq_mail_ingest import SafeError
import etax_h_semantics_audit as s


class SemanticProofTests(unittest.TestCase):
    def test_header_allowlist_never_print_invoice_number_or_url(self):
        self.assertEqual(s.safe_header("e-Tax Issued?"),"e-Tax Issued?")
        self.assertEqual(s.safe_header("发票状态"),"发票状态")
        self.assertEqual(s.safe_header("20910000203"),"HEADER_NOT_CLASSIFIABLE")
        self.assertEqual(s.safe_header("https://private.example"),"HEADER_NOT_CLASSIFIABLE")

    def test_detect_hyperlink_pdf_and_negative_word_before_any_issuance_assumption(self):
        self.assertIn("PDF_OR_FILE",s.signals("Invoice_203.pdf"))
        self.assertIn("URL_OR_LINK",s.signals("https://example.org/abc"))
        self.assertIn("NEGATIVE_OR_PENDING_WORD",s.signals("NOT ISSUED"))
        self.assertIn("CHINESE_TEXT",s.signals("尚未生成电子发票"))
        self.assertEqual(s.cell_data("NOT ISSUED")["classification"],
                         "TRACKING_MARKED_NOT_ISSUED")

    def test_read_get_only_and_refuse_missing_value_range(self):
        fake={"valueRange":{"values":[["x","y","z","20910000208","","","","未知状态"]]}}
        with mock.patch.object(s,"api",return_value=fake) as a:
            r=s.row_read("token","sheet",24,24)
        self.assertEqual(len(r),1)
        a.assert_called_once()
        self.assertEqual(a.call_args.args[0],"GET")
        self.assertIn("WI6msu7UihcZQotx8XKjDbFypvh",a.call_args.args[1])
        with mock.patch.object(s,"api",return_value={}):
            with self.assertRaisesRegex(SafeError,"RANGE_INVALID"):
                s.row_read("token","sheet",1,1)

    def test_target_id_and_h_must_match_full_scanned_D_H_snapshot(self):
        original=s.INTERESTING
        try:
            s.INTERESTING=("20910000208",)
            rows=[[""]*5 for _ in range(5)]
            rows[2]=["20910000208",None,None,None,"STATUS"]
            base=[""]*9
            base[3]="20910000208"
            base[7]="DIFFERENT_STATUS"
            with mock.patch.object(s,"read_tracking",return_value=(rows,10)),\
                 mock.patch.object(s,"build_index",return_value={"20910000208":("STATUS",3)}),\
                 mock.patch.object(s,"find_sheet",return_value="sheet"),\
                 mock.patch.object(s,"row_read",side_effect=[[[""]*9],[base]]):
                with self.assertRaisesRegex(SafeError,"ID_OR_H_VALUE_CHANGED"):
                    s.audit("token")
        finally:
            s.INTERESTING=original

    def test_cancelled_or_repeated_etax_number_never_counts_as_valid_issuance_candidate(self):
        from contextlib import redirect_stdout
        import io
        original=s.INTERESTING
        try:
            s.INTERESTING=("20910000208","20910000209")
            rows=[[""]*5,["20910000208",None,None,None,"CERTIFICATE12345678"],
                  ["20910000209",None,None,None,"CERTIFICATE12345678"]]
            rec_a=[""]*10
            rec_b=[""]*10
            for rec,key in ((rec_a,"20910000208"),(rec_b,"20910000209")):
                rec[3]=key
                rec[6]="Kim Taehoon"
                rec[7]="CERTIFICATE12345678"
                rec[8]="issued"
            rec_b[9]="CANCELLED_DOCUMENT_REFERENCE"
            def row_read(token,sid,first,last):
                return [[""]*14] if first==1 else [rec_a] if first==2 else [rec_b]
            with mock.patch.object(s,"read_tracking",return_value=(rows,3)),\
                 mock.patch.object(s,"find_sheet",return_value="sheet"),\
                 mock.patch.object(s,"row_read",side_effect=row_read):
                output=io.StringIO()
                with redirect_stdout(output):
                    s.audit("token")
            text=output.getvalue()
            self.assertIn("ETAX_SEMANTIC_DUPLICATE_TAX_NUMBER",text)
            self.assertIn("J_cancel_number_present=true",text)
            self.assertIn("candidates=0",text)
            self.assertNotIn("CANCELLED_DOCUMENT_REFERENCE",text)
        finally:
            s.INTERESTING=original

    def test_only_target_invoice_row_is_fetched(self):
        original=s.INTERESTING
        calls=[]
        try:
            s.INTERESTING=("20910000208",)
            rows=[[""]*5 for _ in range(4)]
            rows[3]=["20910000208",None,None,None,"NO"]
            record=[""]*9
            record[3]="20910000208"
            record[7]="NO"
            def r(token,sid,first,last):
                calls.append((first,last))
                return [[""]*9] if first==1 else [record]
            with mock.patch.object(s,"read_tracking",return_value=(rows,1)),\
                 mock.patch.object(s,"build_index",return_value={"20910000208":("NO",4)}),\
                 mock.patch.object(s,"find_sheet",return_value="sheet"),\
                 mock.patch.object(s,"row_read",side_effect=r):
                s.audit("token")
            self.assertEqual(calls,[(1,1),(4,4)])
        finally:
            s.INTERESTING=original


if __name__=="__main__":
    unittest.main()
