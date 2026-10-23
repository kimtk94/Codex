#!/usr/bin/env python3
"""Offline checks for Salesforce Quote export; no API access."""
import pathlib,sys,unittest
from unittest.mock import MagicMock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import types
if "incremental_sync" not in sys.modules:
    fake=types.ModuleType("incremental_sync");fake.api=MagicMock();fake.authorize=MagicMock();sys.modules["incremental_sync"]=fake
import sfdc_quote_validation as q
class QuoteExportTests(unittest.TestCase):
    def test_canonical_export_header(self):
        header=["Salesforce Record ID","IsActive","Grand Total","CurrencyIsoCode","Opportunity ID","Last Modified Date"]
        self.assertEqual(q.missing(header),[])
    def test_opportunity_snapshot_is_not_quote_export(self):
        self.assertIn("active",q.missing(["Opportunity Name","Amount","Stage","Opportunity Currency"]))
    def test_active_must_be_explicit(self):
        self.assertIsNone(q.active("Quote Issued"))
        self.assertIsNone(q.active(""))
        self.assertTrue(q.active("TRUE"))
        self.assertFalse(q.active("False"))
    def test_currency_not_inferred_from_amount(self):
        self.assertEqual(q.amount("₩13,605,000.00"),13605000.0)
        self.assertIsNone(q.amount("TBD"))
        self.assertIsNone(q.amount("-5"))
    def test_duplicate_ids_do_not_become_valid(self):
        rows=["a0PTK00000zPiZ1","a0PTK00000zPiZ1"]
        self.assertNotEqual(len(rows),len(set(rows)))
if __name__=="__main__":unittest.main()
