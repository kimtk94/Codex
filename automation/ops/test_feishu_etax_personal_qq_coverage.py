"""Source-backed eTax-to-personal QQ review parity; never changes owner or paid status."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from feishu_etax_personal_qq_coverage import audit,original_qq

NOW=dt.datetime(2026,10,31,17,30,tzinfo=ZoneInfo("Asia/Seoul"))
def qq_row(invoice,amount):
    return [invoice,str(amount),"AMEA2026100213","H209SC26100560","SQ",
       "TAX INVOICE-"+invoice+"-H209SC26100560-SQ-AMEA2026100213-KRW"+str(amount)+".00.pdf",
       "❗️Notice: Invoice Issued & Statement Confirmed - "+invoice,
       "2026-10-28T12:30:00+08:00","40012","INBOX|123|40012","FILENAME_PARSED","now"]

def fixtures():
    cw=[["Key Type","Invoice Identifier","Base Amount KRW","Dated Sheet Amount KRW",
         "Evidence","Snapshot Date","Source Age Days","Payment / Issuance",
         "Review Boundary","Checked KST","GitHub Run"],
        ["CMS","209126001008",1110,1110,"ID_AND_AMOUNT_MATCHED_SNAPSHOT_ONLY",
         "2026-10-26",5,"NOT_VERIFIED","","",""],
        ["CMS","209126001012","",2200,"DATED_ONLY_OR_UNRESOLVED_REVIEW",
         "2026-10-26",5,"NOT_VERIFIED","","",""],
        ["ERP","209102199","",3500,"DATED_ONLY_OR_UNRESOLVED_REVIEW",
         "2026-10-26",5,"NOT_VERIFIED","","",""]]
    header=["x"]*35
    for i,label in [(4,"ERP Invoice Number"),(5,"CMS Invoice Num"),(15,"Amount"),(25,"Sales")]:
        header[i]=label
    def row(erp,cms,amount):
        values=[""]*35
        values[4:6]=[erp,cms];values[15]=amount;values[25]="Sales label not owner"
        return values
    dated=[header,row("209102155","209126001008","1110"),
           row("209102177","209126001012","2200"),
           row("209102199","","3500")]
    qq=[["invoice_number"]+[""]*9+["validation_status"],qq_row("209126001012",2200)]
    manifest=[["Source","Source Date","Synced At KST","Source ID","Rows","Schema","Meaning"],
              ["eTax Invoice","2026-10-26","2026-10-31T15:00:00+09:00","d9d7dG","3","HEADER_MATCHED",""]]
    return cw,dated,qq,manifest

class ETaxPersonalQQTests(unittest.TestCase):
    def test_match_and_no_cms_are_distinct_review_evidence(self):
        rows,stats=audit(*fixtures(),NOW)
        self.assertEqual(len(rows),2)
        self.assertEqual(stats["states"],{
            "NO_CMS_IDENTIFIER_FOR_PERSONAL_QQ":1,
            "QQ_ORIGINAL_ID_AMOUNT_MATCHED":1})
        self.assertEqual(stats["revenue_writes"],0)
        self.assertEqual(stats["payment_certifications"],0)
        self.assertEqual(stats["source_age_days"],5)
        self.assertTrue(all(x[9]=="NOT_VERIFIED" for x in rows))

    def test_no_personal_qq_is_not_automatically_missing_organization_invoice(self):
        d=list(fixtures())
        d[1][2][5]="209126001016"
        rows,stats=audit(*d,NOW)
        self.assertEqual(stats["states"]["NOT_IN_PERSONAL_QQ_ORIGINALS"],1)

    def test_qq_original_amount_conflict_is_explicit(self):
        d=list(fixtures())
        d[2][1]=qq_row("209126001012",2300)
        rows,_=audit(*d,NOW)
        self.assertEqual(rows[0][5],"QQ_ORIGINAL_GROSS_AMOUNT_CONFLICT")

    def test_reply_and_unverified_filename_never_count_as_original(self):
        d=list(fixtures())
        d[2][1][6]="Re: "+d[2][1][6]
        with self.assertRaisesRegex(ValueError,"QQ_ORIGINAL_EMPTY"):
            audit(*d,NOW)
        d=list(fixtures());d[2][1][5]="bad.pdf"
        with self.assertRaisesRegex(ValueError,"QQ_ORIGINAL_EVIDENCE_INTEGRITY"):
            audit(*d,NOW)

    def test_mirror_amount_mismatch_fails_before_publish(self):
        d=list(fixtures());d[1][2][15]="2201"
        with self.assertRaisesRegex(ValueError,"DATED_ONLY_MIRROR_AMOUNT_CONFLICT"):
            audit(*d,NOW)

    def test_manifest_count_and_source_date_drift_fail_closed(self):
        d=list(fixtures());d[3][1][4]="2"
        with self.assertRaisesRegex(ValueError,"ETAX_MIRROR_ROW_COUNT_MISMATCH"):
            audit(*d,NOW)
        d=list(fixtures());d[0][1][5]="2026-10-25"
        with self.assertRaisesRegex(ValueError,"CROSSWALK_MANIFEST_DATE_CONFLICT"):
            audit(*d,NOW)

    def test_duplicate_keys_fail_before_publish(self):
        d=list(fixtures());d[1].append(d[1][2][:])
        d[3][1][4]="4"
        with self.assertRaisesRegex(ValueError,"DUPLICATE_DATED_ETAX_IDENTIFIER"):
            audit(*d,NOW)

    def test_source_approval_is_not_authoritative(self):
        d=list(fixtures());d[0][2][7]="PAID"
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_PAYMENT_APPROVAL"):
            audit(*d,NOW)
if __name__=="__main__":unittest.main()
