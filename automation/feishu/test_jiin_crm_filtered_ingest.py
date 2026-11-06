#!/usr/bin/env python3
"""Offline safety tests: only exact CRM sender, not forged display names or CC."""
import email.message
import imaplib
import os
import unittest
from unittest import mock
import jiin_crm_filtered_ingest as c

class CRMOnlyTests(unittest.TestCase):
    def test_exact_from_required_not_display_name(self):
        self.assertTrue(c.source_sender("CRM Office <crm@novogene.com>"))
        for value in ("crm@novogene.com.evil.test",
                      "crm+reports@novogene.com",
                      '"crm@novogene.com" <other@example.org>',
                      "person@novogene.com, crm@novogene.com",
                      "", "contact@crm.novogene.com"):
            with self.subTest(value=value):
                self.assertFalse(c.source_sender(value))

    def test_body_rejected_if_wrong_sender(self):
        m = email.message.EmailMessage()
        m["From"] = "Other <person@example.edu>"
        m["To"] = "jiin.yoo@novogene.com"
        m["Date"] = "Fri, 06 Nov 2026 09:00:00 +0900"
        m["Subject"] = "CRM Report"
        m.set_content("Some text")
        with self.assertRaisesRegex(c.SafeError,"CRM_BODY_SENDER_MISMATCH"):
            c.decode_checked(m.as_bytes(),"uidval","100")

    def test_valid_body_copies_source_and_namespace(self):
        m = email.message.EmailMessage()
        m["From"] = "CRM <crm@novogene.com>"
        m["To"] = "jiin.yoo@novogene.com"
        m["Date"] = "Fri, 06 Nov 2026 09:00:00 +0900"
        m["Subject"] = "CRM Notice AMEA2026042239"
        m.set_content("An account notice.")
        row=c.decode_checked(m.as_bytes(),"7","42")
        self.assertEqual(row["Source Account"],c.ACCOUNT)
        self.assertEqual(row["Source Filter"],"EXACT_FROM_CRM")
        self.assertEqual(row["From"],c.SENDER)
        self.assertNotEqual(row["Mail Key"], c.mail_key("8","42"))
        self.assertEqual(row["AMEA"],"AMEA2026042239")

    def test_mail_before_2026_refused(self):
        m=email.message.EmailMessage()
        m["From"]="crm@novogene.com"
        m["Date"]="Tue, 30 Dec 2025 20:00:00 +0900"
        m["To"]="jiin.yoo@novogene.com"
        m.set_content("Old")
        with self.assertRaisesRegex(c.SafeError,"CRM_BODY_DATE_MISMATCH"):
            c.decode_checked(m.as_bytes(),"7","10")

    def test_qq_exmail_uses_ssl_and_authorization_code_by_default(self):
        with mock.patch.dict(os.environ,{
                "JIIN_CRM_APP_PASSWORD": "a-test-only-fake-auth-code"
             },clear=True), \
             mock.patch.object(c.imaplib,"IMAP4_SSL") as server:
            client=server.return_value
            client.login.return_value=("OK",[])
            self.assertIs(c.open_mail(),client)
            server.assert_called_once_with("imap.exmail.qq.com",993,timeout=40)
            client.login.assert_called_once_with("jiin.yoo@novogene.com",
                                                 "a-test-only-fake-auth-code")
            client.authenticate.assert_not_called()

    def test_no_access_without_auth_secret(self):
        with mock.patch.dict(os.environ,{"JIIN_CRM_IMAP_HOST":"outlook.office365.com",
                          "JIIN_CRM_AUTH_METHOD":"oauth2",
                          "JIIN_CRM_OAUTH_ACCESS_TOKEN":""}), \
             mock.patch.object(c.imaplib,"IMAP4_SSL") as network:
            with self.assertRaisesRegex(c.SafeError,"OAUTH_TOKEN_MISSING"):
                c.open_mail()
            network.assert_not_called()

    def test_exact_sender_headers_before_body_fetch(self):
        def header(sender):
            return ("From: "+sender+"\r\n"
                    "Date: Fri, 06 Nov 2026 09:00:00 +0900\r\n"
                    "Subject: CRM report\r\n\r\n").encode()
        im=mock.Mock()
        im.select.return_value=("OK",[])
        im.response.return_value=("OK",[b"88"])
        im.uid.side_effect=[
            ("OK",[b"10 11"]),
            ("OK",[(b"header",header("Other <other@example.org>"))]),
            ("OK",[(b"header",header("CRM <crm@novogene.com>"))]),
        ]
        candidates,validity=c.matching_candidates(im,{},2)
        self.assertEqual(candidates,[b"11"])
        self.assertEqual(validity,"88")
        calls=[x.args for x in im.uid.call_args_list]
        self.assertEqual(len(calls),3)
        self.assertTrue(all("BODY.PEEK[HEADER.FIELDS" in x[2] for x in calls[1:]))
        self.assertEqual(c.mail_key("88","11"),c.mail_key("88","11"))

    def test_probe_never_selects_mail_or_writes(self):
        with mock.patch.dict(os.environ,{"FEISHU_BASE_APP_TOKEN":c.EXPECTED_BASE,
                                          "JIIN_CRM_MODE":"probe"}), \
             mock.patch.object(c,"auth",return_value=("token","/root")), \
             mock.patch.object(c,"open_mail") as open_mail, \
             mock.patch.object(c,"ensure_table") as ensure:
            c.run()
            ensure.assert_not_called()
            open_mail.return_value.select.assert_not_called()
            open_mail.return_value.logout.assert_called_once()

if __name__=="__main__":
    unittest.main()
