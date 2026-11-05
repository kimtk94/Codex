#!/usr/bin/env python3
"""2026-only historical QQ IMAP backfill safeguards."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0,str(Path(__file__).parent))
import qq_mail_ingest as q
from mail_classification_2026 import since_2026


class HistoricalMailTests(unittest.TestCase):
    def test_kst_cutoff_inclusive(self):
        self.assertFalse(since_2026("2025-12-31T14:59:59Z"))
        self.assertTrue(since_2026("2025-12-31T15:00:00Z"))
        self.assertTrue(since_2026("2026-01-01T12:00:00+09:00"))
        self.assertFalse(since_2026(""))
        self.assertFalse(since_2026("2026-01-01"))

    def test_backfill_uses_2026_cutoff_and_batch_write(self):
        one={"Mail Key":"a"*64,"Direction":"INBOUND",
             "Subject":"Sample received","Received At":"2026-01-05T09:00:00+09:00"}
        with mock.patch.object(q,"required",side_effect=["qq@example.com","authcode"]), \
             mock.patch.object(q,"auth",return_value=("token","/base")), \
             mock.patch.object(q,"find_table",return_value="tableid"), \
             mock.patch.object(q,"ensure_table",return_value="/base/tables/tableid"), \
             mock.patch.object(q,"existing",return_value={}), \
             mock.patch.object(q,"collect_from_imap",return_value=[one]) as collect, \
             mock.patch.object(q,"api",return_value={"records":[{"record_id":"record1"}]}) as api, \
             mock.patch.object(q.imaplib,"IMAP4_SSL") as server, \
             mock.patch.dict(q.os.environ,{"FEISHU_MAIL_BATCH_PER_FOLDER":"150"}):
            server.return_value.__enter__.return_value.login.return_value=("OK",[])
            server.return_value.__enter__.return_value.list.return_value=(
                "OK",[b'() "/" "Sent Messages"'])
            q.run("backfill2026")
            self.assertEqual(collect.call_args.kwargs["since_date"],"31-Dec-2025")
            self.assertEqual(collect.call_args.kwargs["min_date_kst"],"2026-01-01")
            self.assertEqual(collect.call_args.args[2],150)
            self.assertTrue(api.call_args.args[1].endswith("/records/batch_create"))

    def test_scan_older_than_2026_is_dropped(self):
        class FakeIMAP:
            def select(self,*args,**kw):
                return "OK",[b"42"]
            def response(self,name):
                return "OK",[b"10"]
            def uid(self,command,*args):
                if command=="SEARCH":return "OK",[b"42"]
                from email.message import EmailMessage
                msg=EmailMessage()
                msg["Date"]="Thu, 25 Dec 2025 12:00:00 +0900"
                msg.set_content("old")
                return "OK",[(b"42",msg.as_bytes())]
            def list(self):
                return "OK",[b'() "/" "Sent Messages"']
        incoming=q.collect_from_imap(FakeIMAP(),{},10,30,
                                     since_date="31-Dec-2025",
                                     min_date_kst="2026-01-01")
        self.assertEqual(incoming,[])


if __name__=="__main__":
    unittest.main()
