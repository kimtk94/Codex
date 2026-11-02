"""Offline no-Save tests: only exact v2 business-ID bridges can seed drafts."""
import unittest
from copy import deepcopy

from verify_business_opportunity_id import verify
from create_draft_from_verified_existing import build_draft, select_verified_source

ROUTE = "006123456789ABCDEF"
ID = "Opp-2026-10-23-291068"


def fixture():
    snap = {
        "source": "Salesforce visible UI",
        "saved_or_modified": False,
        "record_id_evidence": "lightning_opportunity_route",
        "record_id_from_url": ROUTE,
        "frames": [{"fields": [
            {"label": "Opportunity ID", "value": ID},
            {"label": "Opportunity Name", "value": "historical-example"},
            {"label": "Amount", "value": "9000"},
            {"label": "Stage", "value": "Closed Won"},
        ]}],
    }
    rows = [{"opportunity_id": ID, "account": "Example Account",
             "contact": "Example Contact"}]
    bridge = verify(snap, rows)
    return bridge, snap, rows


class VerifiedDraftGateTests(unittest.TestCase):
    def test_verified_bridge_outputs_unsaved_draft(self):
        bridge, snap, rows = fixture()
        draft = build_draft(bridge, snap, rows)
        self.assertFalse(draft["lookup_verified"])
        self.assertFalse(draft["save_allowed"])
        self.assertFalse(draft["salesforce_save_performed"])
        self.assertEqual(draft["Amount"], "")
        self.assertEqual(draft["Close Date"], "")
        self.assertEqual(draft["Stage"], "")
        self.assertEqual(draft["source_opportunity_id"], ID)
        self.assertEqual(draft["source_salesforce_record_id"], ROUTE)

    def test_v1_bridge_status_is_not_sufficient(self):
        bridge, snap, rows = fixture()
        bridge["version"] = "business-id-bridge-v1"
        with self.assertRaises(ValueError):
            select_verified_source(bridge, snap, rows)

    def test_fabricated_catalog_business_id_rejected(self):
        bridge, snap, rows = fixture()
        bridge["matched_catalog_business_ids"] = ["Opp-2026-10-23-000000"]
        with self.assertRaises(ValueError):
            select_verified_source(bridge, snap, rows)

    def test_modified_sfdc_record_id_rejected(self):
        bridge, snap, rows = fixture()
        snap["record_id_from_url"] = "006999999999999AAA"
        with self.assertRaises(ValueError):
            select_verified_source(bridge, snap, rows)

    def test_duplicate_catalog_rows_rejected(self):
        bridge, snap, rows = fixture()
        with self.assertRaises(ValueError):
            select_verified_source(bridge, snap, rows * 2)

    def test_missing_source_label_blocks(self):
        bridge, snap, rows = fixture()
        snap["record_id_evidence"] = "NOT_FOUND"
        with self.assertRaises(ValueError):
            select_verified_source(bridge, snap, rows)

    def test_bridge_marked_saved_blocks(self):
        bridge, snap, rows = fixture()
        bridge["salesforce_save_performed"] = True
        with self.assertRaises(ValueError):
            select_verified_source(bridge, snap, rows)


if __name__ == "__main__":
    unittest.main()
