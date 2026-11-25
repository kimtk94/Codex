#!/usr/bin/env python3
"""No identity inferred from name, generic CSS sender, or quoted body."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from unittest.mock import patch

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
            {"Salesforce Record ID": "a0PAbc123456789", "AMEA Quotation ID": "QID-2026-000001",
             "Opportunity ID": "OPP-2026-000001"}
        ],
        "quote_portfolio": [
            {"Salesforce Quote ID (18)": "a0PAbc123456789AAA", "Quote QID": "QID-2026-000001",
             "Approved AMEA ID": "AMEA2026042239", "Opportunity ID": "OPP-2026-000001"}
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
        self.assertEqual(row["Opportunity ID"], "OPP-2026-000001")
        self.assertIn("EXACT_AMEA_QID_QUOTE_OBJECT_OPPORTUNITY_REFERENCE", row["Evidence"])
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

    def test_inbound_css_excluded_from_customer_unanswered_pool(self):
        row = m.decorate(mail("Contract Ready AMEA2026042239",
                              sender="css@novogene-amea.com"), self.index, NOW)
        self.assertEqual(row["Mail Role"], "CSS_AUTOMATED_NOTICE")
        self.assertEqual(row["Followup Pool"], "EXCLUDE_CSS")
        self.assertEqual(row["Primary Category"], "PROJECT")
        self.assertEqual(row["Milestone"], "CONTRACT_READY")
        self.assertEqual(row["Rule Version"], "2026-v2")
        self.assertEqual(row["Evidence Tier"], "EXACT_PROJECT_ONLY")

    def test_internal_mail_not_customer_pending(self):
        row = m.decorate(mail("Internal discussion", sender="staff@novogene.com"),
                         self.index, NOW)
        self.assertEqual(row["Mail Role"], "INTERNAL_MAIL")
        self.assertEqual(row["Followup Pool"], "EXCLUDE_INTERNAL")
        self.assertEqual(row["Primary Category"], "GENERAL")

    def test_external_inbound_unanswered_not_assumed(self):
        row = m.decorate(mail("Question about experiment",
                              sender="unknown@university.edu"), self.index, NOW)
        self.assertEqual(row["Mail Role"], "EXTERNAL_INBOUND_CANDIDATE")
        self.assertEqual(row["Followup Pool"], "THREAD_REVIEW_REQUIRED")
        self.assertEqual(row["Evidence Tier"], "NO_IDENTITY_PROOF")
        self.assertEqual(row["Contact ID"], "")

    def test_outbound_mail_not_unanswered(self):
        row = m.decorate(mail("Re: project update",
                              sender="staff@novogene.com",direction="OUTBOUND",
                              **{"To": "person@example.edu"}), self.index, NOW)
        self.assertEqual(row["Mail Role"], "OUTBOUND")
        self.assertEqual(row["Followup Pool"], "NOT_APPLICABLE")

    def test_system_report_excluded(self):
        row = m.decorate(mail("Report results (Leads)",
                              sender="report@example.org"), self.index, NOW)
        self.assertEqual(row["Mail Role"], "SYSTEM_REPORT")
        self.assertEqual(row["Followup Pool"], "EXCLUDE_SYSTEM")

    def test_exact_contact_project_evidence_tier(self):
        row = m.decorate(mail("AMEA2026042239",
                              sender="person@example.edu"), self.index, NOW)
        self.assertEqual(row["Evidence Tier"], "EXACT_CONTACT_AND_PROJECT")
        self.assertIn("Classification Tags", row)
        self.assertEqual(row["Contact Link"], "EMAIL_EXACT_CONTACT")

    def test_field_changes_only_when_needed(self):
        entry = {"Mail Key": "a"*64, "Project ID": "AMEA2026042239",
                 "Last Sync KST": "older"}
        self.assertTrue(m.same({"Mail Key": [{"text":"a"*64}],
                                "Project ID": [{"text":"AMEA2026042239"}]}, entry))
        self.assertFalse(m.same({"Mail Key": "a"*64}, entry))

class QuoteOpportunityBridgeTests(unittest.TestCase):
    def setUp(self):
        self.a = "AMEA2026042239"
        self.q = "QID-2026-000001"
        self.o = "OPP-2026-000001"
        self.x = "a0PAbc123456789"
        self.export = {"Salesforce Record ID": self.x, "AMEA Quotation ID": self.q,
                       "Opportunity ID": self.o}
        self.portfolio = {"Salesforce Quote ID (18)": self.x+"AAA", "Quote QID": self.q,
                          "Approved AMEA ID": self.a, "Opportunity ID": self.o}

    def test_qid_is_not_amea_and_requires_portfolio_bridge(self):
        refs, review = m.quote_opportunity_index([self.export], [])
        self.assertEqual(dict(refs), {})
        self.assertEqual(review, set())
        refs, review = m.quote_opportunity_index([self.export], [self.portfolio])
        self.assertEqual(refs[self.a], [{"Opportunity ID":self.o}])
        self.assertEqual(review, set())

    def test_mismatched_qid_object_case_opp_and_duplicate_export_block(self):
        for exports, portfolio in (
            ([dict(self.export, **{"AMEA Quotation ID":"QID-2026-000002"})], self.portfolio),
            ([dict(self.export, **{"Salesforce Record ID":self.x.upper()})], self.portfolio),
            ([dict(self.export, **{"Opportunity ID":"OPP-2026-000002"})], self.portfolio),
            ([self.export,self.export.copy()], self.portfolio),
            ([self.export], dict(self.portfolio, **{"Opportunity ID":""})),
        ):
            with self.subTest(case=exports[0]):
                refs, review = m.quote_opportunity_index(exports, [portfolio])
                self.assertFalse(refs[self.a])
                self.assertEqual(review,{self.a})

    def test_duplicate_qid_under_other_export_object_blocks(self):
        for other in ("a0PAbc123456780", "invalid"):
            with self.subTest(other=other):
                refs, review = m.quote_opportunity_index(
                    [self.export, dict(self.export, **{"Salesforce Record ID": other})],
                    [self.portfolio])
                self.assertFalse(refs[self.a])
                self.assertEqual(review, {self.a})

    def test_portfolio_qid_object_collision_even_without_amea(self):
        for changes in (
            {"Salesforce Quote ID (18)": "a0PAbc123456780AAA", "Approved AMEA ID": ""},
            {"Quote QID": "QID-2026-000002", "Approved AMEA ID": ""},
        ):
            with self.subTest(changes=changes):
                refs, review = m.quote_opportunity_index(
                    [self.export], [self.portfolio, dict(self.portfolio, **changes)])
                self.assertFalse(refs[self.a])
                self.assertEqual(review, {self.a})

    def test_same_quote_shared_amea_not_auto_assigned(self):
        other="AMEA2026042240"
        refs, review = m.quote_opportunity_index([self.export], [self.portfolio,
            dict(self.portfolio, **{"Approved AMEA ID":other})])
        self.assertEqual(dict(refs),{})
        self.assertEqual(review,{self.a,other})

    def test_multiple_valid_quotes_and_opportunity_conflict(self):
        x2="a0PAbc123456780"
        q2="QID-2026-000002"
        e2={"Salesforce Record ID":x2,"AMEA Quotation ID":q2,"Opportunity ID":self.o}
        p2={"Salesforce Quote ID (18)":x2+"AAA","Quote QID":q2,
            "Approved AMEA ID":self.a,"Opportunity ID":self.o}
        refs,review=m.quote_opportunity_index([self.export,e2],[self.portfolio,p2])
        self.assertEqual({r["Opportunity ID"] for r in refs[self.a]},{self.o})
        self.assertFalse(review)
        e2["Opportunity ID"]=p2["Opportunity ID"]="OPP-2026-000002"
        refs,review=m.quote_opportunity_index([self.export,e2],[self.portfolio,p2])
        idx=fixture_refs(); idx["quotes"]=refs; idx["quote_review"]=review
        row=m.decorate(mail("Project "+self.a),idx,NOW)
        self.assertEqual(row["Opportunity ID"],"")
        self.assertEqual(row["Project ID"],self.a)
        self.assertIn("MULTIPLE_QUOTE_OPPORTUNITY_CANDIDATES",row["Evidence"])

    def test_bad_quote_row_keeps_project_reference_in_review(self):
        idx=fixture_refs()
        idx["quote_review"]={self.a}
        row=m.decorate(mail("Project "+self.a),idx,NOW)
        self.assertEqual(row["Project ID"],self.a)
        self.assertEqual(row["Opportunity ID"],"")
        self.assertEqual(row["Review State"],"REVIEW")
        self.assertIn("QUOTE_PORTFOLIO_EXPORT_REFERENCE_REVIEW",row["Evidence"])


class IdentityChangePlanTests(unittest.TestCase):
    @staticmethod
    def row(key, opp="", **extra):
        return {"Mail Key": key * 64, "Opportunity ID": opp, **extra}

    @classmethod
    def existing(cls, key, opp="", **extra):
        return {"record_id": "rec" + key, "fields": cls.row(key, opp, **extra)}

    def test_full_diff_preserves_manual_fields_and_existing_only(self):
        existing = [
            self.existing("a", **{"Subject": "old", "Manual Note": "keep"}),
            self.existing("b", "OPP-OLD"),
            self.existing("c", "OPP-OLD"),
            self.existing("d", **{"Last Sync KST": "old"}),
            self.existing("e", "OPP-RETAINED"),
        ]
        desired = [
            self.row("a", "OPP-NEW", Subject="new"),
            self.row("b"),
            self.row("c", "OPP-REPLACEMENT"),
            self.row("d", **{"Last Sync KST": "new"}),
            self.row("f", "OPP-NEW"),
        ]
        summary = m.identity_change_summary(existing, desired)
        self.assertEqual(summary["existing"], 5)
        self.assertEqual(summary["desired"], 5)
        self.assertEqual(summary["creates"], 1)
        self.assertEqual(summary["updates"], 3)
        self.assertEqual(summary["unchanged"], 1)
        self.assertEqual(summary["existing_only_retained"], 1)
        self.assertEqual(summary["opportunity_added"], 1)
        self.assertEqual(summary["opportunity_removed"], 1)
        self.assertEqual(summary["opportunity_replaced"], 1)
        self.assertEqual(summary["new_rows_with_opportunity"], 1)
        self.assertEqual(summary["updates_with_other_fields"], 1)
        self.assertEqual(summary["field_changes"], {"Opportunity ID": 3, "Subject": 1})
        self.assertEqual(existing[0]["fields"]["Manual Note"], "keep")
        with self.assertRaisesRegex(SafeError, "IDENTITY_EXISTING_OPPORTUNITY_CHANGE_REVIEW"):
            m.require_safe_opportunity_changes(summary)

    def test_additive_enrichment_passes(self):
        summary = m.identity_change_summary([self.existing("a")], [self.row("a", "OPP-NEW")])
        self.assertEqual(summary["opportunity_added"], 1)
        m.require_safe_opportunity_changes(summary)

    def test_duplicate_keys_and_unowned_fields_fail(self):
        with self.assertRaisesRegex(SafeError, "IDENTITY_DUPLICATE_MAIL_KEY"):
            m.identity_change_summary([self.existing("a"), self.existing("a")], [])
        for desired in ([self.row("a"), self.row("a")],
                        [self.row("a", **{"Manual Note": "not writable"})]):
            with self.assertRaisesRegex(SafeError, "IDENTITY_DESIRED_KEY_OR_FIELD_INVALID"):
                m.identity_change_summary([], desired)

    def test_plan_reads_existing_or_absent_without_writes(self):
        with patch.object(m, "api") as write, patch.object(m, "list_all") as read:
            read.return_value = []
            self.assertEqual(m.read_identity_target("token", "/base"), (None, []))
            read.side_effect = [[{"name": m.TABLE, "table_id": "tblTest"}],
                                [self.existing("a")]]
            self.assertEqual(m.read_identity_target("token", "/base"),
                             ("tblTest", [self.existing("a")]))
            write.assert_not_called()

    def test_apply_rechecks_destructive_change_before_writing(self):
        with patch.object(m, "list_all", return_value=[self.existing("a", "OPP-OLD")]), \
                patch.object(m, "api") as write:
            with self.assertRaisesRegex(SafeError, "IDENTITY_EXISTING_OPPORTUNITY_CHANGE_REVIEW"):
                m.changes("token", "/table", [self.row("a")], 100)
            write.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class MixedCaseOpportunityRegression(unittest.TestCase):
    def test_mixed_case_reference_preserved_and_mismatch_rejected(self):
        export={"Salesforce Record ID":"a0PAbc123456789","AMEA Quotation ID":"QID-2026-000001","Opportunity ID":"Opp-2026-000001"}
        portfolio={"Salesforce Quote ID (18)":"a0PAbc123456789AAA","Quote QID":"QID-2026-000001","Approved AMEA ID":"AMEA2026042239","Opportunity ID":"Opp-2026-000001"}
        refs,review=m.quote_opportunity_index([export],[portfolio])
        self.assertEqual(refs["AMEA2026042239"],[{"Opportunity ID":"Opp-2026-000001"}])
        self.assertFalse(review)
        export["Opportunity ID"]="OPP-2026-000001"
        refs,review=m.quote_opportunity_index([export],[portfolio])
        self.assertFalse(refs)
        self.assertIn("AMEA2026042239",review)
