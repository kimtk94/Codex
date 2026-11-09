"""Offline regression tests; never connect to QQ."""
import io
import unittest
from openpyxl import Workbook
from quotation_process_mail_audit import (
    PROCESS_HEAD, inspect_attachment, REQUIRED,
)

class ProcessMailAuditTests(unittest.TestCase):
    def headers(self):
        return sorted(PROCESS_HEAD)

    def test_utf8_csv_exact_full_25_fields(self):
        h=self.headers()
        row=["fake"]*len(h)
        blob=(",".join(h)+"\n"+",".join(row)+"\n").encode()
        result=inspect_attachment(blob,"report.csv")
        self.assertEqual(result["kind"],"detail_exact_25")
        self.assertEqual(result["rows"],1)
        self.assertTrue(result["all_25_present"])

    def test_euc_kr_html_xls_schema(self):
        h=self.headers()
        html=('<head><meta charset="euc-kr"></head><table><tr>'+
              "".join("<th>"+x+"</th>" for x in h)+"</tr><tr>"+
              "".join("<td>1</td>" for _ in h)+"</tr></table>")
        result=inspect_attachment(html.encode("euc-kr"),"report.xls")
        self.assertEqual(result["kind"],"detail_exact_25")
        self.assertEqual(result["rows"],1)

    def test_summary_header_is_not_process(self):
        h=["Quotation: SFDC Quotation ID","Quotation: ID",
           "Exclude Tax After Discount USD","Opportunity ID"]
        blob=(",".join(h)+"\nQ1,a0P000000000000AAA,999,opp\n").encode()
        result=inspect_attachment(blob,"header.csv")
        self.assertEqual(result["kind"],"quotation_header")

    def test_xlsx_full_process(self):
        wb=Workbook();ws=wb.active
        ws.append(self.headers());ws.append(["synthetic"]*25)
        b=io.BytesIO();wb.save(b)
        result=inspect_attachment(b.getvalue(),"process.xlsx")
        self.assertEqual(result["kind"],"detail_exact_25")
        self.assertEqual(result["rows"],1)

    def test_different_column_order_allowed(self):
        cols=list(reversed(self.headers()))
        blob=(",".join(cols)+"\n"+",".join(["x"]*25)+"\n").encode()
        self.assertEqual(inspect_attachment(blob,"report.csv")["kind"],"detail_exact_25")

    def test_missing_required_process_fields_do_not_pass(self):
        h=sorted(PROCESS_HEAD-{"Unit Price USD"})
        blob=(",".join(h)+"\n"+",".join(["x"]*len(h))+"\n").encode()
        self.assertEqual(inspect_attachment(blob,"report.csv")["kind"],"other_schema")

    def test_required_subset_but_not_all_fields_has_partial_status(self):
        h=sorted(REQUIRED)
        blob=(",".join(h)+"\n"+",".join(["x"]*len(h))+"\n").encode()
        self.assertEqual(inspect_attachment(blob,"report.csv")["kind"],"detail_partial_schema")

if __name__=="__main__":
    unittest.main()
