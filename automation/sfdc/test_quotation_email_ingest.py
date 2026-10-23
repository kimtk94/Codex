#!/usr/bin/env python3
"""Offline Salesforce subscription-export regression; no mailbox access."""
import sys, pathlib, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from quotation_email_ingest import parse_attachment
class QuotationEmailTests(unittest.TestCase):
    def test_korean_html_xls(self):
        cols=["Quotation: SFDC Quotation ID","*Account Id","Account Name","Contact ID","Contact Name","Opportunity ID","Opportunity Name","Quotation: ID","Quotation Name","Active","Sync CMS","Exclude Tax After Discount USD","Quotation Create Date","Contract Creation"]
        row=["QID-2026-10-23-12345","","이화여자대학교","","","Opp-2026-10-23-12345","","a0PTK00000za6F3","이화-인간유전체","1","1","2,500.00","10/23/2026",""]
        html='<head><META http-equiv="Content-Type" content="text/html; charset=euc-kr"></head><table><tr>'+''.join('<th>'+x+'</th>' for x in cols)+'</tr><tr>'+''.join('<td>'+x+'</td>' for x in row)+'</tr></table>'
        found=parse_attachment(html.encode("euc-kr"),"Automation Quotation Report.xls")
        self.assertEqual(len(found),1)
        self.assertEqual(found[0][1],"1")
        self.assertEqual(found[0][2],2500.0)
        self.assertEqual(found[0][3],"USD")
        self.assertIn("이화",found[0][6])
    def test_small_xlsx_true_active(self):
        import io
        from openpyxl import Workbook
        wb=Workbook()
        ws=wb.active
        ws.append(["Quotation: SFDC Quotation ID","Opportunity ID","Quotation: ID","Quotation Name","Active","Exclude Tax After Discount USD"])
        ws.append(["QID-2026-10-23-12345","006TEST","a0PTK00000za6F3","Test Quote","TRUE","1,250.50"])
        out=io.BytesIO()
        wb.save(out)
        found=parse_attachment(out.getvalue(),"report.xlsx")
        self.assertEqual(len(found),1)
        self.assertEqual(found[0][1],"1")
        self.assertEqual(found[0][2],1250.5)
    def test_missing_quote_fields_is_not_accepted(self):
        html=b"<table><tr><th>Opportunity Name</th><th>Amount</th></tr><tr><td>A</td><td>250</td></tr></table>"
        self.assertEqual(parse_attachment(html,"bad.xls"),[])
if __name__=="__main__":unittest.main()
