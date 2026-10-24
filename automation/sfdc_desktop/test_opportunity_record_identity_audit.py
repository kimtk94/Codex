import unittest
from unittest.mock import MagicMock
from opportunity_record_identity_audit import classify_url, inspect_context

class IdentityAuditTests(unittest.TestCase):
    def test_record_route(self):
        result=classify_url("https://novogene.lightning.force.com/lightning/r/Opportunity/006123456789ABCDEF/view")
        self.assertTrue(result["valid_id_in_route"])

    def test_workspace_route(self):
        result=classify_url("https://novogene.lightning.force.com/lightning/page/home")
        self.assertTrue(result["lightning_workspace_or_list"])
        self.assertFalse(result["valid_id_in_route"])

    def test_invalid_record_token(self):
        result=classify_url("https://novogene.lightning.force.com/lightning/r/Opportunity/Opp-2025-01-20/view")
        self.assertTrue(result["has_opportunity_record_route"])
        self.assertFalse(result["valid_id_in_route"])

    def test_aggregate_does_not_log_ids(self):
        page=MagicMock()
        page.is_closed.return_value=False
        page.url="https://novogene.lightning.force.com/lightning/page/home"
        frame=MagicMock()
        frame.evaluate.return_value={"shadow_roots":3,"active_tab_indicators":1,
             "opportunity_link_candidates":2,"record_id_attribute_candidates":1}
        page.frames=[frame]
        ctx=MagicMock()
        ctx.pages=[page]
        output=inspect_context(ctx)
        self.assertEqual(output["opportunity_link_candidates"],2)
        self.assertFalse(output["route_record_id"])
        self.assertNotIn("url",output)

if __name__=="__main__":
    unittest.main()
