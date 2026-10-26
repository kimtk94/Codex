import unittest
from nba_mail_evidence_audit import summarize, exact_header_reply_links

class MailEvidenceTests(unittest.TestCase):
    def test_ambiguous_review_notes_not_confirmed(self):
        rows=[
            {"Thread UID":"inbox:1","Aging Days":"7","Effective Queue":"REVIEW_2D","Reply Evidence":"후속조치 검토 (확정 아님)"},
            {"Thread UID":"inbox:2","Aging Days":"8","Effective Queue":"REVIEW_2D","Reply Evidence":"PC_REPLIED"},
            {"Thread UID":"inbox:3","Aging Days":"45","Effective Queue":"OVERDUE_7D","Reply Evidence":"30일 초과: Action Center 대상 제외"},
        ]
        out=summarize(rows)
        self.assertEqual(out["threads"],3)
        self.assertEqual(out["explicit_reply_evidence"],1)
        self.assertEqual(out["nonproof_status_text"],2)
        self.assertEqual(out["historical_over_30d"],1)
        self.assertEqual(out["nba_actionable"],1)

    def test_exact_header_link_requires_original_recipient(self):
        rows=[
            {"folder":"Sent","message_id":"<out-1>","from_email":"taehoon.kim@novogene.com","recipient_to":"client@example.org"},
            {"folder":"INBOX","message_id":"<in-1>","from_email":"client@example.org","recipient_to":"taehoon.kim@novogene.com","in_reply_to":"<out-1>"},
            {"folder":"INBOX","message_id":"<in-2>","from_email":"other@example.org","recipient_to":"taehoon.kim@novogene.com","in_reply_to":"<out-1>"},
        ]
        self.assertEqual(exact_header_reply_links(rows)["strict_reply_links"],1)

    def test_sent_and_closed_are_not_reply_proof(self):
        rows=[
            {"Thread UID":"inbox:4","Reply Evidence":"SENT_CONFIRMED"},
            {"Thread UID":"inbox:5","Reviewer Mail Action":"DONE"},
            {"Thread UID":"inbox:6","Reply Evidence":"REPLIED"},
        ]
        result=summarize(rows)
        self.assertEqual(result["explicit_reply_evidence"],1)
        self.assertEqual(result["reviewer_closed_not_reply_proof"],1)
        self.assertEqual(result["nonproof_status_text"],1)

if __name__=="__main__":
    unittest.main()
