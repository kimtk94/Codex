import unittest
from unittest.mock import MagicMock
from opportunity_record_identity_audit import classify_url, inspect_context, error_category
from playwright.sync_api import Error as PlaywrightError

class IdentityAuditTests(unittest.TestCase):
    def test_record_route(self):
        result=classify_url("https://novogene.lightning.force.com/lightning/r/Opportunity/006123456789ABCDEF/view")
        self.assertTrue(result["route_record_id"])

    def test_workspace_route(self):
        result=classify_url("https://novogene.lightning.force.com/lightning/page/home")
        self.assertTrue(result["workspace_or_list_route"])
        self.assertFalse(result["route_record_id"])

    def test_invalid_record_token(self):
        result=classify_url("https://novogene.lightning.force.com/lightning/r/Opportunity/Opp-2025-01-20/view")
        self.assertTrue(result["route_opportunity"])
        self.assertFalse(result["route_record_id"])

    def test_counts_without_exposing_ids(self):
        page=MagicMock()
        page.is_closed.return_value=False
        page.url="https://novogene.lightning.force.com/lightning/page/home"
        frame=MagicMock()
        frame.locator.return_value.count.return_value=2
        page.frames=[frame]
        ctx=MagicMock()
        ctx.pages=[page]
        output=inspect_context(ctx)
        self.assertEqual(output["opportunity_link_candidates"],2)
        self.assertEqual(output["frames_inspected"],1)
        self.assertFalse(output["route_record_id"])
        self.assertNotIn("url",output)

    def test_failure_redacted(self):
        self.assertEqual(error_category(PlaywrightError("Frame was detached")),"FRAME_DETACHED")

if __name__=="__main__":
    unittest.main()
