"""Offline strict sender and exact To/CC personal Lead evidence tests."""
import datetime as dt
import unittest
from lead_my_sent_refresh import build, parse_messages, KST


class PersonalLeadTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,10,29,20,0,tzinfo=KST)
        self.hh=["message_id","received_at","from_name","from_email","to","cc"]
        self.sh=["message_id","imap_uid","folder","uidvalidity",
                 "received_at","from_email","recipient_to","cc"]
        self.history=[self.hh,
            ["old","2026-10-20T10:00:00+09:00","","taehoon.kim@novogene.com",
             "lead0@example.com",""],
            ["other","2026-10-27T10:00:00+09:00","","other@novogene.com",
             "lead1@example.com",""],
            ["same","2026-10-29T11:00:00+09:00","","taehoon.kim@novogene.com",
             "lead2@example.com",""]]
        self.hdir=[["direction"],["SENT"],["SENT"],["SENT"]]
        self.stage=[self.sh,
            ["same","5","SENT","1","2026-10-29T11:00:00+09:00",
             "taehoon.kim@novogene.com","lead2@example.com",""],
            ["cc","6","SENT","1","2026-10-29T17:00:00+09:00",
             "taehoon.kim@novogene.com","sales@novogene.com","lead3@example.com"],
            ["inbound","7","INBOX","1","2026-10-29T18:00:00+09:00",
             "taehoon.kim@novogene.com","lead4@example.com",""]]
        self.sdir=[["direction"],["OUTBOUND"],["OUTBOUND"],["INBOUND"]]
        self.head=["Created Date","First Name","Last Name","Company / Account",
                   "Lead Status","Email","Description","Lead Owner",
                   "SFDC Lead ID","Opportunity ID"]
        self.raw=[self.head]
        for i in range(450):
            self.raw.append(["10/26/2026","Researcher",str(i),"University","New",
                             "lead"+str(i)+"@example.com",
                             "Please quote RNA-seq" if i==2 else "",
                             "Kim Taehoon","Lead-"+str(i),""])

    def evidence(self):
        return build(self.raw,self.history,self.hdir,self.stage,self.sdir,self.now)

    def test_only_personal_sender_and_exact_recipient(self):
        rows,counts,latest=self.evidence()
        ids={r[0]:r for r in rows[1:]}
        self.assertEqual(counts["SENT_BEFORE_LEAD_ONLY"],1)
        self.assertEqual(counts["SENT_AFTER_LEAD_CONFIRMED"],2)
        self.assertEqual(counts["NO_PERSONAL_OUTBOUND_EVIDENCE"],447)
        self.assertEqual(ids["Lead-0"][14],"SENT_BEFORE_LEAD_ONLY")
        self.assertEqual(ids["Lead-1"][14],"NO_PERSONAL_OUTBOUND_EVIDENCE")
        self.assertEqual(ids["Lead-2"][9],1)  # duplicate Message-ID deduplicated
        self.assertEqual(ids["Lead-3"][16],"CC")
        self.assertEqual(ids["Lead-4"][14],"NO_PERSONAL_OUTBOUND_EVIDENCE")
        self.assertEqual(ids["Lead-2"][6],"PRESENT")
        self.assertEqual(ids["Lead-3"][6],"MISSING")

    def test_stale_mail_source_blocks_no_sent(self):
        with self.assertRaisesRegex(ValueError,"stale"):
            build(self.raw,self.history,self.hdir,self.stage,self.sdir,
                  dt.datetime(2026,11,4,20,0,tzinfo=KST))

    def test_unaligned_qq_columns_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"row-aligned"):
            build(self.raw,self.history,self.hdir,self.stage,self.sdir[:-1],self.now)

    def test_wrong_lead_email_fails_closed(self):
        self.raw[1][5]=""
        with self.assertRaisesRegex(ValueError,"Missing Lead"):
            self.evidence()

    def test_converted_not_queued_for_first_contact(self):
        self.raw[1][4]="Qualified"
        rows,_,_=self.evidence()
        lead=next(x for x in rows if x[0]=="Lead-0")
        self.assertEqual(lead[19],"MANAGE_OPPORTUNITY")


if __name__=="__main__":
    unittest.main()
