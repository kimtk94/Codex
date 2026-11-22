"""Integration-style writer tests using fake QQ IMAP and in-memory Google Sheets.

Never contacts a real mailbox, downloads files or writes live worksheets.
"""
import contextlib
import io
import os
from pathlib import Path
import sys
import unittest
from unittest import mock
from urllib.parse import unquote

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE.parent.parent))
from automation.css_mail import qq_historical_invoice_backfill as writer

ISSUER="css@novogene-amea.com"
SUBJECT="Notice: Invoice Issued & Statement Confirmed"


def attachment(inv,amt=1000):
    return "TAX INVOICE-%s-H209SC26065705-SQ-AMEA2026042239-KRW%d.00.pdf" % (inv,amt)


class FakeMail:
    def __init__(self,invoice_by_uid,body_fail=None,header_fail=None,epoch="123"):
        self.invoices=invoice_by_uid
        self.body_fail=set(body_fail or ())
        self.header_fail=set(header_fail or ())
        self.epoch=epoch
        self.calls=[]
        self.selected_readonly=False

    def __enter__(self):return self
    def __exit__(self,*args):return False
    def login(self,*args):return "OK",[]
    def list(self):return "OK",[b'(\\HasNoChildren) "/" "INBOX"']
    def select(self,folder,readonly=False):
        self.selected_readonly=readonly
        return "OK",[]
    def response(self,key):
        assert key=="UIDVALIDITY"
        return "OK",[self.epoch.encode()]
    def status(self,*args):
        return "OK",[b'INBOX (UIDVALIDITY %s)'%self.epoch.encode()]
    def uid(self,cmd,uid,query,*args):
        assert self.selected_readonly
        if cmd=="SEARCH":
            assert uid is None
            return "OK",[b" ".join(str(i).encode() for i in sorted(self.invoices))]
        assert cmd=="FETCH"
        self.calls.append((int(uid),query))
        idx=int(uid)
        if "HEADER.FIELDS" in query:
            if idx in self.header_fail:
                return "NO",[]
            hdr=("From: CSS <%s>\r\nSubject: %s\r\n\r\n"%(
                ISSUER,SUBJECT)).encode()
            return "OK",[(b"head",hdr)]
        if query=="(BODYSTRUCTURE)":
            if idx in self.body_fail:
                return "NO",[]
            names=self.invoices[idx]
            content=b" ".join(('"%s"'%n).encode() for n in names)
            return "OK",[(b"frame",content)]
        if query=="(INTERNALDATE)":
            return "OK",[b'1 (INTERNALDATE "2-Nov-2026 08:00:00 +0900")']
        raise AssertionError("Unknown FETCH action")
    def logout(self):return "BYE",[]


class FakeSheet:
    def __init__(self,initial=None,initial_cursor=100,raise_on_cursor_once=False):
        self.qq=[writer.HEAD]+list(initial or [])
        self.cursor=[["year","folder","uidvalidity","last_uid","updated_utc"],
                     ["2026","INBOX","123",str(initial_cursor),"2026-11-20T00:00:00Z"]]
        self.audit=[["year","last_run_utc","status","candidates","scanned",
                     "filename_candidates","parsed_invoices","new_invoices"]]
        self.puts=[]
        self.raise_on_cursor_once=raise_on_cursor_once

    def call(self,session,method,path,**kw):
        key=unquote(path)
        if method=="GET" and key=="?fields=sheets.properties.title":
            return {"sheets":[{"properties":{"title":n}} for n in
                (writer.TAB,writer.CURSOR_TAB,writer.AUDIT_TAB,
                 "CSS Tax Invoice List")]}
        if method=="GET" and key.startswith("/values/"):
            if writer.TAB in key:
                return {"values":self.qq}
            if writer.CURSOR_TAB in key:
                return {"values":self.cursor}
            if writer.AUDIT_TAB in key:
                return {"values":self.audit}
            if "CSS Tax Invoice List" in key:
                return {"values":[["invoice_number","invoice_month","amount_krw",
                                   "uid","project_id","h_project_number",
                                   "po_reference"]]}
            raise AssertionError("Unexpected read: %s"%key)
        if method=="PUT" and key.startswith("/values/"):
            values=kw["json"]["values"]
            if writer.CURSOR_TAB in key and self.raise_on_cursor_once:
                self.raise_on_cursor_once=False
                raise RuntimeError("SYNTHETIC_CURSOR_SAVE_FAILURE")
            if writer.TAB in key:
                self.qq=[list(x) for x in values]
                label="EVIDENCE"
            elif writer.CURSOR_TAB in key:
                self.cursor=[list(x) for x in values]
                label="CURSOR"
            elif writer.AUDIT_TAB in key:
                self.audit=[list(x) for x in values]
                label="AUDIT"
            else:
                raise AssertionError("Unexpected writer tab")
            self.puts.append(label)
            return {}
        raise AssertionError("Unexpected API %s %s"%(method,key))


def run_writer(mail, sheets, mode="APPLY", approved=True):
    with mock.patch.dict(os.environ,{
        "BACKFILL_WRITE_MODE":mode,
        "BACKFILL_STAGE_WRITES_APPROVED":"YES" if approved else "NO",
        "CKD_DRIVE_SA_JSON":"{}",
        "CSS_QQ_MAIL_ADDRESS":"test@example.invalid",
        "CSS_QQ_MAIL_AUTH_CODE":"offline-placeholder",
        "BACKFILL_YEAR":"2026",
        "BACKFILL_TAB":"QQ 2026 Invoice Backfill",
        "BACKFILL_MAX_MATCHES":"100"
    }),mock.patch.object(
        writer.service_account.Credentials,"from_service_account_info",
        return_value=object()
    ),mock.patch.object(
        writer,"AuthorizedSession",return_value=object()
    ),mock.patch.object(
        writer,"call",new=sheets.call
    ),mock.patch.object(
        writer.imaplib,"IMAP4_SSL",return_value=mail
    ),contextlib.redirect_stdout(io.StringIO()):
        return writer.main()


class WriterIntegrationTests(unittest.TestCase):
    def test_first_failed_uid_remains_retryable_after_evidence_put(self):
        mail=FakeMail({101:[attachment("209126000701")],
                       102:[attachment("209126000702")],
                       103:[attachment("209126000703")]},body_fail={102})
        sheets=FakeSheet()
        with self.assertRaises(SystemExit) as exc:
            run_writer(mail,sheets)
        self.assertEqual(exc.exception.code,2)
        self.assertEqual(sheets.puts,["EVIDENCE","CURSOR","AUDIT"])
        self.assertEqual(sheets.cursor[1][3],"101")
        self.assertEqual(len(sheets.qq),2)  # header plus verified UID 101
        self.assertFalse(any(uid==103 for uid,_ in mail.calls))
        self.assertEqual(sheets.audit[1][2],"PARTIAL_SCAN")

    def test_two_invoices_from_one_mail_are_staged_and_checkpointed(self):
        mail=FakeMail({101:[attachment("209126000701"),
                            attachment("209126000702",2000)]})
        sheets=FakeSheet()
        run_writer(mail,sheets)
        self.assertEqual(len(sheets.qq),3)
        self.assertEqual(sheets.cursor[1][3],"101")
        self.assertEqual(sheets.audit[1][2],"SCAN_COMPLETE")
        self.assertTrue(all(row[1]=="" for row in sheets.qq[1:]))
        self.assertEqual(sheets.puts,["EVIDENCE","CURSOR","AUDIT"])

    def test_replay_after_failed_cursor_write_is_idempotent(self):
        first=FakeMail({101:[attachment("209126000701")]})
        sheets=FakeSheet(raise_on_cursor_once=True)
        with self.assertRaisesRegex(RuntimeError,"SYNTHETIC_CURSOR_SAVE_FAILURE"):
            run_writer(first,sheets)
        self.assertEqual(len(sheets.qq),2)
        self.assertEqual(sheets.cursor[1][3],"100")
        second=FakeMail({101:[attachment("209126000701")]})
        run_writer(second,sheets)
        self.assertEqual(sheets.cursor[1][3],"101")
        self.assertEqual(len(sheets.qq),2)
        self.assertFalse(any(q=="(BODYSTRUCTURE)" for _,q in second.calls))

    def test_amount_conflict_will_not_advance_checkpoint(self):
        existing=["209126000701","","1200","AMEA2026042239","H209SC26065705",
                  "SQ","INBOX","99","existing.pdf","FILENAME_PARSED","now"]
        mail=FakeMail({101:[attachment("209126000701",1000)]})
        sheets=FakeSheet(initial=[existing])
        with self.assertRaises(SystemExit) as exc:
            run_writer(mail,sheets)
        self.assertEqual(exc.exception.code,2)
        self.assertEqual(sheets.cursor[1][3],"100")
        self.assertEqual(sheets.qq[1][2],"1200")
        self.assertEqual(len(sheets.qq),2)

    def test_preview_of_valid_source_never_writes_sheets_or_cursor(self):
        mail=FakeMail({101:[attachment("209126000701")]})
        sheets=FakeSheet()
        run_writer(mail,sheets,mode="PREVIEW",approved=False)
        self.assertEqual(sheets.puts,[])
        self.assertEqual(sheets.cursor[1][3],"100")
        self.assertEqual(len(sheets.qq),1)
        self.assertTrue(any(x=="(BODYSTRUCTURE)" for _,x in mail.calls))

    def test_preview_of_unresolved_mail_stays_readonly_and_fails(self):
        mail=FakeMail({101:[attachment("209126000701")]},body_fail={101})
        sheets=FakeSheet()
        # Existing fail-closed NO_INVOICE_EVIDENCE check correctly rejects a
        # source run without any trusted invoice. PREVIEW still cannot write.
        with self.assertRaisesRegex(RuntimeError,"QQ_BACKFILL_NO_INVOICE_EVIDENCE"):
            run_writer(mail,sheets,mode="PREVIEW",approved=False)
        self.assertEqual(sheets.puts,[])
        self.assertEqual(sheets.cursor[1][3],"100")

    def test_apply_requires_explicit_second_gate(self):
        mail=FakeMail({101:[attachment("209126000701")]})
        sheets=FakeSheet()
        with self.assertRaisesRegex(RuntimeError,"BACKFILL_WRITER_APPROVAL_GATE"):
            run_writer(mail,sheets,mode="APPLY",approved=False)
        self.assertEqual(sheets.puts,[])
        self.assertEqual(mail.calls,[])

    def test_unverified_mail_must_not_mutate_issued_month(self):
        mail=FakeMail({101:[attachment("209126000701")]})
        sheets=FakeSheet()
        run_writer(mail,sheets)
        self.assertEqual(sheets.qq[1][1],"")
        self.assertEqual(sheets.qq[1][9],"FILENAME_PARSED")


if __name__=="__main__":
    unittest.main()
