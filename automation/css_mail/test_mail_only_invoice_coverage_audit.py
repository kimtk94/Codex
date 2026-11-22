#!/usr/bin/env python3
"""Verified original TAX INVOICE CSS mail only; never manual ERP or forecast."""
import unittest
from unittest import mock
from email.parser import Parser
from mail_only_invoice_coverage_audit import (
    identify_missing,original_proof,net,numeric,
    audit_with_original_imap,select_extracted_original_candidates,
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


    def test_full_2026_both_projection_sources_preserve_older_unmatched(self):
        # Full-year proof must not mislabel already-recorded legacy rows as gaps.
        history=[
            backfill("209126000111",1200,month="2026-08"),
            backfill("209126000222",1300,month="2026-09"),
            backfill("209126000333",1400,month="2026-10"),
            backfill("209126000444",1500,month="2026-11"),
            backfill("209126000555",1600,month="2026-11"),
        ]
        ext=[extracted("209126000333",1400)]
        legacy=[extracted("209126000555",1600)]
        missing=identify_missing(history,ext,canonical=legacy,start_month="2026-01")
        self.assertEqual(set(missing),{
            "209126000111","209126000222","209126000444"
        })


    def test_formatted_canonical_krw_is_parsed_without_weakening_qq_amount(self):
        history=[
            backfill("209126000555",1600,month="2026-11"),
            backfill("209126000666",1700,month="2026-11"),
        ]
        canonical=[extracted("209126000555","1,600 KRW")]
        missing=identify_missing(history,[extracted("209126000999",1000)],
                                 canonical=canonical,start_month="2026-01")
        self.assertEqual(set(missing),{"209126000666"})
        with self.assertRaisesRegex(ValueError,"BAD_ORIGINAL_INVOICE_AMOUNT"):
            identify_missing([backfill("209126000666","1,700")],
                             [extracted("209126000999",1000)],
                             canonical=canonical,start_month="2026-01")

    def test_legacy_extract_price_conflict_is_blocked(self):
        with self.assertRaisesRegex(ValueError,"CANONICAL_EXTRACT_INVOICE_AMOUNT_CONFLICT"):
            identify_missing([backfill("209126000888",1500)],
                             [extracted("209126000999",1000)],
                             canonical=[extracted("209126000999",2000)],
                             start_month="2026-01")

    def test_one_mail_uid_may_have_multiple_distinct_invoices(self):
        missing=identify_missing([
            backfill("209126000111",1200,month="2026-08"),
            backfill("209126000222",1300,month="2026-09")
        ], [extracted("209126000999",900)],
           canonical=[extracted("209126000888",800)],start_month="2026-01")
        self.assertEqual(len(missing),2)
        self.assertEqual({v[-1] for v in missing.values()},{"41234"})

    def test_public_main_does_not_print_invoice_ids_or_amounts(self):
        import inspect
        from mail_only_invoice_coverage_audit import main
        source=inspect.getsource(main)
        self.assertNotIn('invoice="+inv',source)
        self.assertNotIn('gross_krw="+str',source)
        self.assertNotIn('net_krw="+str',source)
        self.assertIn("MAIL_ONLY_PRIVATE_EVIDENCE_REDACTED",source)


    @staticmethod
    def derived_pair(invoice="209126000887",amount=12012000,uid="41234"):
        qq=backfill(invoice,amount,month="2026-11")
        qq.update({"h_project_id":"H209SC26065705","po_reference":"PO9",
                   "imap_uid":uid})
        ext=extracted(invoice,amount)
        ext.update({"project_id":"AMEA2026030802",
                    "h_project_number":"H209SC26065705",
                    "po_reference":"PO9","imap_uid":uid,
                    "validation_status":"FILENAME_PARSED"})
        return qq,ext

    def test_derived_original_candidates_require_four_key_lineage(self):
        q,e=self.derived_pair()
        candidates,held,reasons,overlap=select_extracted_original_candidates(
            [q],[e],[extracted("209126000001",900)])
        self.assertEqual((len(candidates),held,overlap),(1,0,1))
        self.assertEqual(reasons,{})
        self.assertEqual(candidates[q["invoice_number"]][5:],
                         ("H209SC26065705","PO9"))

    def test_derived_uid_conflict_and_missing_po_remain_metadata_hold(self):
        q,e=self.derived_pair()
        e["imap_uid"]="41235"
        e["po_reference"]=""
        candidates,held,reasons,overlap=select_extracted_original_candidates(
            [q],[e],[extracted("209126000001",900)])
        self.assertEqual(candidates,{})
        self.assertEqual((held,overlap),(1,1))
        self.assertEqual(reasons,{"PO_MISSING":1,"UID_MISMATCH":1})

    def test_derived_amount_match_cannot_override_wrong_project(self):
        q,e=self.derived_pair()
        e["project_id"]="AMEA2026030803"
        candidates,held,reasons,_=select_extracted_original_candidates(
            [q],[e],[extracted("209126000001",900)])
        self.assertEqual((candidates,held),({},1))
        self.assertEqual(reasons,{"AMEA_MISMATCH":1})

    def test_derived_canonical_invoice_is_not_an_unrecorded_gap(self):
        q,e=self.derived_pair()
        candidates,held,reasons,overlap=select_extracted_original_candidates(
            [q],[e],[extracted(q["invoice_number"],12012000)])
        self.assertEqual((candidates,held,reasons,overlap),({},0,{},0))

    def test_original_proof_for_derived_requires_h_and_po(self):
        q,e=self.derived_pair()
        filename=("TAX INVOICE-209126000887-H209SC26065705-PO9-"
                  "AMEA2026030802-KRW12012000.00.pdf")
        expected=("2026-11",12012000,"AMEA2026030802",
                  "FILENAME_PARSED","41234","H209SC26065705","PO9")
        self.assertTrue(original_proof(header(),[filename],
                                      q["invoice_number"],expected)["sender_verified"])
        with self.assertRaisesRegex(ValueError,"ORIGINAL_PO_MISMATCH"):
            original_proof(header(),[filename],q["invoice_number"],
                           expected[:-1]+("PO10",))
        with self.assertRaisesRegex(ValueError,"ORIGINAL_CONTRACT_MISMATCH"):
            original_proof(header(),[filename],q["invoice_number"],
                           expected[:5]+("H209SC26000000","PO9"))

    def test_several_invoices_on_same_uid_are_not_deduplicated(self):
        q1,e1=self.derived_pair("209126000887",12012000)
        q2,e2=self.derived_pair("209126000888",1000000)
        candidates,held,_,overlap=select_extracted_original_candidates(
            [q1,q2],[e1,e2],[extracted("209126000001",900)])
        self.assertEqual((len(candidates),held,overlap),(2,0,2))
        self.assertEqual({x[4] for x in candidates.values()},{"41234"})

    def test_bad_derived_filename_status_is_held(self):
        q,e=self.derived_pair()
        e["validation_status"]="EXISTS_IN_LEGACY"
        candidates,held,reasons,_=select_extracted_original_candidates(
            [q],[e],[extracted("209126000001",900)])
        self.assertEqual((candidates,held),({},1))
        self.assertEqual(reasons,{"EXTRACT_PROVENANCE_UNVERIFIED":1})


if __name__=="__main__":
    unittest.main()
