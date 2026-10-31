import unittest
from unittest.mock import MagicMock
from existing_opportunity_audit import inspect_context, VERSION

class ExistingOpportunityTests(unittest.TestCase):
    def test_counts_only(self):
        frame=MagicMock()
        frame.evaluate.return_value={
           "labels":{"Details":1,"Related":1,"Quotation":2},
           "inline_edit_controls":8,"editable_controls":0,"shadow_roots":12}
        page=MagicMock()
        page.is_closed.return_value=False
        page.frames=[frame]
        ctx=MagicMock()
        ctx.pages=[page]
        result=inspect_context(ctx)
        self.assertEqual(result["frames_inspected"],1)
        self.assertEqual(result["visible_label_indicators"]["Details"],1)
        self.assertEqual(result["inline_edit_controls"],8)
        self.assertEqual(result["version"],VERSION)
        self.assertNotIn("record_id",result)

if __name__=="__main__":
    unittest.main()
