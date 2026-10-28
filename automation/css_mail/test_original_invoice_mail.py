import unittest
from tax_invoice_extract import original_issued_mail,extract

class OriginalInvoiceTests(unittest.TestCase):
    def base(self, subject):
        return {"direction":"INBOUND","from_email":"css@novogene-amea.com","subject":subject,"in_reply_to":""}
    def test_original_notice_accepted(self):
        self.assertTrue(original_issued_mail(self.base("❗️Notice: Invoice Issued & Statement Confirmed – H209SC26088039")))
    def test_replies_and_forwards_rejected(self):
        for prefix in ("Re: ","RE: ","회신: ","Fw: ","Fwd: ","전달: "):
            with self.subTest(prefix=prefix):
                self.assertFalse(original_issued_mail(self.base(prefix+"❗️Notice: Invoice Issued & Statement Confirmed")))
    def test_sender_and_thread_guard(self):
        r=self.base("❗️Notice: Invoice Issued & Statement Confirmed")
        r["from_email"]="taehoon.kim@novogene.com"
        self.assertFalse(original_issued_mail(r))
        r["from_email"]="css@novogene-amea.com"
        r["in_reply_to"]="<previous@sample>"
        self.assertFalse(original_issued_mail(r))
    def test_amount_extracted_only_from_pdf_filename(self):
        p=extract("TAX INVOICE-209126000964-H209SC26088039-SQ-AMEA2026073124-KRW4438500.00.pdf")
        self.assertEqual(p[0],"209126000964")
        self.assertEqual(p[4],4438500)
        self.assertIsNone(extract("Re: Notice: Invoice Issued & Statement Confirmed 4438500"))
if __name__=="__main__":unittest.main()
