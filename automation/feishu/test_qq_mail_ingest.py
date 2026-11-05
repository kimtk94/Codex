#!/usr/bin/env python3
"""Offline safety checks for the isolated QQ Mail -> Feishu connector."""
import email.message
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import qq_mail_ingest as q


class MailFeishuTests(unittest.TestCase):
    def test_key_is_stable_and_folder_uidvalidity_scoped(self):
        self.assertEqual(q.key("INBOX", "7", "42"), q.key("INBOX", "7", "42"))
        self.assertNotEqual(q.key("INBOX", "7", "42"), q.key("Sent", "7", "42"))
        self.assertNotEqual(q.key("INBOX", "7", "42"), q.key("INBOX", "8", "42"))

    def test_select_uids_backfills_and_prioritizes_latest(self):
        self.assertEqual(q.select_uids([b"1", b"2", b"3", b"4", b"5", b"6"], 4),
                         [b"1", b"2", b"5", b"6"])

    def test_decode_mail_strips_attachment_and_extracts_ids(self):
        m = email.message.EmailMessage()
        m["Message-ID"] = "<abc@example.com>"
        m["Subject"] = "Invoice AMEA2026042239 H209SC26065705"
        m["From"] = "Client <Client@example.com>"
        m["To"] = "sales@example.com"
        m.set_content("Safe mail text")
        m.add_attachment(b"SECRET_ATTACHMENT", maintype="application", subtype="octet-stream",
                         filename="secret.bin")
        row = q.decode_mail(m.as_bytes(), "INBOX", "INBOUND", "10", "15")
        self.assertEqual(row["Body Excerpt"], "Safe mail text")
        self.assertNotIn("SECRET_ATTACHMENT", row["Body Excerpt"])
        self.assertEqual(row["AMEA"], "AMEA2026042239")
        self.assertEqual(row["H Project"], "H209SC26065705")
        self.assertEqual(row["From"], "client@example.com")

    def test_existing_rejects_duplicate_keys(self):
        dup = [{"record_id": "rec1", "fields": {"Mail Key": [{"text": "X"}]}},
               {"record_id": "rec2", "fields": {"Mail Key": [{"text": "X"}]}}]
        with mock.patch.object(q, "list_all", return_value=dup):
            with self.assertRaisesRegex(q.SafeError, "DUPLICATE_MAIL_KEYS"):
                q.existing("token", "path")

    def test_rejects_wrong_target_schema_without_writes(self):
        fields = [{"field_name": n, "type": 1} for n in q.FIELDS if n != "Mail Key"]
        with mock.patch.object(q, "find_table", return_value="tblABC"), \
             mock.patch.object(q, "get_fields", return_value=fields), \
             mock.patch.object(q, "api") as requests:
            with self.assertRaisesRegex(q.SafeError, "STAGING_SCHEMA_MISMATCH"):
                q.ensure_table("token", "/root")
            requests.assert_not_called()

    def test_smoke_checks_readback(self):
        with mock.patch.object(q, "write_record", return_value="rec123") as write, \
             mock.patch.object(q, "api", return_value={
                 "record": {"fields": {"Mail Key": [{"text": q.SMOKE_KEY}]}}}) as fetch:
            indexed = {}
            q.smoke("token", "/table", indexed)
            self.assertEqual(indexed[q.SMOKE_KEY], "rec123")
            self.assertEqual(write.call_count, 1)
            self.assertEqual(fetch.call_count, 1)

    def test_probe_never_calls_writes_or_reads_customer_mail(self):
        with mock.patch.object(q, "required", side_effect=["mail", "pass"]), \
             mock.patch.object(q, "auth", return_value=("token", "/base")), \
             mock.patch.object(q, "find_table", return_value=None), \
             mock.patch.object(q.imaplib, "IMAP4_SSL") as server, \
             mock.patch.object(q, "ensure_table") as ensure, \
             mock.patch.object(q, "smoke") as smoke:
            server.return_value.__enter__.return_value.login.return_value = ("OK", [])
            server.return_value.__enter__.return_value.list.return_value = (
                "OK", [b'() "/" "Sent Messages"'])
            q.run("probe")
            ensure.assert_not_called()
            smoke.assert_not_called()

    def test_html_sanitizes_script(self):
        m = email.message.EmailMessage()
        m.set_content('<p>Hello</p><script>secret</script>', subtype="html")
        self.assertEqual(q.extract_body(m), "Hello")


if __name__ == "__main__":
    unittest.main()
