"""SFDC operator contract changeset guard. Synthetic/static only. No CRM access.

This permanently fails GitHub Actions when an engineer silently reintroduces
global Opportunity List/New, default Quote Draft, or bypasses Contact/Related
native origin protections. Does not replace live user/source validations.
"""
from __future__ import annotations
import ast
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def source(relative):
    return (ROOT/relative).read_text(encoding="utf-8")


class ExistingSFDCUserRulesContractTests(unittest.TestCase):
    def test_all_twenty_prior_operator_rules_remain_documented(self):
        body=source("automation/sfdc_desktop/SFDC_OPERATOR_RULES.md")
        found=set(re.findall(r"\bSFDC-(\d{3})\b",body))
        self.assertTrue({f"{i:03d}" for i in range(1,21)} <= found)
        for required in (
            "CONTACT_FIRST_ENTRY_REQUIRED", "QUOTE_MUST_START_FROM_OPPO_RELATED",
            "NATIVE_SFDC", "Quote Issued", "VAT", "AliCloud",
        ):
            self.assertIn(required,body)

    def test_no_global_opportunity_list_new_remains_in_active_intake(self):
        body=source("masteros/web/scripts/sfdc_prepare_unsaved_opportunity.py")
        self.assertNotIn('"/lightning/o/Opportunity/list"',body)
        self.assertNotIn("await new.click(",body)
        self.assertIn("Contact.AccountId",body)
        self.assertIn("CONTACT_FIRST_NEW_OPPORTUNITY_ACTION_NOT_YET_VERIFIED",body)

    def test_native_save_rejects_non_contact_and_non_related_origins(self):
        body=source("masteros/web/scripts/sfdc_native_approved_save.py")
        self.assertIn("native_origin_route_violation(",body)
        engine=source("automation/sfdc_desktop/native_save_transaction.py")
        self.assertIn('candidate.get("entry_route") != "CONTACT_RELATED_OPPORTUNITY"',engine)
        self.assertIn('candidate.get("quotation_route") != "OPPORTUNITY_RELATED_QUOTATION"',engine)
        self.assertIn("QUOTE_MUST_START_FROM_OPPO_RELATED",engine)

    def test_legacy_direct_write_entry_remains_disabled(self):
        body=source("masteros/web/scripts/sfdc_paired_native_create.py")
        mod=ast.parse(body)
        func=next(x for x in mod.body if isinstance(x,ast.FunctionDef)
                  and x.name=="execute_pair")
        self.assertIsInstance(func.body[0],ast.Raise)
        self.assertIn("LEGACY_NON_CONTACT_SAVE_DISABLED",body)

    def test_quote_issued_is_new_progress_default_and_approval_queue_requirement(self):
        draft=source("masteros/web/lib/sfdc-report-quote-draft.mjs")
        queue=source("masteros/web/lib/sfdc-pair-request-queue.mjs")
        self.assertIn('descriptionStatus:"Quote Issued"',draft)
        self.assertIn('status:s(draft.descriptionStatus)||"Quote Issued"',draft)
        self.assertIn('d.descriptionStatus!=="Quote Issued"',queue)
        self.assertNotIn('descriptionStatus:"Quote Draft"',draft)
        self.assertNotIn('["Quote Draft","Prospective"].includes',queue)
        self.assertNotIn('errors.push("QUOTE_ISSUED_EVIDENCE_REQUIRED")',draft)

    def test_ui_displays_issued_and_contact_first_without_false_delivery(self):
        body=source("masteros/web/app/sales/commands/pair/ReportOppoDraft.jsx")
        self.assertIn("Quote Issued",body)
        self.assertIn("실제 고객 메일 발송의 증거가 아니",body)
        review=source("masteros/web/app/sales/commands/pair/approvals/page.jsx")
        self.assertIn("기존 Contact 열기 · Account 관계 확인",review)
        self.assertNotIn("Opportunity 입력창 열고 3개 필드 채우기",review)

    def test_existing_same_name_id_and_price_guards_not_omitted(self):
        body=source("automation/sfdc_desktop/native_save_transaction.py")
        for marker in (
            "SOURCE_REFERENCE_NATIVE_ID_BINDING_MISMATCH",
            "created_id_is_distinct",
            "OPPORTUNITY_CLICK_STARTED",
            "QUOTATION_CLICK_STARTED",
            "OPPORTUNITY_SAVED",
        ):
            self.assertIn(marker,body)
        quote=source("automation/sfdc_desktop/quote_native_save_source_audit.py")
        self.assertIn("ALICLOUD_EXCLUDED_BUT_SOURCE_HAS_ALICLOUD_TYPED_PROCESS",quote)
        self.assertIn('"save_permitted":False',quote)


if __name__=="__main__":
    unittest.main()
