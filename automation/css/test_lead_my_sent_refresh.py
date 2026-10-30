"""Offline strict sender and exact To/CC personal Lead evidence tests."""
import datetime as dt
import unittest
from pathlib import Path
from lead_my_sent_refresh import build, parse_messages, verified_lead_stage, KST


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

    def test_recent_preserved_report_is_valid_not_reprocessed(self):
        row=["Leads","2026-10-29 12:00:05 KST",
             "2026-10-29 15:25:40 KST","493","493","0","0",
             "a"*64,"PRESERVED_NO_NEW_REPORT"]
        self.assertTrue(verified_lead_stage(row,self.now))
        row[7]=""
        self.assertFalse(verified_lead_stage(row,self.now))
        row[7]="a"*64
        row[1]="2026-10-20 12:00:05 KST"
        self.assertFalse(verified_lead_stage(row,self.now))

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

    def test_weekday_fallback_applies_only_strict_personal_evidence(self):
        # Code inspection: this backup cannot send email or update SFDC.
        root=Path(__file__).resolve().parents[2]
        workflow=(root/".github"/"workflows"/"lead-unsent-gap-refresh.yml").read_text()
        source=(root/"automation"/"css"/"lead_my_sent_refresh.py").read_text()
        self.assertIn("cron: '10 1 * * 1-5'",workflow)
        self.assertIn("github.event_name == 'schedule'",workflow)
        self.assertIn("Lead source report is stale; refuse to certify no sent",source)
        self.assertIn("QQ staging coverage stale; refuse to certify no sent",source)
        self.assertIn("SENDER = \"taehoon.kim@novogene.com\"",source)
        self.assertIn("if os.getenv(\"LEAD_PERSONAL_APPLY\",\"false\").lower()!=\"true\"",source)
        self.assertIn("range=\"'\"+sheet+\"'!A1:T\"",source)
        self.assertNotIn("mail.send(",source)

    def test_independent_backup_cannot_run_workflow_run_only_nba_steps(self):
        root=Path(__file__).resolve().parents[2]
        workflow=(root/".github"/"workflows"/"lead-unsent-gap-refresh.yml").read_text()
        nba_steps=["Refresh verified QQ reply evidence after successful Report",
                   "Refresh NBA Pool from just-verified personal sent evidence",
                   "Append stable checkbox identities after NBA readback"]
        for label in nba_steps:
            body=workflow.split("      - name: "+label,1)[1].split("      - name:",1)[0]
            self.assertIn("if: github.event_name == 'workflow_run'",body)

    def test_converted_not_queued_for_first_contact(self):
        self.raw[1][4]="Qualified"
        rows,_,_=self.evidence()
        lead=next(x for x in rows if x[0]=="Lead-0")
        self.assertEqual(lead[19],"MANAGE_OPPORTUNITY")


if __name__=="__main__":
    unittest.main()
