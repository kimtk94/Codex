"""Exact QQ-to-legacy invoice key reconciliation; all sample names are synthetic."""
import datetime as dt
import unittest
from css_invoice_legacy_key_bridge import compare,KST

NOW=dt.datetime(2026,10,31,16,10,tzinfo=KST)
SOURCE_HEAD=["invoice_number","amount_krw","project_id","h_project_number",
             "po_reference","attachment_filename","subject","received_at",
             "imap_uid","ingest_key","validation_status","extracted_at_utc"]
LEGACY_HEAD=["invoice_month","issued_at","invoice_number","amount_krw","project_id",
             "h_project_number","po_reference","institution","service","description",
             "attachment_filename","subject","uid","source_row"]
NET_HEAD=["Month","Issued Invoice Gross KRW (VAT incl)","Issued Net Revenue KRW (VAT excl)",
          "Issued Net Revenue kUSD @1500","Issued Invoice Count"]
def filename(id,amount):
    return ("TAX INVOICE-"+id+"-H209SC26100560-SQ-AMEA2026100213-KRW"+
            str(amount)+".00.pdf")
def original(id,amount):
    return [id,str(amount),"AMEA2026100213","H209SC26100560","SQ",
            filename(id,amount),"❗️Notice: Invoice Issued & Statement Confirmed - "+id,
            "2026-10-28T12:30:00+08:00","40012","INBOX|123|40012","FILENAME_PARSED","now"]
def legacy(id,amount):
    return ["2026-10","2026-10-28 13:30:00",id,
            str(amount)+" KRW","AMEA2026100213","H209SC26100560",
            "SQ","","","",filename(id,amount),"Notice", "inbox:1","42"]
def case():
    a="209126001010";b="209126001012"
    return ([SOURCE_HEAD,original(a,1100),original(b,2200)],
            [LEGACY_HEAD,legacy(a,1100)],
            [NET_HEAD,["2026-10","3300","3000","0.002","2"]])

class InvoiceBridgeTests(unittest.TestCase):
    def test_new_exact_invoice_key_is_missing_from_legacy_only(self):
        a,b,c=case()
        rows,info=compare(a,b,c,NOW)
        self.assertEqual(info["canonical_count"],2)
        self.assertEqual(info["legacy_count"],1)
        self.assertEqual(info["new_qq_only_count"],1)
        self.assertEqual(info["new_qq_only_gross"],2200)
        self.assertEqual(info["canonical_net"],3000)
        self.assertEqual(info["overlap_conflicts"],0)
        self.assertEqual(info["source_writes"],0)
        self.assertEqual([r[5] for r in rows],["MATCHED_LEGACY","NEW_QQ_ONLY"])
        self.assertTrue(all(r[8]=="CANONICAL_ALREADY_COUNTED;DO_NOT_ADD_AGAIN" for r in rows))

    def test_conflicting_same_key_blocks(self):
        a,b,c=case()
        b[1][3]="1000 KRW";b[1][10]=filename(b[1][2],1000)
        with self.assertRaisesRegex(ValueError,"OVERLAPPING_INVOICE_AMOUNT_CONFLICT"):
            compare(a,b,c,NOW)

    def test_old_only_key_blocks(self):
        a,b,c=case()
        b.append(legacy("209126001014",4400))
        with self.assertRaisesRegex(ValueError,"LEGACY_KEY_NOT_IN_QQ_CANONICAL"):
            compare(a,b,c,NOW)

    def test_monthly_parity_blocks_if_new_qq_only_is_dropped(self):
        a,b,c=case();c[1][1]="1100"
        with self.assertRaisesRegex(ValueError,"OFFICIAL_MONTH_TOTAL_CONFLICT"):
            compare(a,b,c,NOW)

    def test_qq_duplicate_conflict_blocks(self):
        a,b,c=case();a.append(original("209126001010",3300))
        with self.assertRaisesRegex(ValueError,"ORIGINAL_KEY_CONFLICT"):
            compare(a,b,c,NOW)

    def test_old_duplicate_blocks(self):
        a,b,c=case();b.append(legacy("209126001010",1100))
        with self.assertRaisesRegex(ValueError,"LEGACY_DUPLICATE_KEY"):
            compare(a,b,c,NOW)

    def test_invalid_filename_and_reply_are_not_counted(self):
        a,b,c=case()
        bad=original("209126001014",9900)
        bad[6]="Re: "+bad[6]
        a.append(bad)
        self.assertEqual(compare(a,b,c,NOW)[1]["canonical_count"],2)
        a[1][5]="no-attachment.pdf"
        with self.assertRaisesRegex(ValueError,"ORIGINAL_FILENAME_OR_AMOUNT_INVALID"):
            compare(a,b,c,NOW)

if __name__=="__main__":
    unittest.main()
