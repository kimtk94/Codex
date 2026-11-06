#!/usr/bin/env python3
import unittest
from qq_mail_ingest import SafeError
from jiin_crm_filtered_ingest import mail_key
import jiin_crm_source_audit as a


def record(sender="crm@novogene.com",uid="1",date="2026-11-06T09:00:00+09:00"):
    return {"record_id":"rec"+uid,"fields":{
        "Mail Key":mail_key("99",uid),
        "From":sender,
        "Source Account":"jiin.yoo@novogene.com",
        "Source Filter":"EXACT_FROM_CRM",
        "Received At":date,
        "Direction":"INBOUND",
    }}


class SourceAuditTests(unittest.TestCase):
    def test_valid_exact_sender(self):
        self.assertEqual(a.summarize([record(uid="1"),record(uid="2")]),2)

    def test_refuse_spoofed_sender(self):
        with self.assertRaisesRegex(SafeError,"WRONG_SENDER"):
            a.summarize([record(sender="crm@novogene.com.evil.com")])
        with self.assertRaisesRegex(SafeError,"WRONG_SENDER"):
            a.summarize([record(sender="crm@novogene.com, other@example.com")])

    def test_refuse_duplicate_mail_key(self):
        with self.assertRaisesRegex(SafeError,"DUPLICATE"):
            a.summarize([record(),record()])

    def test_refuse_wrong_source_and_date(self):
        x=record();x["fields"]["Source Account"]="different@example.com"
        with self.assertRaisesRegex(SafeError,"ACCOUNT_MISMATCH"):
            a.summarize([x])
        with self.assertRaisesRegex(SafeError,"BEFORE_2026"):
            a.summarize([record(date="2025-12-31T23:00:00+09:00")])

if __name__=="__main__":
    unittest.main()
