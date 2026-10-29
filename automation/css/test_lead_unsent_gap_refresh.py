"""Offline guardrails for new SFDC report Lead / outgoing QQ audit."""
import datetime as dt
import unittest

from lead_unsent_gap_refresh import build_rows, KST


class LeadGapTests(unittest.TestCase):
    def setUp(self):
        header=[""]*23
        for pos,name in [(0,"Created Date"),(1,"First Name"),(2,"Last Name"),
                         (4,"Company / Account"),(6,"Lead Status"),
                         (12,"Description"),(14,"Email"),(22,"SFDC Lead ID")]:
            header[pos]=name
        self.raw=[header]
        def source(id,email):
            row=[""]*23
            row[0]="10/26/2026"
            row[1]="Fresh";row[2]="Lead";row[4]="University";row[6]="New"
            row[12]="Please quote RNA-Seq";row[14]=email;row[22]=id
            return row
        self.raw.extend([source("Lead-old","old@example.com"),
                         source("Lead-new","new@example.com")])
        h=[""]*30;h[0]="Lead ID"
        r=[""]*30
        r[0]="Lead-old";r[3]="old@example.com";r[4]="University"
        r[5]="2026-10-26";r[6]="New";r[17]="DESCRIPTION_PRESENT"
        r[18]="Please quote RNA-Seq";r[25]="NO_SENT_EVIDENCE"
        self.legacy=[h,r]
        p=[""]*15;p[0]="Lead ID"
        q=[""]*15;q[0]="Lead-old";q[1]="P1";q[4]="University"
        q[6]="old@example.com";q[8]="Please quote RNA-Seq"
        self.priority=[p,q]
        self.mail=[["received_at","from_email","recipient_to"],
                   ["2026-10-18T09:00:00+09:00","other@example.com","none@example.com"],
                   ["2026-10-29T17:54:52+09:00","taehoon.kim@novogene.com","new@example.com"]]
        self.flags=[["direction"],["INBOUND"],["OUTBOUND"]]
        self.now=dt.datetime(2026,10,29,19,0,tzinfo=KST)

    def run_build(self):
        return build_rows(self.raw,self.legacy,self.priority,
                          self.mail,self.flags,self.now)

    def test_exact_new_recipient_excluded_if_sent(self):
        audit,focus,full,counts=self.run_build()
        self.assertEqual(audit[0][6],"SENT_CONFIRMED")
        self.assertEqual(counts["new_sent"],1)
        self.assertEqual(counts["new_no_sent"],0)
        self.assertEqual(counts["priority"],1)
        self.assertEqual(counts["total_no_sent"],1)

    def test_new_unmailed_is_in_both_review_queues(self):
        self.mail[-1][2]="unrelated@example.com"
        audit,focus,full,counts=self.run_build()
        self.assertEqual(audit[0][6],"NO_SENT_EVIDENCE")
        self.assertEqual(counts["new_no_sent"],1)
        self.assertEqual(counts["priority"],2)
        self.assertEqual(counts["total_no_sent"],2)
        self.assertIn("Lead-new",{r[0] for r in full})

    def test_outbound_only_and_sender_restriction(self):
        self.mail[-1][1]="untrusted@example.com"
        audit,_,_,_=self.run_build()
        self.assertEqual(audit[0][6],"NO_SENT_EVIDENCE")
        self.mail[-1][1]="taehoon.kim@novogene.com"
        self.flags[-1][0]="INBOUND"
        audit,_,_,_=self.run_build()
        self.assertEqual(audit[0][6],"NO_SENT_EVIDENCE")

    def test_stale_mail_fails_without_writing(self):
        self.now=dt.datetime(2026,11,3,19,0,tzinfo=KST)
        with self.assertRaisesRegex(ValueError,"stale"):
            self.run_build()

    def test_no_sent_not_asserted_when_history_uncovered(self):
        self.mail=self.mail[1:]
        self.mail.insert(0,["received_at","from_email","recipient_to"])
        self.mail=self.mail[:1]+self.mail[2:]  # only latest 29th available
        self.flags=[["direction"],["OUTBOUND"]]
        self.mail[1][2]="nobody@example.com"
        audit,_,_,_=self.run_build()
        self.assertEqual(audit[0][6],"SOURCE_COVERAGE_UNVERIFIED")


if __name__=="__main__":
    unittest.main()
