#!/usr/bin/env python3
"""No identity inferred from name, generic CSS sender, or quoted body."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo

import mail_identity_2026 as m
from qq_mail_ingest import SafeError


KST = ZoneInfo("Asia/Seoul")
NOW = dt.datetime(2026, 11, 5, 21, tzinfo=KST)


def fixture_refs():
    return m.build_index({
        "contacts": [
            {"Email": "person@example.edu", "First Name": "홍길동",
             "Last Name": "", "Account Name": "고려대학교"},
            {"Email": "person2@example.edu", "First Name": "김가나",
             "Last Name": "", "Account Name": "연세대학교"},
            {"Email": "shared@example.edu", "First Name": "가나",
             "Last Name": "", "Account Name": "고려대학교"},
            {"Email": "shared@example.edu", "First Name": "다라",
             "Last Name": "", "Account Name": "서울대학교"},
        ],
        "leads": [
            {"Email": "person@example.edu", "Contact Name": "홍길동",
             "Contact ID": "003123", "Account ID": "001123",
             "Company / Account": "고려대학교"},
            {"Email": "lead@example.edu", "Contact Name": "",
             "Company / Account": "기타대학교"},
        ],
        "quotes": [
            {"AMEA Quotation ID": "AMEA2026042239", "Opportunity ID": "006AAA",
             "Account Name": "고려대학교"}
        ],
        "projects": [
            {"project_id": "AMEA2026042239", "h_project_numbers": "H209SC26065705",
             "institution": "고려대학교", "customer_name": "홍길동"},
            {"project_id": "AMEA2026042240", "h_project_numbers": "H209SC26065706",
             "institution": "연세대학교", "customer_name": "김가나"},
        ],
    })


def mail(subject, sender="person@example.edu", direction="INBOUND", **kw):
    f = {
        "Mail Key": "a"*64, "Direction": direction, "Subject": subject,
        "Received At": "2026-11-03T11:00:00+09:00",
        "Captured UTC": "2026-11-05T01:00:00Z",
        "From": sender, "To": "taehoon.kim@novogene.com",
        "CC": "", "In Reply To": "",
        "Body Excerpt": "",
        "AMEA": "", "H Project": "",
    }
    f.update(kw)
    return f


class MailIdentityTests(unittest.TestCase):
    def setUp(self):
        self.index = fixture_refs()

    def test_customer_email_contact_account_project_exact(self):
        row = m.decorate(mail("Project AMEA2026042239"), self.index, NOW)
        self.assertEqual(row["Contact Link"], "EMAIL_EXACT_CONTACT")
        self.assertEqual(row["Project Link"], "PROJECT_ID_EXACT")
        self.assertEqual(row["Relationship Status"], "LINKED")
        self.assertEqual(row["Account ID"], "001123")
        self.assertEqual(row["Contact ID"], "003123")
        self.assertEqual(row["Opportunity ID"], "006AAA")
        self.assertEqual(row["Project ID"], "AMEA2026042239")

    def test_css_sender_project_match_not_contact_exact(self):
        row = m.decorate(mail("Sample QC H209SC26065705",
                             sender="css@novogene-amea.com"), self.index, NOW)
        self.assertEqual(row["Project Link"], "PROJECT_ID_EXACT")
        self.assertNotEqual(row["Contact Link"], "EMAIL_EXACT_CONTACT")
        self.assertEqual(row["Contact ID"], "")
        self.assertEqual(row["Account"], "고려대학교")
        self.assertEqual(row["Review State"], "OK")

    def test_h_project_subject_exact(self):
        row = m.decorate(mail("Lab QC H209SC26065706", sender="person2@example.edu"),
                         self.index, NOW)
        self.assertEqual(row["Project ID"], "AMEA2026042240")
        self.assertEqual(row["Relationship Status"], "LINKED")

    def test_same_name_not_used_to_infer_identity(self):
        row = m.decorate(mail("홍길동 sequencing", sender="unknown@example.org"),
                         self.index, NOW)
        self.assertEqual(row["Contact Link"], "NOT_MATCHED")
        self.assertEqual(row["Contact ID"], "")
        self.assertEqual(row["Project ID"], "")
        self.assertEqual(row["Relationship Status"], "UNMATCHED")

    def test_ambiguous_email_blocks_contact(self):
        row = m.decorate(mail("Hello", sender="shared@example.edu"), self.index, NOW)
        self.assertEqual(row["Contact Link"], "MULTIPLE_CONTACT_CANDIDATES")
        self.assertEqual(row["Account"], "")
        self.assertEqual(row["Review State"], "REVIEW")

    def test_project_institution_conflict_requires_review(self):
        row = m.decorate(mail("H209SC26065706", sender="person@example.edu"),
                         self.index, NOW)
        self.assertEqual(row["Review State"], "REVIEW")
        self.assertIn("CONTACT_PROJECT_ACCOUNT_CONFLICT", row["Evidence"])

    def test_multiple_project_identifiers_require_review(self):
        row = m.decorate(mail("AMEA2026042239 H209SC26065706"), self.index, NOW)
        self.assertEqual(row["Project Link"], "MULTIPLE_PROJECTS_REVIEW")
        self.assertEqual(row["Project ID"], "")
        self.assertEqual(row["Review State"], "REVIEW")

    def test_outbound_uses_to_not_sender(self):
        row = m.decorate(mail("Re: sequencing", sender="taehoon.kim@novogene.com",
                              direction="OUTBOUND", **{"To": "person@example.edu"}),
                         self.index, NOW)
        self.assertEqual(row["Contact Link"], "EMAIL_EXACT_CONTACT")

    def test_2025_mail_excluded_and_no_import_date_confusion(self):
        old = mail("Sample QC AMEA2026042239",
                   **{"Received At": "2025-12-31T23:59:59+09:00"})
        self.assertIsNone(m.decorate(old, self.index, NOW))
        backfilled = mail("Sample QC AMEA2026042239",
                          **{"Received At": "2026-01-02T09:00:00+09:00",
                             "Captured UTC": "2026-11-05T01:00:00Z"})
        self.assertEqual(m.decorate(backfilled, self.index, NOW)["Feed Lane"], "HISTORY_2026")

    def test_lead_only_not_contact_verified(self):
        row = m.decorate(mail("Question", sender="lead@example.edu"), self.index, NOW)
        self.assertEqual(row["Contact Link"], "LEAD_EMAIL_CANDIDATE")
        self.assertEqual(row["Contact ID"], "")
        self.assertEqual(row["Review State"], "REVIEW")

    def test_feishu_rich_text_input(self):
        row = mail("AMEA2026042239")
        rich = {k: [{"text": v}] for k,v in row.items()}
        result = m.decorate(rich, self.index, NOW)
        self.assertEqual(result["Project ID"], "AMEA2026042239")

    def test_field_changes_only_when_needed(self):
        entry = {"Mail Key": "a"*64, "Project ID": "AMEA2026042239",
                 "Last Sync KST": "older"}
        self.assertTrue(m.same({"Mail Key": [{"text":"a"*64}],
                                "Project ID": [{"text":"AMEA2026042239"}]}, entry))
        self.assertFalse(m.same({"Mail Key": "a"*64}, entry))


if __name__ == "__main__":
    unittest.main()
