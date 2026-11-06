#!/usr/bin/env python3
"""Read-only original PO MIME validation regressions."""
from email.message import EmailMessage
import unittest
from unittest import mock
import po_original_mime_review as p
import po_body_multiplicity_audit as audit
import contract_po_tracker as po


def raw_message(body, sender="crm@novogene.com", attach=False):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "recipient@example.net"
    msg["Subject"] = "PO AMEA2026042239"
    msg["Message-ID"] = "<original@example.com>"
    msg["Date"] = "Fri, 06 Nov 2026 12:00:00 +0900"
    msg.set_content(body)
    if attach:
        msg.add_attachment(b"PDFDATA", maintype="application",
                           subtype="pdf", filename="test.pdf")
    return msg.as_bytes()


def row(subject, body="", sender=po.CRM_SENDER, uid="one"):
    fields = {"Mail Key":uid, "Message ID": "<original@example.com>",
              "From": sender, "Direction": "INBOUND",
              "Received At": "2026-11-06T12:00:00+09:00",
              "In Reply To": "", "Subject": subject,
              "Body Excerpt": body}
    if sender == po.CRM_SENDER:
        fields["Source Account"] = po.CRM_ACCOUNT
        fields["Source Filter"] = "EXACT_FROM_CRM"
    return {"fields": fields}


class FakeIMAP:
    def __init__(self, key, uid, body):
        self.key=key
        self.uid_value=uid
        self.body=body
        self.is_readonly=False
        self.fetches=0
        self.logged_out=False

    def select(self, name, readonly=False):
        self.is_readonly=readonly
        return "OK", [b"1"]

    def response(self, what):
        return "UIDVALIDITY", [b"77"]

    def uid(self, command, *args):
        if command=="SEARCH":
            return "OK", [self.uid_value.encode()]
        if command=="FETCH":
            self.fetches+=1
            return "OK", [(b"1 (UID 123 RFC822.SIZE "+str(len(self.body)).encode()
                           +b" BODY[]<0> {"+str(len(self.body)).encode()+b"}",
                           self.body), b")"]
        raise AssertionError(command)

    def logout(self):
        self.logged_out=True


class MimeReviewTests(unittest.TestCase):
    def test_full_message_excerpt_versus_true_body(self):
        body="We have received the PO. "+("Original correspondence\n"*150)
        raw=raw_message(body, attach=True)
        fields=row("PO AMEA2026042239", body[:1800])["fields"]
        found=p.inspect_message(raw, fields, po.CRM_SENDER, len(raw))
        self.assertTrue(found["complete_mime"])
        self.assertGreater(found["full_body_chars"], 1800)
        self.assertTrue(found["body_longer_than_excerpt"])
        self.assertTrue(found["attachment_mime_part_seen"])
        self.assertEqual(found["raw_body_signal"], "BODY_DELIVERY_CLAIM_REVIEW")

    def test_mail_is_not_verified_from_mime_attachment(self):
        raw=raw_message("PO approved and attached",attach=True)
        found=p.inspect_message(raw,row("PO AMEA2026042239","PO approved")["fields"],
                                po.CRM_SENDER,len(raw))
        self.assertTrue(found["attachment_mime_part_seen"])
        self.assertEqual(found["raw_body_signal"],"BODY_APPROVAL_CLAIM_REVIEW")
        self.assertNotIn("document_receipt_verified", found)

    def test_partial_raw_mime_not_complete(self):
        raw=raw_message("PO received")
        found=p.inspect_message(raw,row("PO AMEA2026042239","PO received")["fields"],
                                po.CRM_SENDER,len(raw)+999)
        self.assertFalse(found["complete_mime"])

    def test_source_header_identity_strict(self):
        raw=raw_message("PO received",sender="evil@example.com")
        with self.assertRaisesRegex(p.SafeError,"SENDER_MISMATCH"):
            p.inspect_message(raw,row("PO AMEA2026042239")["fields"],
                              po.CRM_SENDER,len(raw))

    def test_message_id_mismatch_rejected(self):
        raw=raw_message("PO received")
        f=row("PO AMEA2026042239")["fields"]
        f["Message ID"]="<another@example.com>"
        with self.assertRaisesRegex(p.SafeError,"MESSAGE_ID_MISMATCH"):
            p.inspect_message(raw,f,po.CRM_SENDER,len(raw))

    def test_candidate_selection_prioritizes_truncated_and_delivery_claims(self):
        source={"CRM Filtered Mail Intake":[
            row("PO AMEA2026042239","We have received the PO",uid="m1"),
            row("PO AMEA2026042240","Status update PO",uid="m2"),
            row("PO AMEA2026042241","x"*1800,uid="m3"),
        ],"QQ Mail Intake":[]}
        selected,counts=p.targets(source)
        self.assertEqual(set(selected["CRM Filtered Mail Intake"]),{"m1","m3"})
        self.assertEqual(counts["source_CRM"],2)

    def test_untrusted_body_only_project_never_promoted(self):
        source={"CRM Filtered Mail Intake":[
            row("Weekly notice","We received PO AMEA2026042239",uid="m1")
        ],"QQ Mail Intake":[]}
        selected,_=p.targets(source)
        self.assertEqual(len(selected["CRM Filtered Mail Intake"]),1)
        # Identity is still the stored Mail Key only, not body project ID.
        self.assertEqual(audit.classify(source["CRM Filtered Mail Intake"][0]["fields"],
                                       po.CRM_SENDER,
                                       "CRM Filtered Mail Intake")["project"],None)

    def test_only_mime_for_owned_qq_contract_after_creation(self):
        source={"CRM Filtered Mail Intake":[
            row("PO AMEA2026042239","We received PO",uid="owned-after"),
            row("PO AMEA2026042240","We received PO",uid="other-sales"),
            row("PO AMEA2026042239","We received PO",uid="owned-before"),
        ],"QQ Mail Intake":[]}
        source["CRM Filtered Mail Intake"][2]["fields"]["Received At"]="2026-11-05T09:00:00+09:00"
        owned={"AMEA2026042239":po.parse_time("2026-11-06T09:00:00+09:00")}
        selected,counts=p.targets(source,owned)
        self.assertEqual(list(selected["CRM Filtered Mail Intake"]),["owned-after"])
        self.assertEqual(counts["source_CRM"],1)

    def test_body_only_project_id_never_auto_joins_owner(self):
        source={"CRM Filtered Mail Intake":[
            row("Weekly update","PO received AMEA2026042239",uid="body-only"),
        ],"QQ Mail Intake":[]}
        owned={"AMEA2026042239":po.parse_time("2026-11-05T09:00:00+09:00")}
        selected,_=p.targets(source,owned)
        self.assertEqual(selected["CRM Filtered Mail Intake"],{})

    def test_fetch_is_readonly_and_lookup_key_matches(self):
        raw=raw_message("PO has been received")
        key=p.lookup_key("CRM Filtered Mail Intake","77","123")
        fake=FakeIMAP(key,"123",raw)
        source={key:row("PO AMEA2026042239","PO received",uid=key)["fields"]}
        with mock.patch.object(p,"open_source",return_value=fake):
            stats=p.verify_source("CRM Filtered Mail Intake",po.CRM_SENDER,source)
        self.assertTrue(fake.is_readonly)
        self.assertTrue(fake.logged_out)
        self.assertEqual(fake.fetches,1)
        self.assertEqual(stats["fetched"],1)
        self.assertEqual(stats["missing_uid_or_changed_validity"],0)

    def test_key_missing_does_not_guess_nearest_uid(self):
        raw=raw_message("PO received")
        fake=FakeIMAP("notmatched","123",raw)
        with mock.patch.object(p,"open_source",return_value=fake):
            stats=p.verify_source("CRM Filtered Mail Intake",po.CRM_SENDER,
                                  {"some-unrelated-key":row("PO AMEA2026042239")["fields"]})
        self.assertEqual(fake.fetches,0)
        self.assertEqual(stats["missing_uid_or_changed_validity"],1)

    def test_empty_selection_no_mail_login(self):
        with mock.patch.object(p,"open_source") as op:
            self.assertEqual(p.verify_source("QQ Mail Intake",po.CSS,{}),{})
            op.assert_not_called()

    def test_wrong_base_before_mail_credentials(self):
        with mock.patch.dict(p.os.environ,{"FEISHU_BASE_APP_TOKEN":"wrong"}), \
             mock.patch.object(p,"auth") as a:
            with self.assertRaisesRegex(p.SafeError,"WRONG_BASE"):
                p.main()
            a.assert_not_called()


if __name__=="__main__":
    unittest.main()
