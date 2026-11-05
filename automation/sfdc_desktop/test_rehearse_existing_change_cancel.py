"""Synthetic fake-UI tests for no-Save, immediate-Cancel fill-only rehearsal."""
import unittest
from unittest.mock import patch

from rehearse_existing_change_cancel import (
    gate, replay, rehearsal_field, locate_exact_editor_field,
)

SF = "006000000000000AAA"
ACCOUNT = "001000000000000AAA"
CONTACT = "003000000000000AAA"
BUSINESS = "Opp-2099-01-01-222222"


def request():
    return {
        "request_uid": "REQ-syntheticfill-001",
        "mode": "EXISTING_OPPORTUNITY_FILL_ONLY",
        "reviewed_current_deal_values": True,
        "fill_only_pilot_approved": True,
        "approved_fill_only_request_uid": "REQ-syntheticfill-001",
        "target_opportunity_record_id": SF,
        "business_opportunity_id": BUSINESS,
        "expected_account_record_id": ACCOUNT,
        "expected_contact_record_id": CONTACT,
        "expected_before_values": {"Opportunity Name": "Old Deal"},
        "changes": {"Opportunity Name": "New Deal"},
        "save_allowed": False,
    }


def bridge():
    return {
        "version": "live-related-quote-report-bridge-v1",
        "status": "VERIFIED_BY_LIVE_QUOTATION_REPORT",
        "identity_verified": True,
        "opportunity_record_id": SF,
        "business_opportunity_id": BUSINESS,
        "save_allowed": False, "salesforce_save_performed": False,
    }


def lookups():
    return {
        "account_contact_field_links_verified": True,
        "salesforce_save_allowed": False,
        "salesforce_save_performed": False,
        "opportunity_record_id": SF,
        "account_record_id": ACCOUNT,
        "contact_record_id": CONTACT,
    }


def ledger():
    return {"version": "sfdc-local-operation-ledger-v1", "entries": []}


class FakeInput:
    def __init__(self, page, value="Old Deal", change_on_fill=False, raise_on_fill=False):
        self.page = page
        self.value = value
        self.fills = []
        self.change_on_fill = change_on_fill
        self.raise_on_fill = raise_on_fill

    def count(self):
        return 1

    def is_visible(self):
        return True

    def is_enabled(self):
        return True

    def input_value(self):
        return self.value

    def fill(self, value, timeout=None):
        self.fills.append(value)
        if self.raise_on_fill:
            raise RuntimeError("Synthetic UI fill failure")
        self.value = value + "auto-format" if self.change_on_fill else value


class FakeButton:
    def __init__(self, page, label):
        self.page = page
        self.label = label

    def count(self):
        if self.label == "Save":
            return int(self.page.editor_open)
        if self.label == "Cancel":
            return int(self.page.editor_open)
        return 1

    def wait_for(self, state=None, timeout=None):
        if self.label == "Cancel" and not self.page.editor_open:
            raise RuntimeError("Cancel not visible in synthetic editor")

    def click(self, timeout=None):
        if self.label == "Save":
            self.page.save_clicks += 1
            raise AssertionError("Save must never be clicked")
        if self.label == "Cancel":
            self.page.cancel_clicks += 1
            self.page.editor_open = False
        else:
            self.page.editor_open = True


class FakePage:
    def __init__(self, old="Old Deal", **kwargs):
        self.editor_open = False
        self.save_clicks = 0
        self.cancel_clicks = 0
        self.field = FakeInput(self, old, **kwargs)

    url = "https://novogene.lightning.force.com/lightning/r/Opportunity/" + SF + "/view"

    def evaluate(self, js):
        return []

    def get_by_role(self, role, name=None, exact=False):
        if role == "tab" and name == "Details":
            return FakeDetailsTab()
        if role == "button":
            return FakeButton(self, name)
        if role == "textbox" and name == "Opportunity Name":
            return self.field
        raise AssertionError("Unexpected control requested")

    def wait_for_timeout(self, delay):
        pass


class FakeDetailsTab:
    def count(self):
        return 1

    def get_attribute(self, key):
        if key == "aria-selected":
            return "true"
        return None


class FakeBrowser:
    def __init__(self, page):
        self.contexts = [type("Context", (), {"pages": [page]})()]


class ReviewSafety(unittest.TestCase):
    def test_unreviewed_template_returns_hold_without_browser(self):
        data = request()
        data["reviewed_current_deal_values"] = False
        data["changes"] = {}
        data["expected_before_values"] = {}
        r = replay(None, data, None, None, None)
        self.assertEqual(r["status"], "HOLD_REVIEW_OR_PILOT_APPROVAL_REQUIRED")
        self.assertFalse(r["save_allowed"])

    def test_no_explicit_fill_approval_returns_hold(self):
        data = request()
        data["fill_only_pilot_approved"] = False
        self.assertEqual(gate(data)[0], "HOLD_REVIEW_OR_PILOT_APPROVAL_REQUIRED")

    def test_pilot_approval_uid_mismatch_rejected(self):
        data = request()
        data["approved_fill_only_request_uid"] = "REQ-other-id"
        self.assertEqual(gate(data)[0], "HOLD_FILL_ONLY_REQUEST_ID_MISMATCH")

    def test_valid_reviewed_request_requires_real_browser(self):
        decision, evidence = gate(request(), bridge(), lookups(), ledger())
        self.assertEqual(decision, "READY_FOR_CANCEL_ONLY_REHEARSAL")
        self.assertFalse(evidence["save_allowed"])

    def test_duplicate_operation_uid_rejected(self):
        data = ledger()
        preflight = gate(request(), bridge(), lookups(), ledger())[1]
        data["entries"] = [{
            "request_uid": request()["request_uid"],
            "operation_fingerprint": preflight["operation_fingerprint"],
            "change_intent_fingerprint": preflight["change_intent_fingerprint"],
            "state": "WRITE_OUTCOME_UNKNOWN",
        }]
        with self.assertRaises(ValueError):
            gate(request(), bridge(), lookups(), data)

    def test_missing_operation_ledger_rejected(self):
        with self.assertRaises(ValueError):
            gate(request(), bridge(), lookups(), None)


class CancelOnlyFieldTests(unittest.TestCase):
    def test_name_new_value_is_filled_then_cancelled(self):
        page = FakePage()
        r = rehearsal_field(page, "Opportunity Name", "Old Deal", "New Deal")
        self.assertEqual(r["status"], "CANCEL_ONLY_REHEARSAL_FIELD_MATCH")
        self.assertEqual(page.field.fills, ["New Deal"])
        self.assertTrue(r["cancel_clicked"])
        self.assertEqual(page.cancel_clicks, 1)
        self.assertEqual(page.save_clicks, 0)
        self.assertFalse(page.editor_open)

    def test_stale_name_value_is_hold_and_cancelled_without_fill(self):
        page = FakePage(old="Changed by another user")
        r = rehearsal_field(page, "Opportunity Name", "Old Deal", "New Deal")
        self.assertEqual(r["status"], "HOLD_STALE_BEFORE_VALUE")
        self.assertEqual(page.field.fills, [])
        self.assertTrue(r["cancel_clicked"])
        self.assertEqual(page.save_clicks, 0)

    def test_autoformatted_new_value_is_hold_cancelled(self):
        page = FakePage(change_on_fill=True)
        r = rehearsal_field(page, "Opportunity Name", "Old Deal", "New Deal")
        self.assertEqual(r["status"], "HOLD_FIELD_AFTER_FILL_DIFFERS")
        self.assertEqual(page.cancel_clicks, 1)
        self.assertEqual(page.save_clicks, 0)

    def test_fill_error_still_cancels(self):
        page = FakePage(raise_on_fill=True)
        with self.assertRaises(RuntimeError):
            rehearsal_field(page, "Opportunity Name", "Old Deal", "New Deal")
        self.assertEqual(page.cancel_clicks, 1)
        self.assertEqual(page.save_clicks, 0)

    def test_wrong_field_type_rejected(self):
        page = FakePage()
        with self.assertRaises(ValueError):
            rehearsal_field(page, "Stage", "Old Deal", "New Deal")
        self.assertEqual(page.cancel_clicks, 0)
        self.assertEqual(page.save_clicks, 0)

    def test_amount_field_uses_exact_label_locator(self):
        page = FakePage(old="100")
        with patch("rehearse_existing_change_cancel.locate_field", return_value=page.field) as loc:
            r = rehearsal_field(page, "Amount", "100", "200")
        loc.assert_called_once_with(page, "Amount")
        self.assertTrue(r["after_equal"])
        self.assertTrue(r["cancel_clicked"])
        self.assertEqual(page.save_clicks, 0)

    def test_close_date_uses_exact_label_locator(self):
        page = FakePage(old="11/02/2099")
        with patch("rehearse_existing_change_cancel.locate_field", return_value=page.field):
            r = rehearsal_field(page, "Close Date", "11/02/2099", "2099-11-03")
        self.assertTrue(r["cancel_clicked"])
        self.assertEqual(page.save_clicks, 0)


class RestorationGateTests(unittest.TestCase):
    def test_after_cancel_original_restored_allows_rehearsal_result(self):
        page = FakePage()
        with (patch("rehearse_existing_change_cancel.validate_preflight", return_value=True),
              patch("rehearse_existing_change_cancel.check_lookup_ids", return_value=True),
              patch("rehearse_existing_change_cancel.current_value", return_value="Old Deal") as reread):
            result = replay(FakeBrowser(page), request(), bridge(), lookups(), ledger())
        self.assertEqual(result["status"], "REHEARSAL_CANCELLED_ALL_FIELDS")
        self.assertFalse(result["save_allowed"])
        self.assertEqual(page.save_clicks, 0)
        self.assertTrue(result["per_field_result"][0]["before_value_restored_after_cancel"])
        reread.assert_called_once_with(page, "Opportunity Name")

    def test_after_cancel_not_restored_forces_hold(self):
        page = FakePage()
        with (patch("rehearse_existing_change_cancel.validate_preflight", return_value=True),
              patch("rehearse_existing_change_cancel.check_lookup_ids", return_value=True),
              patch("rehearse_existing_change_cancel.current_value", return_value="New Deal")):
            result = replay(FakeBrowser(page), request(), bridge(), lookups(), ledger())
        self.assertEqual(result["status"], "HOLD_FIELD_REHEARSAL")
        self.assertEqual(result["per_field_result"][0]["status"], "HOLD_CANCEL_DID_NOT_RESTORE_BEFORE_VALUE")
        self.assertEqual(page.save_clicks, 0)
        self.assertFalse(result["actual_salesforce_changes_committed"])


if __name__ == "__main__":
    unittest.main()
