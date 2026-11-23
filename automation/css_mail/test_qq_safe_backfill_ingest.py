"""Offline tests for proof-first cursor-aware source candidate processing."""
import datetime as dt
import re
import unittest
from unittest import mock
from automation.css_mail.qq_safe_backfill_ingest import (
    evaluate_candidate, date_metadata_class, candidate_filenames,
    safe_folder_checkpoint
)
from automation.css_mail.qq_cursor_checkpoint_policy import (
    assess_writer_cursor_order
)

NOTICE = "Notice: Invoice Issued & Statement Confirmed"
OFFICIAL = "css@novogene-amea.com"


def valid_attachment(inv="209126000007", gross=1100):
    return "TAX INVOICE-%s-H209SC26000001-SQ-AMEA2026010101-KRW%d.00.pdf" % (inv,gross)


def extract(name):
    match=re.search(
        r"TAX INVOICE-(\d+)-(H\d+SC\d+)-(SQ)-(AMEA\d+)-KRW(\d+)\.00\.pdf",name
    )
    if match:
        inv,h,po,amea,amount=match.groups()
        return inv,h,po,amea,int(amount),"FILENAME_PARSED"
    return None


def names(blob):
    return re.findall(r"TAX INVOICE-\d+-H\d+SC\d+-SQ-AMEA\d+-KRW\d+\.00\.pdf",
                      blob.decode("utf-8","replace"))


def chunks(parts):
    ret=[]
    for x in parts or []:
        if isinstance(x,bytes):ret.append(x)
        elif isinstance(x,tuple):
            ret.extend(v for v in x if isinstance(v,bytes))
    return ret


class FakeIMAP:
    def __init__(self, attachments=None, sender=OFFICIAL, subject=NOTICE,
                 reply=False, header_status="OK", mime_status="OK",
                 internaldate=b'1 (INTERNALDATE "2-Nov-2026 10:00:00 +0900")',
                 split=False):
        self.attachments=attachments if attachments is not None else [valid_attachment()]
        self.sender=sender
        self.subject=subject
        self.reply=reply
        self.header_status=header_status
        self.mime_status=mime_status
        self.internaldate=internaldate
        self.split=split
        self.calls=[]

    def uid(self, cmd, uid, action):
        assert cmd=="FETCH"
        self.calls.append((uid,action))
        if "HEADER" in action:
            hdr = ("From: CSS <%s>\r\nSubject: %s\r\n" % (self.sender,self.subject))
            if self.reply:hdr += "In-Reply-To: <prior@sample.invalid>\r\n"
            hdr += "\r\n"
            return self.header_status, [(b"header",hdr.encode())]
        if action=="(BODYSTRUCTURE)":
            if self.split and self.attachments:
                name=self.attachments[0]
                i=len(name)//2
                return self.mime_status, [
                    (b"IMAP FRAMING",name[:i].encode()),
                    (b"IMAP FRAMING",name[i:].encode()),
                ]
            return self.mime_status, [
                (b"frame",b" ".join(a.encode() for a in self.attachments))
            ] if self.attachments else []
        if action=="(INTERNALDATE)":
            return "OK",[self.internaldate]
        raise AssertionError("Unexpected FETCH")

def candidate(im, known=False, original=None):
    return evaluate_candidate(
        im,"410","INBOX",known,chunks,names,extract,
        lambda filename,subject:None,original or {})


class SafeIngestTests(unittest.TestCase):
    def test_known_uid_never_refetches(self):
        im=FakeIMAP()
        state,rows,diag=candidate(im,known=True)
        self.assertEqual(state,"KNOWN_UID_WITH_VALID_EVIDENCE")
        self.assertEqual(rows,[])
        self.assertEqual(im.calls,[])

    def test_official_original_only_and_no_issue_date_guess(self):
        im=FakeIMAP()
        state,rows,diag=candidate(im)
        self.assertEqual(state,"ORIGINAL_ISSUED_PROOF_PERSISTED")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][0],"209126000007")
        self.assertEqual(rows[0][1],"")  # NOT IMAP arrival month
        self.assertEqual(rows[0][2],"1100")
        self.assertEqual(diag["arrival_metadata_state"],"VALID_ARRIVAL_DATE")

    def test_single_digit_and_space_padded_arrival_never_fills_invoice_month(self):
        for stamp in (b'1 (INTERNALDATE "2-Nov-2026 10:00:00 +0900")',
                      b'1 (INTERNALDATE " 2-Nov-2026 10:00:00 +0900")',
                      b'1 (INTERNALDATE "02-Nov-2026 10:00:00 +0900")'):
            with self.subTest(shape=stamp[:30]):
                state,rows,diag=candidate(FakeIMAP(internaldate=stamp))
                self.assertEqual(state,"ORIGINAL_ISSUED_PROOF_PERSISTED")
                self.assertEqual(diag["arrival_metadata_state"],"VALID_ARRIVAL_DATE")
                self.assertEqual(rows[0][1],"")

    def test_malformed_or_unquoted_arrival_never_fills_invoice_month(self):
        for stamp in (b'1 (INTERNALDATE "40-Nov-2026 10:00:00 +0900")',
                      b'1 (INTERNALDATE "2-Nov-2026 10:00:00 +09:00")',
                      b'1 (INTERNALDATE 2-Nov-2026 10:00:00 +0900)',
                      b'1 (INTERNALDATE NIL)'):
            with self.subTest(shape=stamp[:30]):
                state,rows,diag=candidate(FakeIMAP(internaldate=stamp))
                self.assertEqual(state,"ORIGINAL_ISSUED_PROOF_PERSISTED")
                self.assertNotEqual(diag["arrival_metadata_state"],"VALID_ARRIVAL_DATE")
                self.assertEqual(rows[0][1],"")

    def test_official_sender_but_reply_is_not_issued(self):
        im=FakeIMAP(reply=True)
        state,rows,_=candidate(im)
        self.assertEqual(state,"ORIGINAL_NONOFFICIAL_HEADER_VERIFIED")
        self.assertEqual(rows,[])
        self.assertFalse(any(x[1]=="(BODYSTRUCTURE)" for x in im.calls))

    def test_nonofficial_sender_rejected_without_parsing(self):
        im=FakeIMAP(sender="other@sample.invalid")
        state,rows,_=candidate(im)
        self.assertEqual(state,"ORIGINAL_NONOFFICIAL_HEADER_VERIFIED")
        self.assertEqual(rows,[])
        self.assertEqual(len(im.calls),1)

    def test_fetch_failure_blocks(self):
        im=FakeIMAP(header_status="NO")
        state,rows,_=candidate(im)
        self.assertEqual(state,"FETCH_FAILED")
        self.assertEqual(rows,[])

    def test_bodystructure_fetch_failure_blocks(self):
        im=FakeIMAP(mime_status="NO")
        state,rows,_=candidate(im)
        self.assertEqual(state,"FETCH_FAILED")
        self.assertEqual(rows,[])

    def test_undecodable_official_attachment_blocks(self):
        im=FakeIMAP(attachments=["TAX INVOICE-UNKNOWN.pdf"])
        state,rows,_=candidate(im)
        self.assertEqual(state,"MIME_PARSER_UNRESOLVED")
        self.assertEqual(rows,[])

    def test_missing_attachment_blocks(self):
        im=FakeIMAP(attachments=[])
        state,rows,_=candidate(im)
        self.assertEqual(state,"FETCH_FAILED")
        self.assertEqual(rows,[])

    def test_duplicate_invoice_same_amount_does_not_create_second_row(self):
        knownrow=["209126000007","","1100","AMEA2026010101",
                  "H209SC26000001","SQ","INBOX","100","test","FILENAME_PARSED","now"]
        im=FakeIMAP()
        state,rows,_=candidate(im,original={"209126000007":knownrow})
        self.assertEqual(state,"ORIGINAL_ISSUED_PROOF_PERSISTED")
        self.assertEqual(len(rows),1)
        self.assertEqual(knownrow[1],"")  # source rows not mutated

    def test_conflicting_amount_blocks_entire_message(self):
        previous=["209126000007","","1200","AMEA2026010101",
                  "H209SC26000001","SQ","INBOX","100","test","FILENAME_PARSED","now"]
        im=FakeIMAP(attachments=[
            valid_attachment("209126000009"),
            valid_attachment("209126000007",1100)
        ])
        state,rows,_=candidate(im,original={"209126000007":previous})
        self.assertEqual(state,"AMOUNT_CONFLICT")
        self.assertEqual(rows,[])

    def test_two_invoices_in_one_message_staged_together(self):
        im=FakeIMAP(attachments=[
            valid_attachment("209126000007"),
            valid_attachment("209126000008",2200)])
        state,rows,_=candidate(im)
        self.assertEqual(state,"ORIGINAL_ISSUED_PROOF_PERSISTED")
        self.assertEqual(len(rows),2)
        self.assertEqual({x[0] for x in rows},
                         {"209126000007","209126000008"})

    def test_mime_literal_fragments_are_reassembled(self):
        im=FakeIMAP(split=True)
        state,rows,_=candidate(im)
        self.assertEqual(state,"ORIGINAL_ISSUED_PROOF_PERSISTED")
        self.assertEqual(len(rows),1)

    def test_first_failed_uid_holds_later_success(self):
        r=safe_folder_checkpoint(100,[101,102,103],{
            101:"KNOWN_UID_WITH_VALID_EVIDENCE",
            102:"MIME_PARSER_UNRESOLVED",
            103:"ORIGINAL_ISSUED_PROOF_PERSISTED"
        })
        self.assertEqual(r["checkpoint_safe"],101)
        self.assertTrue(r["blocked"])

    def test_invalid_arrival_is_not_official_issue_date(self):
        self.assertEqual(date_metadata_class([
            b'1 (INTERNALDATE "2-Nov-2026 10:00:00 +0900")'
        ]),"VALID_ARRIVAL_DATE")
        self.assertEqual(date_metadata_class([
            b'1 (INTERNALDATE NIL)'
        ]),"UNSUPPORTED_FORMAT")

    def test_safe_cursor_policy_static_proof_accepts_post_fetch_only(self):
        source = (
            "last_by_folder = {}\n"
            "for uid in eligible:\n"
            "    resp = im.uid('FETCH', uid, '(BODYSTRUCTURE)')\n"
            "    state, rows = result\n"
            "last_by_folder[folder] = verified_uid\n"
        )
        result=assess_writer_cursor_order(source)
        self.assertFalse(result["early_cursor_advance_detected"])


if __name__=="__main__":
    unittest.main()
