"""Synthetic-only tests of targeted read-only IMAP proof (no credentials or writes)."""
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from automation.css_mail import qq_targeted_backfill_proof as proof

SCAN = "2026-11-22T08:35:12+00:00"


def qq(num, month="2026-11", uid="410"):
    return {"invoice_number":num,"issued_month":month,"imap_uid":uid}


def css(num):
    return {"invoice_number":num}


def ext(num, uid="410", when="2026-10-29T15:30:00+00:00"):
    return {"invoice_number":num,"amount_krw":"1100","project_id":"AMEA-TEST",
            "h_project_number":"H-TEST","po_reference":"PO-TEST",
            "imap_uid":uid,"validation_status":"FILENAME_PARSED",
            "ingest_key":"KEY-"+num,"extracted_at_utc":when}


def cursor(uid="500", uv="1234"):
    return [{"year":"2026","folder":"INBOX","uidvalidity":uv,"last_uid":uid}]


def audit():
    return [{"year":"2026","status":"SCAN_COMPLETE","last_run_utc":SCAN}]


def ingest(e,uv="1234"):
    return {"ingest_key":e["ingest_key"],"imap_uid":e["imap_uid"],
            "folder":"INBOX","uidvalidity":uv}


class FakeIMAP:
    entries = {}
    search_uids = None
    closed = False

    def __init__(self, host, port, timeout):
        self.selected_readonly = False
        self.calls = []
        self.epoch = "1234"

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def login(self,*args): return "OK",[]
    def select(self,folder,readonly=False):
        self.selected_readonly = readonly
        assert folder == "INBOX" and readonly
        return "OK",[]
    def response(self,name):
        assert name == "UIDVALIDITY"
        return "OK",[self.epoch.encode()]
    def status(self,*args):
        return "OK",[b'INBOX (UIDVALIDITY 1234)']
    def uid(self,action,uid,query,*rest):
        assert self.selected_readonly
        if action == "SEARCH":
            assert uid is None and query == "SINCE"
            assert rest == ("01-Jan-2026", "BEFORE", "01-Jan-2027",
                            "SUBJECT", '"Invoice Issued"') or rest == (
                            "01-Jan-2026", "BEFORE", "01-Jan-2027",
                            "SUBJECT", '"TAX INVOICE"')
            selected = (self.search_uids if self.search_uids is not None
                        else self.entries.keys())
            return "OK", [" ".join(selected).encode("ascii")]
        assert action == "FETCH"
        assert query in ("(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT IN-REPLY-TO)])",
                         "(BODYSTRUCTURE)","(INTERNALDATE)")
        self.calls.append((uid,query))
        entry=self.entries[uid]
        if "HEADER" in query:
            who=entry.get("sender","css@novogene-amea.com")
            header=("From: CSS <"+who+">\r\n"+
                    "Subject: Notice: Invoice Issued & Statement Confirmed\r\n\r\n")
            return "OK",[(b"H",header.encode())]
        if query=="(INTERNALDATE)":
            return "OK",[b'1 (INTERNALDATE "22-Nov-2026 10:00:00 +0900")']
        n=entry["number"]
        if entry.get("split"):
            return "OK",[(b"x",('"TAX INVOICE-'+n[:6]).encode()),
                         (b"y",(n[6:]+'.PDF"').encode())]
        return "OK",[(b"x",('"TAX INVOICE-'+n+'.PDF"').encode())]
    def logout(self):
        self.closed=True


def filenames(blob):
    text=blob.decode()
    return re.findall(r'TAX INVOICE-209126\d{6}\.PDF',text)


def parser(name):
    m=re.search(r'209126\d{6}',name)
    return (m.group(),"H-TEST","PO-TEST","AMEA-TEST",1100,"FILENAME_PARSED") if m else None


class ProofTests(unittest.TestCase):
    def test_entrypoint_and_package_imports_both_resolve(self):
        # No mail account or Sheets credentials: test module loading only.
        self.assertTrue(callable(proof.summarize_replay))
        entrypoint_dir=Path(proof.__file__).resolve().parent
        completed=subprocess.run(
            [sys.executable,"-c",
             "from qq_targeted_backfill_proof import summarize_replay; assert callable(summarize_replay)"],
            cwd=entrypoint_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=15)
        self.assertEqual(completed.returncode,0,"Direct-script import failed")

    def setUp(self):
        FakeIMAP.entries={}
        FakeIMAP.search_uids=None

    def test_picks_precursor_blank_and_postcursor_exactly(self):
        n0="209126000001";n1="209126000002";n2="209126000003"
        q=[qq(n1,month="",uid="420")]
        records=[ext(n0,uid="410"),ext(n1,uid="420"),
                 ext(n2,uid="700",when="2026-11-22T11:20:36+00:00")]
        targets,c,stamp=proof.pick_targets(q,[css("209126000099")],
                                            records,cursor(),audit())
        by={x["number"]:x["category"] for x in targets}
        self.assertEqual(by[n0],"PRE_CURSOR_MISSING")
        self.assertEqual(by[n1],"BLANK_ISSUED_MONTH")
        self.assertEqual(by[n2],"POST_CURSOR_PENDING")
        self.assertEqual(c["last_uid"],"500")

    def test_reassembles_split_mime_and_never_writes(self):
        n="209126000001"; e=ext(n,uid="410")
        targets,c,_=proof.pick_targets([qq("209126000009")],
                     [css("209126000010")],[e],cursor(),audit())
        FakeIMAP.entries={"410":{"number":n,"split":True}}
        with mock.patch.dict(os.environ,{"CSS_QQ_MAIL_ADDRESS":"test@example.com",
                                          "CSS_QQ_MAIL_AUTH_CODE":"offline-test"}):
            result=proof.check_imap(targets,c,{e["ingest_key"]:ingest(e)},
                                    FakeIMAP,filenames,parser)
        self.assertEqual(result["PRE_CURSOR_MISSING"],1)
        self.assertEqual(result["original_mime_verified"],1)
        self.assertEqual(result["fragmented_mime_legacy_parser_gap"],1)
        self.assertEqual(result["historical_single_chunk_parser_would_match"],0)
        self.assertEqual(result["qq_cursor_writes"],0)
        self.assertEqual(result["business_writes"],0)
        dump=json.dumps(result)
        self.assertNotIn(n,dump)
        self.assertNotIn("1100",dump)
        self.assertNotIn("test@example.com",dump)

    def test_blank_month_internaldate_is_not_invoice_issue_date(self):
        n="209126000002"; e=ext(n,uid="420")
        targets,c,_=proof.pick_targets([qq(n,month="",uid="420")],
                      [css("209126000010")],[e],cursor(),audit())
        FakeIMAP.entries={"420":{"number":n}}
        with mock.patch.dict(os.environ,{"CSS_QQ_MAIL_ADDRESS":"test@example.com",
                                          "CSS_QQ_MAIL_AUTH_CODE":"offline-test"}):
            result=proof.check_imap(targets,c,{e["ingest_key"]:ingest(e)},
                                    FakeIMAP,filenames,parser)
        self.assertEqual(result["original_mime_verified"],1)
        self.assertEqual(result["imap_arrival_metadata_available"],1)
        self.assertEqual(result["original_invoice_issue_date_proved"],0)
        self.assertNotIn("invoice_month",result)

    def test_mismatched_qq_uid_is_held_without_source_mutation(self):
        n="209126000002"; e=ext(n,uid="420")
        targets,c,_=proof.pick_targets([qq(n,month="",uid="404")],
                      [css("209126000010")],[e],cursor(),audit())
        FakeIMAP.entries={"420":{"number":n}}
        with mock.patch.dict(os.environ,{"CSS_QQ_MAIL_ADDRESS":"test@example.com",
                                          "CSS_QQ_MAIL_AUTH_CODE":"offline-test"}):
            result=proof.check_imap(targets,c,{e["ingest_key"]:ingest(e)},
                                    FakeIMAP,filenames,parser)
        self.assertEqual(result["blank_month_qq_extract_uid_conflict"],1)
        self.assertEqual(result["business_writes"],0)

    def test_wrong_original_sender_never_counts_as_proved(self):
        n="209126000001";e=ext(n)
        targets,c,_=proof.pick_targets([qq("209126000009")],
                      [css("209126000010")],[e],cursor(),audit())
        FakeIMAP.entries={"410":{"number":n,"sender":"unknown@example.com"}}
        with mock.patch.dict(os.environ,{"CSS_QQ_MAIL_ADDRESS":"test@example.com",
                                          "CSS_QQ_MAIL_AUTH_CODE":"offline-test"}):
            result=proof.check_imap(targets,c,{e["ingest_key"]:ingest(e)},
                                    FakeIMAP,filenames,parser)
        self.assertEqual(result.get("original_mime_verified",0),0)
        self.assertEqual(result["non_official_or_missing_header"],1)

    def test_uidvalidity_change_blocks_no_best_effort_fallback(self):
        n="209126000001";e=ext(n)
        targets,c,_=proof.pick_targets([qq("209126000009")],
                      [css("209126000010")],[e],cursor(uv="9999"),audit())
        with mock.patch.dict(os.environ,{"CSS_QQ_MAIL_ADDRESS":"test@example.com",
                                          "CSS_QQ_MAIL_AUTH_CODE":"offline-test"}):
            with self.assertRaisesRegex(ValueError,"IMAP_UIDVALIDITY_CHANGED"):
                proof.check_imap(targets,c,{e["ingest_key"]:ingest(e)},
                                 FakeIMAP,filenames,parser)

    def test_original_search_flags_absent_uid_without_guessing(self):
        n="209126000001"; e=ext(n,uid="410")
        targets,c,_=proof.pick_targets([qq("209126000009")],
                      [css("209126000010")],[e],cursor(),audit())
        FakeIMAP.entries={"410":{"number":n}}
        FakeIMAP.search_uids=[]
        with mock.patch.dict(os.environ,{"CSS_QQ_MAIL_ADDRESS":"test@example.com",
                                          "CSS_QQ_MAIL_AUTH_CODE":"offline-test"}):
            result=proof.check_imap(targets,c,{e["ingest_key"]:ingest(e)},
                                    FakeIMAP,filenames,parser)
        self.assertEqual(result["search_absent_pre_cursor_missing"],1)
        self.assertEqual(result["original_mime_verified"],1)
        self.assertEqual(result["historical_search_verified"],1)
        self.assertEqual(result["business_writes"],0)

    def test_date_fetch_response_shape_classified_without_date_output(self):
        self.assertEqual(proof.classify_internaldate_response(
            "OK", [b'2 (INTERNALDATE "22-Nov-2026 10:00:00 +0900")']),
            "VALID_ARRIVAL_DATE")
        self.assertEqual(proof.classify_internaldate_response(
            "OK", [b'2 (INTERNALDATE NIL)']),"DATE_NIL")
        self.assertEqual(proof.classify_internaldate_response(
            "OK", [b'2 (UID 401)']),"DATE_TOKEN_ABSENT")
        self.assertEqual(proof.classify_internaldate_response(
            "NO", []),"FETCH_STATUS_ERROR")
        self.assertEqual(proof.classify_internaldate_response(
            "OK", []),"EMPTY_RESPONSE")
        self.assertEqual(proof.classify_internaldate_response(
            "OK", [(123,)]),"NO_BYTE_PAYLOAD")

    def test_private_date_shape_variants_have_distinct_counters(self):
        cases = [
            (b'1 (INTERNALDATE NIL)', "DATE_NIL"),
            (b'1 (INTERNALDATE 22-Nov-2026 10:00:00 +0900)', "DATE_UNQUOTED"),
            (b'1 (INTERNALDATE "2-Nov-2026 10:00:00 +0900")', "VALID_ARRIVAL_DATE"),
            (b'1 (INTERNALDATE " 2-Nov-2026 10:00:00 +0900")', "VALID_ARRIVAL_DATE"),
            (b'1 (INTERNALDATE "2-Foo-2026 10:00:00 +0900")', "DATE_INVALID"),
            (b'1 (INTERNALDATE "22-Nov-2026 10:00:00 +09:00")', "DATE_COLON_TIMEZONE"),
            (b'1 (INTERNALDATE {12}', "DATE_IMAP_LITERAL"),
            (b'1 (INTERNALDATE BADDATE)', "DATE_FORMAT_OTHER"),
            (b'1 (INTERNALDATE "40-Nov-2026 10:00:00 +0900")', "DATE_INVALID"),
        ]
        for payload, expected in cases:
            with self.subTest(shape=expected):
                actual = proof.classify_internaldate_response("OK", [payload])
                self.assertEqual(actual, expected)

    def test_detailed_date_state_is_counter_only(self):
        n="209126000002"; e=ext(n,uid="420")
        targets,c,_=proof.pick_targets([qq(n,month="",uid="420")],
                      [css("209126000010")],[e],cursor(),audit())
        class NilIMAP(FakeIMAP):
            def uid(self,action,uid,query,*args):
                if action=="FETCH" and query=="(INTERNALDATE)":
                    return "OK",[b'1 (INTERNALDATE NIL)']
                return super().uid(action,uid,query,*args)
        FakeIMAP.entries={"420":{"number":n}}
        with mock.patch.dict(os.environ,{"CSS_QQ_MAIL_ADDRESS":"test@example.com",
                                          "CSS_QQ_MAIL_AUTH_CODE":"offline-test"}):
            result=proof.check_imap(targets,c,{e["ingest_key"]:ingest(e)},
                                    NilIMAP,filenames,parser)
        self.assertEqual(result["internaldate_date_nil"],1)
        self.assertEqual(result["original_invoice_issue_date_proved"],0)
        self.assertEqual(result["business_writes"],0)

    def test_original_search_rejects_failed_search_not_guess(self):
        class BadSearch(FakeIMAP):
            def uid(self,action,uid,query,*rest):
                if action=="SEARCH":return "NO",[]
                return super().uid(action,uid,query,*rest)
        n="209126000001"; e=ext(n,uid="410")
        targets,c,_=proof.pick_targets([qq("209126000009")],
                      [css("209126000010")],[e],cursor(),audit())
        with mock.patch.dict(os.environ,{"CSS_QQ_MAIL_ADDRESS":"test@example.com",
                                          "CSS_QQ_MAIL_AUTH_CODE":"offline-test"}):
            with self.assertRaisesRegex(ValueError,"BACKFILL_ORIGINAL_SEARCH_UNAVAILABLE"):
                proof.check_imap(targets,c,{e["ingest_key"]:ingest(e)},
                                 BadSearch,filenames,parser)

    def test_parser_never_accepts_wrong_amount(self):
        e=ext("209126000001")
        self.assertFalse(proof.parsed_matches(
            (e["invoice_number"],"H-TEST","PO-TEST","AMEA-TEST",1099,"FILENAME_PARSED"),e))
        self.assertFalse(proof.parsed_matches(
            (e["invoice_number"],"H-TEST","PO-TEST","AMEA-TEST",1100,"FALLBACK"),e))

    def test_internaldate_absent_or_invalid_is_not_proof(self):
        self.assertFalse(proof.extract_date_metadata([b"1 (FLAGS (\\Seen))"]))
        self.assertFalse(proof.extract_date_metadata([
            b'1 (INTERNALDATE "40-Nov-2026 10:00:00 +0900")']))
        self.assertTrue(proof.extract_date_metadata([
            b'1 (INTERNALDATE "22-Nov-2026 10:00:00 +0900")']))
        self.assertTrue(proof.extract_date_metadata([
            b'1 (INTERNALDATE "2-Nov-2026 10:00:00 +0900")']))
        self.assertTrue(proof.extract_date_metadata([
            b'1 (INTERNALDATE " 2-Nov-2026 10:00:00 +0900")']))
        self.assertFalse(proof.extract_date_metadata([
            b'1 (INTERNALDATE "2-Foo-2026 10:00:00 +0900")']))
        self.assertFalse(proof.extract_date_metadata([
            b'1 (INTERNALDATE "2-Nov-2026 10:00:00 +09:00")']))

    def test_caps_excessive_target_volume(self):
        cases=[ext("209126"+str(i).zfill(6),uid=str(100+i))
               for i in range(36)]
        with self.assertRaisesRegex(ValueError,"TARGET_SCOPE_TOO_LARGE"):
            proof.pick_targets([qq("209126999999")],[css("209126999998")],
                               cases,cursor(),audit())

    def test_cannot_infer_scanned_complete_when_status_partial(self):
        with self.assertRaisesRegex(ValueError,"QQ_SCAN_NOT_COMPLETE"):
            proof.pick_targets([qq("209126000001")],[css("209126000002")],
                               [ext("209126000003")],cursor(),
                               [{"year":"2026","status":"PARTIAL_SCAN",
                                 "last_run_utc":SCAN}])


if __name__=="__main__":
    unittest.main()
