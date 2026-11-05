"""Offline safety contracts for existing Opportunity UI audit. Synthetic identifiers."""
import unittest
from copy import deepcopy

from audit_existing_opportunity_no_save import (
    validate_preflight, check_lookup_controls, SFDC_ROUTE,
)

SF = "006000000000000AAA"
ROUTE = "/lightning/r/Opportunity/" + SF + "/view"


def bridge():
    return {
        "version": "live-related-quote-report-bridge-v1",
        "status": "VERIFIED_BY_LIVE_QUOTATION_REPORT",
        "identity_verified": True,
        "opportunity_record_id": SF,
        "save_allowed": False,
        "salesforce_save_performed": False,
    }


def observed():
    return {
        "Account Name": {
            "count": 1, "visible": True, "enabled": True,
            "placeholder": "Search Accounts...", "readonly": True,
        },
        "Main Contact": {
            "count": 1, "visible": True, "enabled": True,
            "placeholder": "Search Contacts...", "readonly": True,
        },
    }


class ExactRecordPreflightTests(unittest.TestCase):
    def test_verified_exact_record_preflight(self):
        self.assertTrue(validate_preflight(bridge(), ROUTE))
        self.assertEqual(SFDC_ROUTE.fullmatch(ROUTE).group(1), SF)

    def test_wrong_record_id_rejected(self):
        with self.assertRaises(ValueError):
            validate_preflight(bridge(), "/lightning/r/Opportunity/006000000000001AAA/view")

    def test_wrong_object_type_rejected(self):
        with self.assertRaises(ValueError):
            validate_preflight(bridge(), "/lightning/r/Contact/" + SF + "/view")

    def test_forged_unverified_bridge_rejected(self):
        x = bridge()
        x["identity_verified"] = False
        with self.assertRaises(ValueError):
            validate_preflight(x, ROUTE)

    def test_legacy_bridge_rejected(self):
        x = bridge()
        x["status"] = "VERIFIED_BUSINESS_ID_MATCH"
        with self.assertRaises(ValueError):
            validate_preflight(x, ROUTE)

    def test_save_permission_must_be_false(self):
        x = bridge()
        x["save_allowed"] = True
        with self.assertRaises(ValueError):
            validate_preflight(x, ROUTE)

    def test_already_saved_bridge_rejected(self):
        x = bridge()
        x["salesforce_save_performed"] = True
        with self.assertRaises(ValueError):
            validate_preflight(x, ROUTE)

    def test_existing_open_editor_rejected(self):
        for save, cancel in ((1, 0), (0, 1), (1, 1)):
            with self.subTest(save=save, cancel=cancel):
                with self.assertRaises(ValueError):
                    validate_preflight(bridge(), ROUTE, save, cancel)


class LookupTopologyTests(unittest.TestCase):
    def test_selected_readonly_lookup_controls_are_valid_ui_topology_only(self):
        self.assertTrue(check_lookup_controls(observed()))

    def test_not_a_record_association_verification(self):
        self.assertTrue(check_lookup_controls(observed()))
        self.assertNotIn("selected_record_id", observed()["Account Name"])

    def test_missing_lookup_control_fails(self):
        x = observed()
        del x["Main Contact"]
        self.assertFalse(check_lookup_controls(x))

    def test_duplicate_lookup_control_fails(self):
        x = observed()
        x["Account Name"]["count"] = 2
        self.assertFalse(check_lookup_controls(x))

    def test_hidden_or_disabled_lookup_fails(self):
        for field in ("Account Name", "Main Contact"):
            for prop in ("visible", "enabled"):
                with self.subTest(field=field, prop=prop):
                    x = observed()
                    x[field][prop] = False
                    self.assertFalse(check_lookup_controls(x))

    def test_wrong_lookup_object_type_fails(self):
        x = observed()
        x["Main Contact"]["placeholder"] = "Search Accounts..."
        self.assertFalse(check_lookup_controls(x))

    def test_missing_lookups_fails(self):
        self.assertFalse(check_lookup_controls({}))
        self.assertFalse(check_lookup_controls(None))


if __name__ == "__main__":
    unittest.main()
