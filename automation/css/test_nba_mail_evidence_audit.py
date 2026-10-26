import unittest
from nba_mail_evidence_audit import summarize, exact_header_reply_links, followup_after_verified_reply

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
        duplicated = rows + [dict(rows[1], ingest_key="duplicate-copy")]
        summary = exact_header_reply_links(duplicated)
        self.assertEqual(summary["strict_reply_links"],1)
        self.assertEqual(summary["duplicate_incoming_rows"],1)
        self.assertEqual(summary["review_required"],1)

    def test_dashboard_does_not_overwrite_manual_decision_column(self):
        from pathlib import Path
        src = Path("nba_mail_evidence_audit.py").read_text(encoding="utf-8")
        self.assertIn("A{target}:I{target}", src)
        self.assertIn("K{target}", src)
        self.assertNotIn("J{target}", src)

    def test_followup_requires_later_outbound_and_dedups_message_id(self):
        rows=[
            {"message_id":"<r>","from_email":"client@example.org","recipient_to":"taehoon.kim@novogene.com","received_at":"2026-10-26T10:00:00+09:00","direction":"INBOUND"},
            {"message_id":"<r>","from_email":"client@example.org","recipient_to":"taehoon.kim@novogene.com","received_at":"2026-10-26T10:00:00+09:00","direction":"INBOUND"},
            {"message_id":"<old>","from_email":"taehoon.kim@novogene.com","recipient_to":"client@example.org","received_at":"2026-10-26T09:00:00+09:00","direction":"OUTBOUND"},
        ]
        self.assertEqual(followup_after_verified_reply(rows,["<r>"])["later_outbound_not_found"],1)
        rows.append({"message_id":"<later>","from_email":"taehoon.kim@novogene.com","recipient_to":"client@example.org","received_at":"2026-10-26T11:00:00+09:00","direction":"OUTBOUND"})
        self.assertEqual(followup_after_verified_reply(rows,["<r>"])["later_outbound_confirmed"],1)

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
