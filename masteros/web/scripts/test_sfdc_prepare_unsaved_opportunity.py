"""Synthetic pure tests: never open a real Salesforce tab or Save."""
import unittest
from sfdc_prepare_unsaved_opportunity import reuse_decision

WANTED={
  "Opportunity Name":"Korea-Synthetic-PMP-4-5Gb",
  "Close Date":"2026-12-18",
  "Progress Description":"New request: 4 synthetic samples expected; PO unconfirmed."
}

class UnsavedOpportunityReuseTests(unittest.TestCase):
    def test_no_existing_modal_allows_a_single_new_tab(self):
        self.assertEqual(reuse_decision([],WANTED),"OPEN_NEW")

    def test_exact_matching_unsaved_modal_is_reused(self):
        self.assertEqual(reuse_decision([WANTED.copy()],WANTED),
                         "REUSE_UNMODIFIED_EXISTING_FORM")

    def test_multiple_modals_do_not_create_a_fourth_tab(self):
        self.assertEqual(reuse_decision([WANTED.copy()]*3,WANTED),
                         "HOLD_MULTIPLE_UNSAVED_OPPORTUNITY_MODALS")

    def test_existing_customer_edits_cannot_be_overwritten(self):
        for k in WANTED:
            changed=WANTED.copy()
            changed[k]+="modified"
            self.assertEqual(reuse_decision([changed],WANTED),
                             "HOLD_EXISTING_UNSAVED_FIELDS_DIFFER")

    def test_incomplete_existing_dialog_is_held(self):
        self.assertEqual(reuse_decision([{"Opportunity Name":"fake"}],WANTED),
                         "HOLD_EXISTING_UNSAVED_FIELDS_NOT_VERIFIED")
        self.assertEqual(reuse_decision([None],WANTED),
                         "HOLD_EXISTING_UNSAVED_FIELDS_NOT_VERIFIED")

if __name__=="__main__":
    unittest.main()
