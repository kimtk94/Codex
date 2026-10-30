"""Offline verification for original QQ Invoice to central source backfill."""
import unittest
import qq_invoice_central_sync as m


AMEA="AMEA2026100213"
H="H209SC26100527"
INVOICE="209126001012"
AMOUNT=1622500
SUBJECT=("❗️Notice: Invoice Issued & Statement Confirmed – J001-X209SC26100527-Z01 "
         "-209126001012 - "+H+" - Korea-Yonsei Univ.-6-mRNA-Seq-6Gb-WOBI-"+AMEA)
FILE="TAX\r\n INVOICE-"+INVOICE+"-"+H+"-SQ-"+AMEA+"-KRW1622500.00.pdf"

def sample():
    return [INVOICE,str(AMOUNT),AMEA,H,"SQ",FILE,SUBJECT,
            "2026-10-28T12:20:31+08:00","40600","INBOX|1776302013|40600",
            "FILENAME_PARSED","2026-10-29T15:29:00+00:00"]

def central():
    h=m.HEAD
    prev=["2026-10","2026-10-19 07:34:32","209126000964","4,438,500 KRW",
          "AMEA2026073124","H209SC26088039","SQ","GenixCure","WGS",
          "Korea-GenixCure-1-WGS","TAX INVOICE-209126000964.pdf","Notice",
          "inbox:39173","40869",""]
    return [h,prev]

class InvoiceSyncTests(unittest.TestCase):
    def test_original_notice_parses_filename_amount_and_kst(self):
        r=m.original_record(sample())
        self.assertEqual(r[0],"2026-10")
        self.assertEqual(r[1],"2026-10-28 13:20:31")
        self.assertEqual(r[2],INVOICE)
        self.assertEqual(r[3],"1,622,500 KRW")
        self.assertEqual(r[7],"Yonsei Univ.")
        self.assertEqual(r[8],"mRNA-Seq")
        self.assertEqual(r[12],"inbox:40600")
        self.assertEqual(r[14],"INBOX|1776302013|40600")

    def test_missing_invoice_added_only_once_and_idempotent(self):
        src=[["invoice_number","amount_krw"]]+[sample()]
        new,count,old=m.plan(src,central())
        self.assertEqual((count,old,len(new)),(1,1,1))
        same=central()
        same.append(new[0])
        again,total,_=m.plan(src,same)
        self.assertEqual((len(again),total),(0,1))

    def test_reply_or_filename_conflict_blocks(self):
        r=sample()
        r[6]="Re: "+r[6]
        with self.assertRaisesRegex(RuntimeError,"QQ_INVOICE_NONORIGINAL"):
            m.original_record(r)
        r=sample()
        r[5]=r[5].replace("1622500","1722500")
        with self.assertRaisesRegex(RuntimeError,"FILENAME_AMOUNT_CONFLICT"):
            m.original_record(r)

    def test_gross_amount_conflict_prevents_reimport(self):
        src=[["invoice_number","amount_krw"],sample()]
        dest=central()
        bad=m.original_record(sample())
        bad[3]="1,722,500 KRW"
        dest.append(bad)
        with self.assertRaisesRegex(RuntimeError,"QQ_CENTRAL_AMOUNT_MISMATCH"):
            m.plan(src,dest)

    def test_source_uid_and_conflicting_duplicate_proof(self):
        r=sample()
        r[9]="INBOX|1776302013|99999"
        with self.assertRaisesRegex(RuntimeError,"QQ_INVOICE_SOURCE_UID_INVALID"):
            m.original_record(r)
        r=sample()
        x=sample()
        x[9]="INBOX|1776302012|40600"
        with self.assertRaisesRegex(RuntimeError,"QQ_DUPLICATE_ORIGINAL_CONFLICT"):
            m.plan([["invoice_number","amount_krw"],r,x],central())

    def test_missing_header_and_empty_source_are_blocked(self):
        with self.assertRaisesRegex(RuntimeError,"QQ_INVOICE_SCHEMA_INVALID"):
            m.plan([],central())
        with self.assertRaisesRegex(RuntimeError,"CENTRAL_INVOICE_SCHEMA_INVALID"):
            m.plan([["invoice_number","amount_krw"],sample()],[["A","B"]])

if __name__=="__main__":
    unittest.main()
