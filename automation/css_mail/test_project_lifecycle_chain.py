"""Offline regression tests: stages, J billings, forecasts and source provenance."""
import unittest

from project_lifecycle_refresh import build, lifecycle_content_equal, lifecycle_unformatted_readback
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

def prior_source_only(x=X, billing="STATEMENT READY - INVOICE PENDING [QQ_ONLY]"):
    previous=[""]*24
    previous[0]=x
    previous[5]="NOT_IN_FEISHU_SOURCE"
    previous[16]=billing
    previous[20]="J001" if "PENDING" in billing else ""
    previous[23]="AMOUNT_VERIFIED 1/1" if previous[20] else "NO_OPEN_STATEMENT"
    return [["Project / Sub-project"]]+[previous]


class LifecycleTests(unittest.TestCase):
    def test_lifecycle_complete_readback_allows_only_trimmed_blank_cells(self):
        from project_lifecycle_refresh import HEAD
        expected=[list(HEAD),["X0001"]+[""]*23]
        observed=[list(HEAD),["X0001"]]
        self.assertTrue(lifecycle_content_equal(expected,observed))
        observed=[list(HEAD),["X0001"]+[""]*22+[123]]
        self.assertFalse(lifecycle_content_equal(expected,observed))

    def test_lifecycle_same_row_count_changed_stage_or_amount_blocks(self):
        from project_lifecycle_refresh import HEAD
        expected=[list(HEAD),["X0001"]+[""]*14+[632500]+[""]*8]
        same=[list(HEAD),["X0001"]+[""]*14+[632500]+[""]*8]
        self.assertTrue(lifecycle_content_equal(expected,same))
        same[1][15]=632400
        self.assertFalse(lifecycle_content_equal(expected,same))
        same[1][15]=632500
        same[1][5]="NEW_STATUS"
        self.assertFalse(lifecycle_content_equal(expected,same))
        same[1][5]=""
        same[1][0]="X0002"
        self.assertFalse(lifecycle_content_equal(expected,same))
        self.assertFalse(lifecycle_content_equal(expected,same[:1]))

    def test_progress_only_numeric_sheet_roundtrip_does_not_false_fail(self):
        from project_lifecycle_refresh import HEAD
        expected=[list(HEAD),["X0001"]+[""]*23]
        expected[1][7]=97.0
        observed=[list(HEAD),list(expected[1])]
        observed[1][7]=97
        self.assertTrue(lifecycle_content_equal(expected,observed))
        observed[1][7]="97.000"
        self.assertTrue(lifecycle_content_equal(expected,observed))
        observed[1][7]="96.0"
        self.assertFalse(lifecycle_content_equal(expected,observed))
        observed[1][7]=""
        self.assertFalse(lifecycle_content_equal(expected,observed))
        observed[1][7]="NaN"
        self.assertFalse(lifecycle_content_equal(expected,observed))

    def test_other_23_fields_retain_exact_value_check(self):
        from project_lifecycle_refresh import HEAD
        expected=[list(HEAD),["X0001"]+[""]*23]
        expected[1][7]=97.0
        expected[1][15]=1000000
        expected[1][11]="2026-11-18"
        observed=[list(HEAD),list(expected[1])]
        observed[1][7]=97
        observed[1][15]=1000001
        self.assertFalse(lifecycle_content_equal(expected,observed))
        observed[1][15]=1000000
        observed[1][11]="2026-11-19"
        self.assertFalse(lifecycle_content_equal(expected,observed))
        observed[1][11]="2026-11-18"
        self.assertTrue(lifecycle_content_equal(expected,observed))

    def test_lifecycle_readback_uses_unformatted_values_and_does_not_log_customers(self):
        from unittest.mock import patch
        def fake_req(session,method,url):
            self.assertEqual("GET",method)
            self.assertIn("valueRenderOption=UNFORMATTED_VALUE",url)
            self.assertIn("A1%3AX2",url)
            return {"values":[["header"],["PRIVATE_CLIENT"]]}
        with patch("project_lifecycle_refresh.req",side_effect=fake_req):
            got=lifecycle_unformatted_readback(object(),"SYNTHETIC_BOOK",
                                               "BI Project Lifecycle Overview","A1:X2")
        self.assertEqual("PRIVATE_CLIENT",got[1][0])
        with patch("project_lifecycle_refresh.req",return_value={}):
            with self.assertRaisesRegex(RuntimeError,"LIFECYCLE_READBACK_UNAVAILABLE") as ctx:
                lifecycle_unformatted_readback(object(),"SYNTHETIC_BOOK",
                                              "BI Project Lifecycle Overview","A1:X2")
        self.assertNotIn("PRIVATE_CLIENT",str(ctx.exception))

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

    def test_verified_qq_statement_missing_from_feishu_is_tracked_separately(self):
        data=fixtures()
        data[1]=[data[1][0]]  # No Feishu subproject, no manual X association.
        data[4].append(notice(J1))
        data[5].append([J1,X,"J001",1881000,"KRW",
                        "2026-10-28T10:00:00+08:00","40005","1776302013",
                        "AMOUNT_VERIFIED","2026-10-28",notice(J1)[4]])
        rows=build(*data)
        self.assertEqual(len(rows),2)
        r=rows[1]
        self.assertEqual(r[0],X)
        self.assertEqual(r[5],"NOT_IN_FEISHU_SOURCE")
        self.assertEqual(r[15],0)
        self.assertEqual(r[16],"STATEMENT READY - INVOICE PENDING [QQ_ONLY]")
        self.assertEqual(r[20],"J001")
        self.assertEqual(r[22],1881000)
        self.assertEqual(r[23],"AMOUNT_VERIFIED 1/1")
        self.assertFalse(r[3])  # No fabricated customer
        from revenue_lifecycle_monthly import reconcile_pending
        monthly=[["Month","Actual Invoice KRW","Pending Verified KRW",
                  "Forecast KRW","Combined KRW","Invoice Count",
                  "Open Statement Count","Pending Amount Unknown"],
                 ["2026-10",0,1881000,0,1881000,0,1,0]]
        source_headers=["statement_key","project_x","statement_no","amount_krw",
                        "currency","notice_at","imap_uid","uidvalidity",
                        "validation_status","verified_at_utc","subject"]
        reconciled=reconcile_pending([source_headers]+data[5][1:],
                                     data[2],rows,monthly)
        self.assertEqual(reconciled,(1,1881000))


    def test_qq_only_pending_to_verified_issued_invoice_keeps_project(self):
        # Regression for actual Nov 16 blocker: 111 previous vs 110 Feishu.
        # The source-only J001 is now exactly issued; never delete its X row.
        data=fixtures()
        data[1]=[data[1][0]]  # Feishu did not provide this subproject
        data[4].append(notice(J1))
        data[5].append([J1,X,"J001",632500,"KRW",
                        "2026-10-28T10:00:00+08:00","40005","1776302013",
                        "AMOUNT_VERIFIED","2026-10-28",notice(J1)[4]])
        data[2].append(inv(J1,"209126000989",632500))
        rows=build(*data,previous_rows=prior_source_only())
        self.assertEqual(2,len(rows))
        row=rows[1]
        self.assertEqual(X,row[0])
        self.assertEqual("NOT_IN_FEISHU_SOURCE",row[5])
        self.assertEqual(1,row[14])
        self.assertEqual(632500,row[15])
        self.assertEqual("ISSUED (BALANCE UNVERIFIED) [QQ_ONLY]",row[16])
        self.assertEqual("",row[20])  # Original J001 is no longer Pending.
        self.assertIn(row[22],("",0))  # Do not double count issued as Pending.
        self.assertEqual("NO_OPEN_STATEMENT",row[23])
        self.assertFalse(row[3])  # Never invent a customer from email.
        from revenue_lifecycle_monthly import compute,reconcile_pending
        import datetime as dt
        revenue=compute(data[2],rows,dt.datetime(2026,10,30,tzinfo=dt.timezone.utc))
        month=next(r for r in revenue[1:] if r[0]=="2026-10")
        self.assertEqual(632500,month[1])
        self.assertEqual(0,month[2])
        self.assertEqual(1,month[5])
        headers=["statement_key","project_x","statement_no","amount_krw",
                 "currency","notice_at","imap_uid","uidvalidity",
                 "validation_status","verified_at_utc","subject"]
        self.assertEqual((0,0),reconcile_pending([headers]+data[5][1:],
                                                    data[2],rows,revenue))

    def test_qq_only_issued_invoice_without_open_notice_is_still_retained(self):
        data=fixtures()
        data[1]=[data[1][0]]
        data[2].append(inv(J1,"209126000990",632500))
        rows=build(*data,previous_rows=prior_source_only(
            billing="ISSUED (BALANCE UNVERIFIED) [QQ_ONLY]"))
        self.assertEqual(2,len(rows))
        row=rows[1]
        self.assertEqual("NOT_IN_FEISHU_SOURCE",row[5])
        self.assertEqual(1,row[14])
        self.assertEqual(632500,row[15])
        self.assertEqual("",row[20])
        self.assertEqual("NO_OPEN_STATEMENT",row[23])

    def test_qq_only_partially_invoiced_does_not_erase_other_pending_j(self):
        data=fixtures()
        data[1]=[data[1][0]]
        data[2].append(inv(J1,"209126000991",632500))
        data[4].extend([notice(J1),notice(J2)])
        data[5].append([J2,X,"J002",220000,"KRW",
                        "2026-10-28T10:00:00+08:00","40006","1776302013",
                        "AMOUNT_VERIFIED","2026-10-28",notice(J2)[4]])
        row=build(*data)[1]
        self.assertEqual("ISSUED + STATEMENT PENDING [QQ_ONLY]",row[16])
        self.assertEqual(632500,row[15])
        self.assertEqual("J002",row[20])
        self.assertEqual(220000,row[22])
        self.assertEqual("AMOUNT_VERIFIED 1/1",row[23])

    def test_new_invoiced_only_X_must_not_bulk_expand_lifecycle(self):
        data=fixtures()
        # 84 synthetic historical invoice-only X records are absent from
        # both Feishu and the previous source-only lifecycle. Reject all
        # rather than silently converting every Invoice into a project row.
        for n in range(84):
            x=f"X209SC2609{n:04d}-Z01"
            data[2].append(inv("J001-"+x,f"209126{n:06d}",500000+n))
        current=build(*data,previous_rows=[["Project / Sub-project"]])
        self.assertEqual(2,len(current))  # header + one Feishu project
        self.assertEqual(X,current[1][0])

    def test_real_scale_110_feishu_plus_85_invoice_x_keeps_111_project_rows(self):
        data=fixtures()
        feishu_header=data[1][0]
        row_template=data[1][1]
        data[1]=[feishu_header]
        for n in range(110):
            row=list(row_template)
            row[1]=f"X209SC2608{n:04d}-Z01"
            row[2]=f"H209SC2608{n:04d}"
            data[1].append(row)
        for n in range(85):
            x=f"X209SC2609{n:04d}-Z01"
            data[2].append(inv("J001-"+x,f"209126{n:06d}",100000+n))
        prior_x="X209SC26090000-Z01"
        rows=build(*data,previous_rows=prior_source_only(x=prior_x))
        self.assertEqual(111,len(rows)-1)
        qq_only=[r for r in rows[1:] if r[5]=="NOT_IN_FEISHU_SOURCE"]
        self.assertEqual(1,len(qq_only))
        self.assertEqual(prior_x,qq_only[0][0])
        self.assertEqual(1,qq_only[0][14])
        self.assertEqual(100000,qq_only[0][15])
        self.assertEqual("",qq_only[0][20])
        self.assertEqual("NO_OPEN_STATEMENT",qq_only[0][23])
        self.assertEqual(111,len({r[0] for r in rows[1:]}))
        self.assertEqual(110,len([r for r in rows[1:]
                                  if r[5]!="NOT_IN_FEISHU_SOURCE"]))

    def test_prior_qq_only_without_verified_invoice_remains_source_hold(self):
        data=fixtures()
        data[1]=[data[1][0]]
        data[2].append(inv(J1,"209126000991",632500))
        # A previous row with a different, non-Qq-only state is not authority
        # for manufacturing a source-only project.
        invalid=prior_source_only()
        invalid[1][5]="COMPLETED"
        with self.assertRaisesRegex(RuntimeError,"Empty lifecycle"):
            build(*data,previous_rows=invalid)
        # Without any earlier lifecycle lineage, no new invoice-only X.
        with self.assertRaisesRegex(RuntimeError,"Empty lifecycle"):
            build(*data)

    def test_still_retains_qq_only_issued_on_next_refresh(self):
        data=fixtures()
        data[1]=[data[1][0]]
        data[2].append(inv(J1,"209126000994",632500))
        previous=prior_source_only()
        first=build(*data,previous_rows=previous)
        second=build(*data,previous_rows=first)
        self.assertEqual(first[1][:18],second[1][:18])
        self.assertEqual("ISSUED (BALANCE UNVERIFIED) [QQ_ONLY]",second[1][16])
        self.assertEqual("",second[1][20])

    def test_unverified_orphan_does_not_generate_pending_amount(self):
        data=fixtures()
        orphan=notice("J001-X209SC26106973-Z01")
        data[4].append(orphan)
        rows=build(*data)
        self.assertEqual(len(rows),2)  # No verified amount; no phantom project.
        self.assertEqual(rows[1][0],X)

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
