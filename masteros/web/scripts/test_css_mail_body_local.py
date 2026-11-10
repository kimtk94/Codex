#!/usr/bin/env python3
"""Pure unit tests: the local viewer reads one cached, verified UID, not arbitrary mail."""
import pathlib
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import css_mail_local as m

KEY="INBOX|177|901"
UID="inbox:901"
def provider(session,book,tab,area):
    if tab==m.QUEUE and area=="K1:O2000":
        return [["Mail UID","Last Possible Outbound (KST)","To","Cc","Canonical Ingest Key"],
                [UID,"","other@novogene.com","taehoon.kim@novogene.com",KEY]]
    if tab=="CSS Mail Inbox Raw" and area=="A1:A10000":
        return [["Mail UID"],[UID]]
    if tab=="CSS Mail Inbox Raw" and area=="A2:V2":
        return [[UID]+[""]*8+["원본 본문 <html> literal, do not render HTML"]+[""]*11+["WEB_REVIEW_CACHE"]]
    raise AssertionError("Unexpected source "+tab+" "+area)

class BodyTests(unittest.TestCase):
    def test_body_matches_exact_queue_uid_and_reads_one_cached_row(self):
        with patch.object(m,"fetch",side_effect=provider):
            result=m.read_mail_body(object(),KEY,UID)
        self.assertEqual(result["status"],"PASS")
        self.assertEqual(result["uid"],UID)
        self.assertIn("<html>",result["body"])
        self.assertEqual(result["bodyStatus"],"WEB_REVIEW_CACHE")
    def test_arbitrary_mail_uid_rejected(self):
        with self.assertRaisesRegex(ValueError,"MAIL_BODY_ID_INVALID"):
            m.read_mail_body(object(),KEY,"sent:901")
        with patch.object(m,"fetch",side_effect=provider):
            with self.assertRaisesRegex(ValueError,"MAIL_BODY_QUEUE_UID_CHANGED"):
                m.read_mail_body(object(),"INBOX|177|902",UID)
    def test_missing_cache_returns_explicit_empty_reason(self):
        def unavailable(session,book,tab,area):
            if tab==m.QUEUE:return provider(session,book,tab,area)
            return [["Mail UID"]]
        with patch.object(m,"fetch",side_effect=unavailable):
            result=m.read_mail_body(object(),KEY,UID)
        self.assertEqual(result["bodyStatus"],"NOT_CACHED")
        self.assertFalse(result["body"])
    def test_body_request_is_read_only_and_bounded(self):
        m.validate_request({"mode":"body","uid":UID,"key":KEY})
        for arg in [
            {"mode":"body","uid":"inbox:abc","key":KEY},
            {"mode":"body","uid":UID,"key":"evil
url"},
            {"mode":"body","uid":UID,"key":KEY,"action":"SKIP_MAIL"},
        ]:
            with self.assertRaises(ValueError):
                m.validate_request(arg)

if __name__=="__main__":unittest.main()
