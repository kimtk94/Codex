import unittest
from unittest.mock import MagicMock
from playwright.sync_api import Error as PlaywrightError
from field_label_audit import inspect, error_category

class FieldLabelTests(unittest.TestCase):
    def test_safe_error_classification(self):
        self.assertEqual(error_category(PlaywrightError("Execution context was destroyed")), "NAVIGATION")
        self.assertEqual(error_category(PlaywrightError("SyntaxError unexpected token")), "JAVASCRIPT_SYNTAX")

    def test_successful_probe(self):
        context=MagicMock()
        page=MagicMock()
        page.is_closed.return_value=False
        context.pages=[page]
        frame=MagicMock()
        page.frames=[frame]
        frame.evaluate.return_value={"Amount":{"label_matches":1,"required_labels":1}}
        out=inspect(context)
        self.assertEqual(out["frames_inspected"],1)
        self.assertEqual(out["field_labels"]["Amount"]["label_matches"],1)
        self.assertEqual(out["frames_unavailable"],0)

    def test_failure_categorized_without_secrets(self):
        context=MagicMock()
        page=MagicMock()
        page.is_closed.return_value=False
        context.pages=[page]
        frame=MagicMock()
        page.frames=[frame]
        frame.evaluate.side_effect=PlaywrightError("SyntaxError: unexpected token")
        out=inspect(context)
        self.assertEqual(out["frames_unavailable"],1)
        self.assertEqual(out["failure_categories"],{"JAVASCRIPT_SYNTAX":1})

if __name__=="__main__":
    unittest.main()
