import unittest
from unittest.mock import MagicMock
from locator_audit import inspect_frame, inspect_context, AUDIT_VERSION

class AuditTests(unittest.TestCase):
    def test_version_and_aggregate_only(self):
        frame=MagicMock()
        frame.evaluate.return_value={"dialogs":1,"shadow_roots":2,
          "control_types":{"input":3},"control_count":3,"required_count":2}
        result=inspect_frame(frame)
        self.assertEqual(result["control_count"],3)
        self.assertNotIn("values",result)
        self.assertTrue(AUDIT_VERSION.startswith("3."))

    def test_tabs_and_frames(self):
        ctx=MagicMock()
        page=MagicMock()
        page.is_closed.return_value=False
        ctx.pages=[page]
        frame=MagicMock()
        page.frames=[frame]
        frame.evaluate.return_value={"dialogs":1,"shadow_roots":0,
            "control_types":{"input":2},"control_count":2,"required_count":1}
        result=inspect_context(ctx)
        self.assertEqual(result["inspected_tabs"],1)
        self.assertEqual(result["frames_with_controls"],1)
        self.assertEqual(result["results"][0]["dialogs"],1)

if __name__=="__main__":
    unittest.main()
