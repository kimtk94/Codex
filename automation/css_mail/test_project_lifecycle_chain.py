"""Offline regression tests: stages, J billings, forecasts and source provenance."""
import unittest

from project_lifecycle_refresh import build
from statement_amount_extract import candidates

X = "X209SC260910566-Z01"
J1 = "J001-"+X
J2 = "J002-"+X
AMEA = "AMEA2026092127"
H = "H209SC260910566"

def inv(j, number, amount, subject_prefix="❗️Notice: Invoice Issued & Statement Confirmed"):
    return [number,str(amount),AMEA,H,"SQ",
            "TAX\r\n INVOICE-"+number+"-"+H+"-SQ-"+AMEA+"-KRW"+str(amount)+".00.pdf",
            subject_prefix+" – "+j+" -"+number+" - "+H+" - Korea-Gachon Univ.-12-mRNA-"+AMEA,
            "2026-10-28T10:30:00+08:00","40001","INBOX|1776302013|40001","FILENAME_PARSED","2026-10-28T11:00:00+00:00"]

def notice(j,date="2026-10-28T10:00:00+08:00",reply=""):
    # CSS Git Ingest F:Q: date, from, to, cc, subject, K..O, direction, in-reply-to.
    return [date,"css@novogene-amea.com","client@example.org","taehoon.kim@novogene.com",
            "❗️Action Required: Final Report & Statement Ready For Confirmation – "+j+" - "+H+" - "+AMEA,
            AMEA,H,"","","2026-10-28T12:00:00+00:00","INBOUND",reply]

def source_mail(j):
    # CSS Git Ingest A:R, retaining UID, UIDVALIDITY, and reply status.
    x=[""]*18
    x[0]="INBOX|1776302013|40005"
    x[2]="40005";x[3]="INBOX";x[4]="1776302013";x[5]="2026-10-28T10:00:00+08:00"
    x[6]="css@novogene-amea.com";x[9]=notice(j)[4];x[15]="INBOUND"
    return x

def fixtures(status="Waiting for Settlement"):
    css=[["exclude"],[]]
    fe=[["Snapshot KST"],
        ["2026-10-28 18:40:01",X,H,"Korea-Gachon Univ.-12-mRNA-"+AMEA,status,
         "F001","Library",10,"10","2026-11-03","2026-11","FORECAST",None,None,1650000]]
    ctrl=[["Sub-Project Number"],
          [X,H,"F001","2026-11",status,"2026-10","2026-11","FORECAST",1650000,"NO_INVOICE_MATCH","2026-10-28"]]
    invoice=[["invoice_number"]]
    mail=[["received_at"]]
    amounts=[["statement_key"]]
    return [css,fe,invoice,ctrl,mail,amounts]

class LifecycleTests(unittest.TestCase):
    def test_verified_statement_missing_from_feishu_is_source_only(self):
        data=fixtures()
        data[1]=[data[1][0]]  # Feishu has not yet synced this X.
        data[4]=[data[4][0]]  # The live mail header snapshot also lags.
        data[5].append([J1,X,"J001",1320000,"KRW",
                        "2026-10-28T10:00:00+08:00","40005","1776302013",
                        "AMOUNT_VERIFIED","2026-10-28",
                        notice(J1)[4]])
        out=build(*data)
        self.assertEqual(len(out),2)
        row=out[1]
        self.assertEqual(row[0],X)
        self.assertEqual(row[1],AMEA)
        self.assertEqual(row[5],"SOURCE_ONLY_FEISHU_UNMATCHED")
        self.assertEqual(row[20],"J001")
        self.assertEqual(row[22],1320000)
        self.assertEqual(row[23],"AMOUNT_VERIFIED 1/1")
        self.assertEqual(row[17],0)

    def test_verified_statement_recovers_missing_mail_header_for_linked_x(self):
        data=fixtures()
        data[5].append([J1,X,"J001",1320000,"KRW",
                        "2026-10-28T10:00:00+08:00","40005","1776302013",
                        "AMOUNT_VERIFIED","2026-10-28",notice(J1)[4]])
        out=build(*data)
        self.assertEqual(out[1][20],"J001")
        self.assertEqual(out[1][22],1320000)

    def test_source_only_conflict_is_rejected(self):
        data=fixtures()
        data[1]=[data[1][0]]
        record=[J1,X,"J001",1320000,"KRW",
                "2026-10-28T10:00:00+08:00","40005","1776302013",
                "AMOUNT_VERIFIED","2026-10-28",notice(J1)[4]]
        data[5].append(record)
        data[5].append([*record[:3],1400000,*record[4:]])
        with self.assertRaisesRegex(RuntimeError,"CONFLICTING_VERIFIED_STATEMENT"):
            build(*data)

    def test_partial_billing_j001_issued_j002_pending(self):
        data=fixtures()
        data[2].append(inv(J1,"209126000989",1320000))
        data[2].append(inv(J1,"209126000989",1320000))  # same original replay
        data[4].append(notice(J1))
        data[4].append(notice(J2))
        data[5].append([J2,X,"J002",220000,"KRW","2026-10-28T10:00:00+08:00",
                        "40005","1776302013","AMOUNT_VERIFIED","2026-10-28",notice(J2)[4]])
        out=build(*data)[1]
        self.assertEqual(out[14],1)
        self.assertEqual(out[15],1320000)
        self.assertEqual(out[16],"ISSUED + STATEMENT PENDING")
        self.assertEqual(out[20],"J002")
        self.assertEqual(out[22],220000)
        self.assertEqual(out[12],"2026-11")
        self.assertEqual(out[13],"2026-11")

    def test_replied_invoice_does_not_establish_actual(self):
        data=fixtures()
        data[2].append(inv(J1,"209126000989",1320000,subject_prefix="Re: ❗️Notice: Invoice Issued & Statement Confirmed"))
        data[4].append(notice(J1))
        out=build(*data)[1]
        self.assertEqual(out[15],0)
        self.assertEqual(out[16],"STATEMENT READY - INVOICE PENDING")

    def test_stale_statement_amount_is_not_counted(self):
        data=fixtures()
        data[4].append(notice(J2))
        data[5].append([J2,X,"J002",220000,"KRW","2026-10-20T10:00:00+08:00",
                        "30005","1776302013","AMOUNT_VERIFIED","2026-10-20",notice(J2)[4]])
        out=build(*data)[1]
        self.assertEqual(out[22],"")
        self.assertEqual(out[23],"AMOUNT_VERIFIED 0/1")

    def test_exclude_abnormal_from_forecast(self):
        data=fixtures(status="Abnormal")
        out=build(*data)[1]
        self.assertEqual(out[16],"BLOCKED / EXCLUDED FROM FORECAST")

    def test_contract_level_qc_updates_progress(self):
        data=fixtures(status="In Progress")
        data[4].append(["2026-10-29T08:00:00+09:00",
                        "css@novogene-amea.com","client@example.org","taehoon.kim@novogene.com",
                        "❗️Action Required: Review Sample QC Report – SAM20261008045 - "+H+
                        " - Korea-Gachon Univ.-"+AMEA,
                        AMEA,H,"","","2026-10-29T00:00:00+00:00","INBOUND",""])
        out=build(*data)[1]
        self.assertIn("QC",out[6])
        self.assertGreaterEqual(out[7],55)
        self.assertIn("contract-level",out[6])

    def test_original_notices_only_and_stale_invoice_filter(self):
        mail=[["ingest_key"],source_mail(J2)[:16]]  # Sheets trims empty Q:R for originals
        replied=source_mail(J1)
        replied[0]="INBOX|1776302013|40006";replied[2]="40006";replied[9]="Re: "+replied[9]
        mail.append(replied)
        invoice=[["invoice_number"],inv(J1,"209126000989",1320000)]
        c=candidates(mail,invoice)
        self.assertEqual(list(c),[J2])


class StatementLedgerTransitionTests(unittest.TestCase):
    """Source-key matching, original invoice recognition, and safe partials."""
    def setUp(self):
        import statement_amount_extract as statement
        self.module = statement
        self.x = "X209SC26065705-Z01"
        self.key = "J002-" + self.x
        self.amea = "AMEA2026042239"
        self.h = "H209SC26065705"
        self.subject = ("❗️Action Required: Final Report & Statement Ready For Confirmation – "
                        + self.key + " - " + self.h + " - Korea-Yonsei Univ.-"
                        "200-lysate-Deep DIA-Prof.KimMinWoo-" + self.amea)
        self.source = [[
            "statement_key", "project_x", "statement_no", "amount_krw",
            "currency", "notice_at", "imap_uid", "uidvalidity",
            "validation_status", "verified_at_utc", "subject"],
            [self.key, self.x, "J002", "22704000", "KRW",
             "2026-10-26T15:22:52+08:00", "40256", "1776302013",
             "AMOUNT_VERIFIED", "2026-10-28T16:22:31+00:00", self.subject]]
        self.heading = ["AMEA","H Contract","X Sub-project","SAM Batch",
                        "Statement Event KST","Statement Amount KRW",
                        "Statement State","Invoice Number","Invoice Amount KRW",
                        "Invoice Issued Date","Attribution State","Revenue Treatment",
                        "Evidence Source","Next Check","Statement ID"]
        self.current = [self.amea,self.h,self.x,"","2026-10-26", "22704000",
                        "STATEMENT_ORIGINAL_VERIFIED_PENDING","","","","",
                        "PENDING_VERIFIED_NOT_ACTUAL","","",self.key]

    def invoice(self, number, amount, reply=False):
        subject = ("❗️Notice: Invoice Issued & Statement Confirmed – " + self.key
                   + " -" + number + " - " + self.h + " - " + self.amea)
        if reply: subject = "Re: " + subject
        return [number,str(amount),self.amea,self.h,"SQ",
                "TAX INVOICE-" + number + "-" + self.h + "-SQ-"
                + self.amea + "-KRW" + str(amount) + ".00.pdf",
                subject,"2026-10-29T12:00:00+08:00","","","FILENAME_PARSED",""]

    def calls(self, invoices, existing=True):
        from unittest.mock import patch
        rows = [self.heading] + ([self.current] if existing else [])
        with patch.object(self.module, "get", return_value=rows), \
             patch.object(self.module, "put") as write:
            self.module.sync_verified_pending(None, self.source,
                                              [["invoice_number"]] + invoices)
        return [(a.args[3],a.args[4]) for a in write.call_args_list]

    def test_original_verified_source_creates_missing_j_row(self):
        updates = self.calls([], existing=False)
        added = next(values[0] for coord,values in updates if coord=="A2")
        self.assertEqual(added[0],self.amea)
        self.assertEqual(added[5],22704000)
        self.assertEqual(added[14],self.key)

    def test_exact_tax_invoice_removes_pending_from_ledger(self):
        updates = self.calls([self.invoice("209126001100",22704000)])
        row = next(values[0] for coord,values in updates if coord=="G2")
        self.assertEqual(row[0],"STATEMENT_INVOICED")
        self.assertEqual(row[2],22704000)
        self.assertEqual(row[5],"INVOICE_ONLY_NO_ADDITIONAL_REVENUE")
        self.assertFalse(any(coord=="F2" for coord,_ in updates))

    def test_two_tax_invoices_are_sum_matched_once(self):
        updates = self.calls([self.invoice("209126001100",12000000),
                              self.invoice("209126001101",10704000)])
        row = next(values[0] for coord,values in updates if coord=="G2")
        self.assertEqual(row[0],"STATEMENT_INVOICED")
        self.assertEqual(row[2],22704000)
        self.assertIn("209126001100",row[1])
        self.assertIn("209126001101",row[1])

    def test_partial_invoice_quarantines_unknown_balance(self):
        updates = self.calls([self.invoice("209126001100",10000000)])
        row = next(values[0] for coord,values in updates if coord=="G2")
        self.assertEqual(row[0],"STATEMENT_INVOICE_ALLOCATION_REVIEW")
        self.assertEqual(row[2],10000000)
        self.assertEqual(row[5],"INVOICE_ACTUAL_ONLY_REMAINING_BALANCE_UNVERIFIED")

    def test_replied_invoice_cannot_clear_pending(self):
        updates = self.calls([self.invoice("209126001100",22704000,reply=True)])
        self.assertFalse(any(coord=="G2" for coord,_ in updates))
        self.assertTrue(any(coord=="F2" for coord,_ in updates))

if __name__=="__main__":
    unittest.main()
