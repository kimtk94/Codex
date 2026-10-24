import unittest
from unittest.mock import MagicMock
from locator_audit import inspect, inspect_context

class AuditTests(unittest.TestCase):
    def test_aggregate_only(self):
        frame=MagicMock()
        frame.evaluate.return_value={"dialog_found":True,"control_count":2,
             "control_types":{"input":1,"button":1},"required_count":1,"mode":"dialog"}
        result=inspect(frame)
        self.assertEqual(result["control_count"],2)
        self.assertEqual(result["required_count"],1)
        self.assertNotIn("controls",result)

    def test_full_page_fallback(self):
        frame=MagicMock()
        frame.evaluate.return_value={"dialog_found":False,"control_count":12,
             "control_types":{"input":10,"button":2},"required_count":5,"mode":"document"}
        self.assertFalse(inspect(frame)["dialog_found"])
        self.assertEqual(inspect(frame)["mode"],"document")

    def test_all_tabs_and_frames(self):
        ctx=MagicMock()
        first=MagicMock()
        second=MagicMock()
        first.is_closed.return_value=False
        second.is_closed.return_value=False
        ctx.pages=[first,second]
        a=MagicMock();a.evaluate.return_value={"dialog_found":False,"control_count":0,
             "control_types":{},"required_count":0,"mode":"document"}
        b=MagicMock();b.evaluate.return_value={"dialog_found":True,"control_count":3,
             "control_types":{"input":3},"required_count":2,"mode":"dialog"}
        first.frames=[a];second.frames=[b]
        result=inspect_context(ctx)
        self.assertEqual(result["inspected_tabs"],2)
        self.assertEqual(result["frames_with_controls"],1)
        self.assertTrue(result["results"][0]["dialog_found"])

if __name__=="__main__":
    unittest.main()
