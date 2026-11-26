import datetime as dt
from email.message import EmailMessage
import json
import unittest
import urllib.parse
from unittest.mock import patch
from incremental_sync import COLS
from statement_source_coverage import read_full_source, select_candidates, same_notice
from statement_original_recovery_probe import statement_total, original_matches, inspect, bounded_size
from test_project_lifecycle_chain import source_mail,inv,J1,J2

class SourceTests(unittest.TestCase):
    def reader(self,broken=None):
        def request(session,method,url):
            self.assertEqual(method,"GET")
            if "?fields=" in url:
                return {"spreadsheetId":"BOOK","sheets":[{"properties":{"title":"CSS Git Ingest","sheetId":123,
                         "gridProperties":{"rowCount":12005,"columnCount":26}}}]}
            span=urllib.parse.unquote(url.split("/values/")[1].split("?")[0])
            import re
            a,b=map(int,re.search(r"A(\d+):R(\d+)",span).groups())
            rows=[]
            if a==b==1:rows=[COLS]
            elif a<=11001<=b:
                rows=[[] for _ in range(11001-a)]+[source_mail(J2)]
                if broken=="key":rows[-1][0]="wrong"
            return {"range":span,"majorDimension":"ROWS","values":rows}
        return request

    def test_full_grid_includes_row_after_10000(self):
        rows=read_full_source(object(),"BOOK","CSS Git Ingest",COLS,request=self.reader())
        self.assertEqual(len(rows),2)
        p,i,s=select_candidates(rows,[["invoice_number"]])
        self.assertEqual(set(p),{J2})
        self.assertEqual(i,{})
        self.assertEqual(s["mail_rows"],1)

    def test_bad_ingest_tuple_stops_before_writes(self):
        with self.assertRaisesRegex(RuntimeError,"MAIL_TUPLE"):
            read_full_source(object(),"BOOK","CSS Git Ingest",COLS,request=self.reader("key"))

    def test_issue_notice_without_amount_is_separate_not_pending(self):
        notice=source_mail(J2)
        issued=source_mail(J2);issued[0]="INBOX|1776302013|40006";issued[2]="40006"
        issued[9]="Notice: Invoice Issued & Statement Confirmed "+J2
        p,i,s=select_candidates([COLS,notice,issued],[["invoice_number"]])
        self.assertFalse(p);self.assertEqual(set(i),{J2})
        p,i,s=select_candidates([COLS,notice,issued],[["invoice_number"],inv(J2,"209126000989",1320000)])
        self.assertFalse(p);self.assertFalse(i);self.assertEqual(s["verified_issued_keys"],1)

    def test_untrusted_invoice_reply_does_not_clear_pending(self):
        notice=source_mail(J2)
        r=inv(J2,"209126000989",1320000,subject_prefix="Re: Notice: Invoice Issued & Statement Confirmed")
        p,i,s=select_candidates([COLS,notice],[["invoice_number"],r])
        self.assertEqual(set(p),{J2})

    def test_uidvalidity_date_all_required(self):
        item=select_candidates([COLS,source_mail(J2)],[["invoice_number"]])[0][J2]
        old=[J2,"","",100,"KRW",item["date"],item["uid"],item["uidvalidity"],"AMOUNT_VERIFIED"]
        self.assertTrue(same_notice(old,item))
        old[7]="changed"
        self.assertFalse(same_notice(old,item))

class OriginalProbeTests(unittest.TestCase):
    def message(self,body):
        msg=EmailMessage()
        msg["From"]="css@novogene-amea.com"
        msg["Subject"]=source_mail(J2)[9]
        msg["Date"]="Wed, 28 Oct 2026 10:00:00 +0800"
        msg.set_content(body)
        return msg

    def test_explicit_currency_and_ambiguity(self):
        for body in ("Total Amount: KRW 4,840,000","Total Amount: 4,840,000 KRW"):
            self.assertEqual(statement_total(self.message(body)),4840000)
        for body in ("Total Amount: 4840000","Total Amount: USD 4,840",
                     "Total Amount: KRW 100 Total Amount: KRW 200"):
            self.assertIsNone(statement_total(self.message(body)))

    def test_header_date_sender_subject_identity(self):
        item=select_candidates([COLS,source_mail(J2)],[["invoice_number"]])[0][J2]
        msg=self.message("Total Amount: KRW 100")
        self.assertTrue(original_matches(msg,item,"STATEMENT"))
        msg["In-Reply-To"]="<reply@example.invalid>"
        self.assertFalse(original_matches(msg,item,"STATEMENT"))

    def test_readonly_uid_probe_and_size_limit(self):
        p,_,_=select_candidates([COLS,source_mail(J2)],[["invoice_number"]])
        item=p[J2];msg=self.message("Total Amount: KRW 12345");raw=msg.as_bytes()
        class Fake:
            def select(self,folder,readonly=False):
                self.readonly=readonly;return "OK",[]
            def response(self,name):return name,[item["uidvalidity"].encode()]
            def uid(self,verb,uid,query):
                assert verb=="FETCH"
                pref=("1 (UID "+uid+" ").encode()
                if "RFC822.SIZE" in query:return "OK",[pref+("RFC822.SIZE "+str(len(raw))+")").encode()]
                if "HEADER" in query:return "OK",[(pref,raw.split(b"\n\n",1)[0]+b"\n\n")]
                return "OK",[(pref,raw)]
        fake=Fake()
        out=inspect(fake,p,{})
        self.assertTrue(fake.readonly)
        self.assertEqual(out["results"],{"STATEMENT_ORIGINAL_TOTAL_FOUND":1})
        self.assertEqual(out["statement_candidate_by_due_month"]["2026-11"]["statement_krw_vat_basis_unknown"],12345)
        self.assertNotIn(J2,json.dumps(out))

if __name__=="__main__":
    unittest.main()
