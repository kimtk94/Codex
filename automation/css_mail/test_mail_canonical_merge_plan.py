import unittest
from mail_canonical_merge_plan import plan

LEGACY=["uid","message_id","received_at","from_name","from_email","to","cc","reply_to","subject","attachments"]
STAGING=["ingest_key","message_id","imap_uid","folder","uidvalidity","received_at","from_email","recipient_to","cc","subject"]

class MigrationPlanTests(unittest.TestCase):
    def test_exact_match_preserves_both_source_records(self):
        l=[LEGACY,["17","<abc@a>","2026-10-28T01:00:00+00:00","Sender","css@novogene-amea.com","me@example.com","","","Invoice","TAX INVOICE 1.pdf"]]
        s=[STAGING,["INBOX|123|17","<abc@a>","17","INBOX","123","2026-10-28T01:00:00+00:00","css@novogene-amea.com","me@example.com","","Invoice"]]
        result=plan(l,s)
        self.assertEqual(result["strict_same_message_candidates"],1)
        self.assertEqual(result["legacy_with_attachment"],1)
        self.assertFalse(result["automatic_deletion_allowed"])
    def test_same_message_id_different_recipient_not_equal(self):
        l=[LEGACY,["17","<abc@a>","2026-10-28T01:00:00+00:00","","sender@a","someone@a","","","Test","file.pdf"]]
        s=[STAGING,["INBOX|123|17","<abc@a>","17","INBOX","123","2026-10-28T01:00:00+00:00","sender@a","me@a","","Test"]]
        self.assertEqual(plan(l,s)["strict_same_message_candidates"],0)
    def test_duplicate_uid_checkpoint_rejected(self):
        r=["INBOX|123|17","<x@a>","17","INBOX","123","2026-10-28T01:00:00+00:00","sender@a","me@a","","Test"]
        with self.assertRaisesRegex(ValueError,"DUPLICATE_STAGING_KEY"):
            plan([LEGACY],[STAGING,r,r])
if __name__=="__main__":unittest.main()
