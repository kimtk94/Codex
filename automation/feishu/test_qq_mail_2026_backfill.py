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

    def test_backfill_uses_3000_total_and_batch_write(self):
        one={"Mail Key":"a"*64,"Direction":"INBOUND",
             "Subject":"Sample received","Received At":"2026-01-05T09:00:00+09:00"}
        with mock.patch.object(q,"required",side_effect=["qq@example.com","authcode"]), \
             mock.patch.object(q,"auth",return_value=("token","/base")), \
             mock.patch.object(q,"find_table",return_value="tableid"), \
             mock.patch.object(q,"ensure_table",return_value="/base/tables/tableid"), \
             mock.patch.object(q,"existing",return_value={}), \
             mock.patch.object(q,"collect_2026_total",return_value=[one]) as collect, \
             mock.patch.object(q,"api",return_value={"records":[{"record_id":"record1"}]}) as api, \
             mock.patch.object(q.time,"sleep"), \
             mock.patch.object(q.imaplib,"IMAP4_SSL") as server, \
             mock.patch.dict(q.os.environ,{"FEISHU_MAIL_BACKFILL_TOTAL":"3000"}):
            server.return_value.__enter__.return_value.login.return_value=("OK",[])
            server.return_value.__enter__.return_value.list.return_value=(
                "OK",[b'() "/" "Sent Messages"'])
            q.run("backfill2026")
            self.assertEqual(collect.call_args.args[2],3000)
            self.assertTrue(api.call_args.args[1].endswith("/records/batch_create"))

    def test_allocate_3000_across_inbox_and_sent(self):
        quotas=q.allocate_2026_quotas([24000,2700],3000)
        self.assertEqual(sum(quotas),3000)
        self.assertGreater(quotas[0],quotas[1])
        self.assertEqual(q.allocate_2026_quotas([24000,0],3000),[3000,0])
        self.assertEqual(q.allocate_2026_quotas([0,2700],3000),[0,2700])
        self.assertEqual(q.allocate_2026_quotas([0,0],3000),[0,0])
        self.assertEqual(q.allocate_2026_quotas([1,1],3000),[1,1])
        self.assertEqual(q.allocate_2026_quotas([1,3000],3000),[1,2999])

    def test_uid_selection_never_exceeds_small_quota(self):
        uids=[b"1",b"2",b"3",b"4"]
        self.assertEqual(q.select_uids(uids,0),[])
        self.assertEqual(q.select_uids(uids,1),[b"4"])
        self.assertEqual(len(q.select_uids(uids,2)),2)
        self.assertEqual(len(q.select_uids(uids,3)),3)

    def test_collect_total_2026_respects_folder_quotas(self):
        from email.message import EmailMessage
        class FakeIMAP:
            current=""
            def list(self):
                return "OK",[b'() "/" "Sent Messages"']
            def select(self,folder,readonly=False):
                self.current=folder
                return "OK",[b"3"]
            def response(self,name):
                return "OK",[b"10"]
            def uid(self,cmd,*args):
                if cmd=="SEARCH":
                    return "OK",[b"1 2 3 4" if "INBOX" in self.current else b"5"]
                if cmd=="FETCH":
                    msg=EmailMessage()
                    msg["Date"]="Thu, 05 Nov 2026 12:00:00 +0900"
                    msg["Subject"]="Test 2026"
                    msg.set_content("Test")
                    return "OK",[(b"header",msg.as_bytes())]
        rows=q.collect_2026_total(FakeIMAP(),{},3)
        self.assertEqual(len(rows),3)
        self.assertEqual(sum(x["Direction"]=="OUTBOUND" for x in rows),1)
        self.assertEqual(sum(x["Direction"]=="INBOUND" for x in rows),2)
        self.assertEqual(len({x["Mail Key"] for x in rows}),3)

    def test_cutoff_applied_to_big_backfill_before_storage(self):
        from email.message import EmailMessage
        class FakeIMAP:
            current=""
            def list(self):
                return "OK",[b'() "/" "Sent Messages"']
            def select(self,folder,readonly=False):
                self.current=folder
                return "OK",[b"2"]
            def response(self,name):
                return "OK",[b"10"]
            def uid(self,cmd,*args):
                if cmd=="SEARCH":
                    return "OK",[b"1 2" if "INBOX" in self.current else b""]
                if cmd=="FETCH":
                    msg=EmailMessage()
                    msg["Date"]=("Wed, 31 Dec 2025 01:00:00 +0900" if args[0]==b"1"
                                 else "Thu, 01 Jan 2026 12:00:00 +0900")
                    msg.set_content("Test")
                    return "OK",[(b"header",msg.as_bytes())]
        rows=q.collect_2026_total(FakeIMAP(),{},3000)
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]["Received At"].startswith("2026-01-01"))

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
