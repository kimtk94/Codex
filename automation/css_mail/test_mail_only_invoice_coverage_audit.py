#!/usr/bin/env python3
"""Verified original TAX INVOICE CSS mail only; never manual ERP or forecast."""
import unittest
from unittest import mock
from email.parser import Parser
from mail_only_invoice_coverage_audit import (
    identify_missing,original_proof,net,numeric,
    audit_with_original_imap,
)


def backfill(invoice,amount,month="2026-10",
             state="FILENAME_PARSED",folder="INBOX"):
    return {"invoice_number":invoice,"amount_krw":str(amount),
            "issued_month":month,"amea_project_id":"AMEA2026030802",
            "evidence":state,"imap_folder":folder,"imap_uid":"41234"}


def extracted(invoice,amount):
    return {"invoice_number":invoice,"amount_krw":str(amount)}


def header(sender="CSS <css@novogene-amea.com>",subject=None,reply=False):
    subject=subject or (
        "Notice: Invoice Issued & Statement Confirmed "
        "209126000887 H209SC26065705 AMEA2026030802")
    content="From: "+sender+"\nSubject: "+subject+"\n"
    if reply:content+="In-Reply-To: <x@domain>\n"
    return Parser().parsestr(content)


class MailOnlyTests(unittest.TestCase):
    def test_split_backfill_gap_from_already_in_extract(self):
        history=[
            backfill("209126000887",12012000),
            backfill("209126000926",1470150,state="SUBJECT_CORROBORATED_FILENAME"),
            backfill("209126000989",2282500),
            backfill("209126000757",2678500,month="2026-08"),
            # No ERP manual invoice is in the original QQ mail scope.
            backfill("20910000208",1287000),
        ]
        extracted_rows=[extracted("209126000989",2282500)]
        missing=identify_missing(history,extracted_rows)
        self.assertEqual(set(missing),{"209126000887","209126000926"})
        self.assertEqual(sum(v[1] for v in missing.values()),13482150)
        self.assertEqual(sum(net(v[1]) for v in missing.values()),12256500)

    def test_nonofficial_inbox_reply_excluded_not_missing_revenue(self):
        from email.message import EmailMessage
        class FakeIMAP:
            def __init__(self,*args,**kwargs):pass
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def login(self,user,password):pass
            def select(self,folder,readonly=False):
                assert readonly and folder=="INBOX"
                return "OK",[]
            def uid(self,verb,uid,query):
                assert verb=="FETCH" and uid=="41234"
                if "HEADER.FIELDS" in query:
                    return "OK",[(b"1 FETCH",(
                        b"From: Someone <other@novogene.com>\r\n"
                        b"Subject: Re: Invoice Issued & Statement Confirmed\r\n"
                        b"In-Reply-To: <orig@novogene.com>\r\n\r\n"))]
                raise AssertionError("BODYSTRUCTURE must not be read")
            def logout(self):pass
        missing={"209126000887":("2026-10",12012000,
                "AMEA2026030802","FILENAME_PARSED","41234")}
        with mock.patch.dict("os.environ",{
                "CSS_QQ_MAIL_ADDRESS":"test@example.com",
                "CSS_QQ_MAIL_AUTH_CODE":"test-only"}):
            verified,blocked,excluded=audit_with_original_imap(
                missing,imap_factory=FakeIMAP)
        self.assertEqual(verified,{})
        self.assertEqual(blocked,{})
        self.assertEqual(set(excluded),{"209126000887"})
        self.assertIn("sender_css=false",excluded["209126000887"])
        self.assertIn("subject_reply=true",excluded["209126000887"])

    def test_strict_original_filename_amount_notice_and_sender(self):
        original=("TAX INVOICE-209126000887-H209SC26065705-PO9-"
                  "AMEA2026030802-KRW12012000.00.pdf")
        outcome=original_proof(header(),[original],
                       "209126000887",
                       ("2026-10",12012000,"AMEA2026030802",
                        "FILENAME_PARSED","41234"))
        self.assertEqual(outcome["amount"],12012000)
        self.assertEqual(outcome["net"],10920000)
        self.assertTrue(outcome["sender_verified"])

    def test_fallback_filename_requires_same_original_notice_hid_and_amea(self):
        filename=("TAX INVOICE-209126000926-AMEA2026030802-"
                  "KRW1470150.00.pdf")
        msg=header(subject=("Notice: Invoice Issued & Statement Confirmed "
                   "209126000926 AMEA2026030802 H209SC26065705"))
        result=original_proof(msg,[filename],"209126000926",
                              ("2026-10",1470150,"AMEA2026030802",
                               "SUBJECT_CORROBORATED_FILENAME","41234"))
        self.assertEqual(result["net"],1336500)
        with self.assertRaisesRegex(ValueError,"STRICT_FILENAME_DOWNGRADED"):
            original_proof(msg,[filename],"209126000926",
                           ("2026-10",1470150,"AMEA2026030802",
                            "FILENAME_PARSED","41234"))

    def test_invalid_sender_reply_and_conflicting_amount_fail(self):
        file=("TAX INVOICE-209126000887-H209SC26065705-PO9-"
              "AMEA2026030802-KRW12012000.00.pdf")
        expected=("2026-10",12012000,"AMEA2026030802",
                  "FILENAME_PARSED","41234")
        for msg in (header(sender="Someone <unknown@example.com>"),
                    header(reply=True),
                    header(subject="Re: Notice: Invoice Issued & Statement Confirmed")):
            with self.assertRaisesRegex(ValueError,"EMAIL_IDENTITY_UNVERIFIED"):
                original_proof(msg,[file],"209126000887",expected)
        with self.assertRaisesRegex(ValueError,"AMOUNTS_OR_AMEA_CONFLICT"):
            original_proof(header(),[file],"209126000887",
                           ("2026-10",12012001,"AMEA2026030802",
                            "FILENAME_PARSED","41234"))

    def test_duplicate_id_amount_conflict_not_silently_ignored(self):
        rows=[backfill("209126000887",12012000),
              backfill("209126000887",12012001)]
        with self.assertRaisesRegex(ValueError,"DUPLICATE_SOURCE_CONFLICT"):
            identify_missing(rows,[extracted("209126000001",1)])

    def test_positive_krw_only_and_invoice_vat_rounding(self):
        self.assertEqual(net(4438500),4035000)
        self.assertEqual(net(1969000),1790000)
        self.assertEqual(sum(net(v) for v in
                         (12012000,1470150,4438500,1969000)),18081500)
        with self.assertRaises(ValueError):
            numeric("-100")
        with self.assertRaises(ValueError):
            numeric("0")

    def test_no_sent_folder_is_considered_original_received_mail(self):
        with self.assertRaisesRegex(ValueError,"NOT_ORIGINAL_INBOX"):
            identify_missing([
                backfill("209126000887",12012000,folder="Sent Messages")],
                [extracted("209126000001",1)])


if __name__=="__main__":
    unittest.main()
