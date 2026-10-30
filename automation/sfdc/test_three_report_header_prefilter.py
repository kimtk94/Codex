"""Synthetic IMAP server verifies headers-first SFDC ingestion semantics."""
import datetime as dt
import pathlib
import sys
import unittest
from email import policy
from email.message import EmailMessage

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from three_report_email_ingest import collect,trusted_uids_from_headers

def sample_report():
    html="<table><tr><th>SFDC Lead ID</th><th>Lead ID</th><th>Description</th></tr>"
    html+="".join("<tr><td>00Q%05d</td><td>Lead-%d</td><td>Test</td></tr>"%(i,i) for i in range(60))
    html+="</table>"
    msg=EmailMessage()
    msg["From"]="Taehoon <taehoon.kim@novogene.com>"
    msg["Subject"]="Report results (Automation | Leads)"
    msg["Date"]="Fri, 30 Oct 2026 09:00:00 +0900"
    msg.set_content("Report attached")
    msg.add_attachment(html.encode(),maintype="application",subtype="vnd.ms-excel",filename="Leads.xls")
    return msg.as_bytes(policy=policy.SMTP)

class StubIMAP:
    def __init__(self,missing=False):
        self.missing=missing
        self.full_calls=[]
        self.headers=[]
        self.records={
            b"1":("spoof@example.org","Report results (Automation | Leads)"),
            b"2":("test@example.org","Irrelevant user mail"),
            b"3":("taehoon.kim@novogene.com","Report results (Automation | Leads)"),
        }
    def uid(self,command,*args):
        if command=="SEARCH":
            return "OK",[b"1 2 3" if len(args)==3 else b"3"]
        if command!="FETCH":raise AssertionError("Unexpected IMAP command")
        uid_list=args[0]
        if isinstance(uid_list,str):uid_list=uid_list.encode()
        if b"HEADER.FIELDS" in str(args[-1]).encode():
            requested=uid_list.split(b",")
            self.headers.extend(requested)
            rows=[]
            for uid in requested:
                if self.missing and uid==b"2":continue
                sender,subject=self.records[uid]
                header=("From: "+sender+"\\r\\nSubject: "+subject+"\\r\\n\\r\\n").replace("\\r","\r").replace("\\n","\n").encode()
                rows.append((b"1 (UID "+uid+b" BODY[HEADER.FIELDS (FROM SUBJECT)] {"+str(len(header)).encode()+b"}",header))
            return "OK",rows+[b")"]
        self.full_calls.append(uid_list)
        if uid_list!=b"3":raise AssertionError("Fetched unrelated customer mail body")
        return "OK",[(b"1 (UID 3 BODY[])",sample_report())]

class HeaderFirstTests(unittest.TestCase):
    def test_nonreport_full_bodies_are_never_loaded(self):
        im=StubIMAP();trace={}
        selected=collect(im,days=4,diagnostics_out=trace)
        self.assertEqual(im.full_calls,[b"3"])
        self.assertEqual(im.headers,[b"1",b"2",b"3"])
        self.assertEqual(set(selected),{"Leads"})
        self.assertEqual(selected["Leads"]["stats"]["rows"],60)
        self.assertEqual(trace["headers_scanned"],3)
        self.assertEqual(trace["full_body_fetched"],1)
        self.assertEqual(trace["fetched"],3)
        self.assertEqual(trace["recognized"],1)
    def test_spoofed_sender_matching_subject_rejected_before_full_mime(self):
        im=StubIMAP()
        trusted,scanned=trusted_uids_from_headers(im,{b"1",b"2",b"3"},batch_size=2)
        self.assertEqual(trusted,{b"3"})
        self.assertEqual(scanned,3)
        self.assertEqual(im.full_calls,[])
    def test_partial_header_batch_fails_before_staging(self):
        im=StubIMAP(missing=True)
        with self.assertRaisesRegex(RuntimeError,"IMAP_HEADER_BATCH_INCOMPLETE"):
            collect(im)
        self.assertEqual(im.full_calls,[])
    def test_invalid_batch_size_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"IMAP_HEADER_BATCH_SIZE_INVALID"):
            trusted_uids_from_headers(StubIMAP(),{b"1"},batch_size=0)
    def test_new_header_stage_is_read_only_and_preserves_sender_contract(self):
        import inspect
        from three_report_email_ingest import trusted_uids_from_headers
        source=inspect.getsource(trusted_uids_from_headers)
        self.assertIn("BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)]",source)
        self.assertNotIn("STORE",source)
        self.assertNotIn("BODY.PEEK[]",source)
        self.assertNotIn("sendmail(",source)

if __name__=="__main__":
    unittest.main()
