#!/usr/bin/env python3
"""Regression tests for privacy-safe root-cause counts and conservative candidates."""
import unittest
import datetime as dt
from zoneinfo import ZoneInfo

import mail_identity_gap_audit as audit
from mail_identity_2026 import build_index, decorate

NOW=dt.datetime(2026,11,5,21,0,tzinfo=ZoneInfo("Asia/Seoul"))


def rows():
    idx=build_index({
        "contacts":[{"Email":"someone@univ.example","First Name":"가나",
                     "Last Name":"","Account Name":"기관"}],
        "leads":[],
        "quotes":[],
        "projects":[{"project_id":"AMEA2026042239",
                     "h_project_numbers":"H209SC26065705",
                     "institution":"기관","customer_name":"가나"}],
    })
    def item(key,subject,from_addr,body="",date="2026-02-06T10:00:00+09:00",
             message_id="",in_reply_to=""):
        return {"Mail Key":key,"Subject":subject,
                "From":from_addr,"To":"sales@novogene.com",
                "Direction":"INBOUND","Received At":date,
                "Body Excerpt":body,"Message ID":message_id,
                "In Reply To":in_reply_to}
    source=[
        item("a"*64,"Sample QC AMEA2026042239","someone@univ.example",
             message_id="<known@example.org>"),
        item("b"*64,"Hello","unknown@example.org","Need help AMEA2026042239",
             in_reply_to="<known@example.org>"),
        item("c"*64,"Report results (Contacts)","internal@novogene.com"),
        item("d"*64,"2025 email","unknown@example.org",date="2025-12-31T23:00:00+09:00"),
    ]
    return idx,[{"record_id":"rec_"+str(i),"fields":s} for i,s in enumerate(source)]


class GapTests(unittest.TestCase):
    def test_counts_body_and_thread_cannot_auto_link(self):
        idx,source=rows()
        src=audit.messages(source,idx,NOW)
        self.assertEqual(len(src),3)
        metrics=audit.summarize(src,idx)
        self.assertEqual(metrics["TOTAL_2026"],3)
        self.assertEqual(metrics["STATE_UNMATCHED"],2)
        self.assertEqual(metrics["UNMATCHED_BODY_ONLY_PROJECT_CANDIDATE"],1)
        self.assertEqual(metrics["UNMATCHED_BODY_ONLY_ONE_PROJECT_CANDIDATE"],1)
        self.assertEqual(metrics["UNMATCHED_EXACT_PARENT_PROJECT_CANDIDATE"],1)
        candidate=next(r for m,r in src if m["Mail Key"]=="b"*64)
        self.assertEqual(candidate["Project ID"],"")
        self.assertEqual(candidate["Relationship Status"],"UNMATCHED")

    def test_duplicate_mail_key_fails(self):
        idx,rs=rows()
        with self.assertRaisesRegex(Exception,"AUDIT_BAD_OR_DUPLICATE_MAIL_KEY"):
            audit.messages([rs[0],rs[0]],idx,NOW)

    def test_generic_css_not_contact(self):
        idx,_=rows()
        src={"Mail Key":"1"*64,"Subject":"Sample QC AMEA2026042239",
             "From":"css@novogene-amea.com","Direction":"INBOUND",
             "Received At":"2026-11-03T10:00:00+09:00"}
        r=decorate(src,idx,NOW)
        self.assertEqual(r["Project Link"],"PROJECT_ID_EXACT")
        self.assertNotEqual(r["Contact Link"],"EMAIL_EXACT_CONTACT")


if __name__=="__main__":
    unittest.main()
