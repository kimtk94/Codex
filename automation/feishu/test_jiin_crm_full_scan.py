#!/usr/bin/env python3
"""No live mailbox access. Verify exact-sender full scan, cursor and recovery."""
import datetime as dt
import email.message
import imaplib
import os
import unittest
from unittest import mock
import jiin_crm_full_scan as f
import jiin_crm_filtered_ingest as c


class CRMFullScanTests(unittest.TestCase):
    def test_search_scans_ascending_uids_above_checkpoint(self):
        im=mock.Mock()
        im.select.return_value=("OK", [])
        im.response.return_value=("OK", [b"44"])
        im.uid.return_value=("OK",[b"23 11 22 20 19 20"])
        validity,uids,pending=f.search_next(im,20,10,"44")
        self.assertEqual(validity,"44")
        self.assertEqual(uids,[22,23])
        self.assertEqual(pending,2)
        with self.assertRaisesRegex(f.SafeError,"UIDVALIDITY_CHANGED"):
            f.search_next(im,20,10,"older")

    def test_header_sender_exact_precedes_body(self):
        def hdr(sender):
            return (("From: "+sender+"\r\n")+
                    "Date: Fri, 06 Nov 2026 09:00:00 +0900\r\n\r\n").encode()
        im=mock.Mock()
        im.uid.return_value=("OK",[(b"meta",hdr("crm@novogene.com.evil.org"))])
        self.assertIsNone(f.selected_mail(im,4,"44",{}))
        im.uid.assert_called_once()  # No body fetching for unrelated sender

    def test_header_accepted_body_requires_exact_sender(self):
        m=email.message.EmailMessage()
        m["From"]="crm@novogene.com"
        m["Date"]="Fri, 06 Nov 2026 09:00:00 +0900"
        m["To"]="jiin.yoo@novogene.com"
        m["Subject"]="test CRM"
        m.set_content("message")
        hdr=("From: crm@novogene.com\r\n"
             "Date: Fri, 06 Nov 2026 09:00:00 +0900\r\n\r\n").encode()
        im=mock.Mock()
        im.uid.side_effect=[("OK",[(b"h",hdr)]),
                            ("OK",[(b"body",m.as_bytes())])]
        row=f.selected_mail(im,44,"55",{})
        self.assertEqual(row["From"],"crm@novogene.com")
        self.assertEqual(row["Mail Key"],c.mail_key("55","44"))
        self.assertEqual(im.uid.call_count,2)

    def test_durable_cursor_advances_only_after_storage(self):
        im=mock.Mock()
        initial={"uidvalidity":"55","last_uid":10,"scanned":10,"saved":2}
        with mock.patch.object(f,"search_next",return_value=("55",[11,12,13],3)), \
             mock.patch.object(f,"selected_mail",side_effect=[None,{"Mail Key":"aa"},None]), \
             mock.patch.object(f,"persist_batch",return_value=1) as write, \
             mock.patch.object(f,"write_checkpoint",return_value="rec") as commit:
            rec,state,count,remaining,done=f.scan_block(im,"tok","mail","progress",
                                                     "old",initial,{},200)
        self.assertEqual((count,remaining,done),(3,0,False))
        self.assertEqual((state["last_uid"],state["scanned"],state["saved"]),(13,13,3))
        self.assertEqual(write.call_count,1)
        commit.assert_called_once()
        self.assertEqual(rec,"rec")

    def test_failed_write_does_not_advance_cursor(self):
        with mock.patch.object(f,"search_next",return_value=("55",[11],1)), \
             mock.patch.object(f,"selected_mail",return_value={"Mail Key":"x"}), \
             mock.patch.object(f,"persist_batch",side_effect=f.SafeError("STORE_FAIL")), \
             mock.patch.object(f,"write_checkpoint") as progress:
            with self.assertRaisesRegex(f.SafeError,"STORE_FAIL"):
                f.scan_block(mock.Mock(),"tok","mail","progress","old",
                             {"uidvalidity":"55","last_uid":10,"scanned":10,"saved":0},{},200)
            progress.assert_not_called()

    def test_reject_duplicate_saved_keys(self):
        with mock.patch.object(f,"list_all",return_value=[
                {"fields":{"Mail Key":"same"}},{"fields":{"Mail Key":"same"}}]), \
             mock.patch.object(f.c,"ensure_table",return_value="mail"), \
             mock.patch.object(f,"ensure_checkpoint",return_value="state"):
            with self.assertRaisesRegex(f.SafeError,"DUPLICATE_SOURCE_KEY"):
                f.drain("t","root",300)

    def test_backfill_mode_routes_through_checkpoint(self):
        with mock.patch.dict(os.environ,{"JIIN_CRM_MODE":"backfill",
                                          "FEISHU_BASE_APP_TOKEN":c.EXPECTED_BASE,
                                          "JIIN_CRM_MAIL_LIMIT":"15000"}), \
             mock.patch.object(c,"auth",return_value=("t","root")), \
             mock.patch.object(f,"drain",return_value={"complete":True}) as drain:
            self.assertEqual(c.run(),{"complete":True})
            drain.assert_called_once_with("t","root",15000)

    def test_limits_abort_empty_and_probe(self):
        with mock.patch.dict(os.environ,{"JIIN_CRM_MODE":"backfill",
                                          "FEISHU_BASE_APP_TOKEN":c.EXPECTED_BASE,
                                          "JIIN_CRM_MAIL_LIMIT":"15001"}), \
             mock.patch.object(c,"auth") as auth:
            with self.assertRaisesRegex(c.SafeError,"MAIL_LIMIT_INVALID"):
                c.run()
            auth.assert_not_called()

if __name__=="__main__":
    unittest.main()
