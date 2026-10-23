#!/usr/bin/env python3
"""Synthetic Feishu project-state tests; no external Feishu or Sheet credentials."""
import pathlib, sys, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from project_status_sync import group, pick, normalize, status
class ProjectStates(unittest.TestCase):
    def test_independent_flags_both(self):
        self.assertEqual(status(True,True)[0],"P0_BOTH")
        self.assertEqual(status(True,False)[0],"P1_ETAX")
        self.assertEqual(status(False,True)[0],"P1_PAYMENT")
    def test_exact_project_ids_and_dedup(self):
        rows=[{"fields":{"Project Number":"AMEA2026102149"}},{"fields":{"Project Number":"AMEA2026102149"}},{"fields":{"Project Number":"AMEA2026102149-01"}}]
        groups,missing=group(rows,"Project Number")
        self.assertEqual(missing,0)
        self.assertEqual(len(groups),2)
        self.assertEqual(groups["AMEA2026102149"],2)
    def test_unknown_project_quarantined(self):
        groups,missing=group([{"fields":{"Project Number":None}},{"fields":{"Project Number":"unknown"}}],"Project Number")
        self.assertEqual(missing,2)
        self.assertFalse(groups)
    def test_column_alias(self):
        self.assertEqual(pick([{"field_name":"Project Number"}]),"Project Number")
if __name__=="__main__":unittest.main()
