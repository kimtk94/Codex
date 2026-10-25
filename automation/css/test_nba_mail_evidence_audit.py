import unittest
from nba_mail_evidence_audit import summarize

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
        self.assertEqual(out["ambiguous_reply_evidence"],2)
        self.assertEqual(out["historical_over_30d"],1)
        self.assertEqual(out["nba_actionable"],1)

if __name__=="__main__":
    unittest.main()
