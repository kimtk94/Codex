"""Synthetic-only safety tests for G12 writer AST context scanner."""
import unittest
from css_g12_writer_context_audit import inspect

class ContextTests(unittest.TestCase):
    def test_known_tab_constant_and_write_ref_only_context(self):
        src=b'''TAB="CSS Contract-SIF Tracker"
def emit(sheet_ws):
    label=TAB
    sheet_ws.clear()
'''
        obj=inspect(src)
        self.assertEqual(obj["module_known_tab_constants"]["sif_tracker"],1)
        self.assertEqual(obj["contextual_sites"][0]["tab_references_in_same_function"],["sif_tracker"])
        self.assertFalse(obj["contextual_sites"][0]["tab_reference_is_write_target_proof"])

    def test_never_reports_unknown_user_literals(self):
        src=b'''SECRET="customer@example.test"
def f(sheet_ws):
    sheet_ws.update("private-project", [["client@example.test"]])
'''
        rendered=str(inspect(src))
        for value in ("customer@example.test","private-project","client@example.test","SECRET"):
            self.assertNotIn(value,rendered)

    def test_safely_classifies_destructive_calls(self):
        src=b'''def main():
    ws.batch_clear(["A2:C3"])
    ws.resize(5)
    set_with_dataframe(ws, fixture)
'''
        obj=inspect(src)
        self.assertEqual(obj["candidate_methods_by_risk"]["structural_or_full_rewrite"],3)
        self.assertEqual([x["method"] for x in obj["contextual_sites"]],
                         ["batch_clear","resize","set_with_dataframe"])

    def test_generic_sort_and_dict_update_ignored(self):
        src=b"def main():\n    items.sort()\n    mapping.update(other)\n"
        self.assertEqual(inspect(src)["candidate_methods_by_risk"],{})

    def test_python_source_not_executed(self):
        src=b"raise RuntimeError('private')\ndef main():\n    ws.clear()\n"
        obj=inspect(src)
        self.assertEqual(len(obj["contextual_sites"]),1)
        self.assertFalse(obj["source_or_function_executed"])

    def test_conservative_worksheet_alias_is_context_only(self):
        src=b'''TAB="CSS Contract-SIF Tracker"
def main():
    input_ws=worksheets[TAB]
    input_ws.clear()
'''
        report=inspect(src)
        site=report["contextual_sites"][0]
        self.assertEqual(site["simple_alias_possible_target"],"sif_tracker")
        self.assertFalse(site["alias_match_is_runtime_proof"])

    def test_worksheet_factory_method_uses_known_tab_literal(self):
        src=b'''def run():
    temp_ws=book.worksheet("CSS Project Dashboard")
    temp_ws.batch_update([])
'''
        site=inspect(src)["contextual_sites"][0]
        self.assertEqual(site["simple_alias_possible_target"],"dashboard")

    def test_ambiguous_reassignment_does_not_claim_target(self):
        src=b'''TAB="CSS Project Dashboard"
def main():
    tab_ws=worksheets[TAB]
    tab_ws=other
    tab_ws.clear()
'''
        site=inspect(src)["contextual_sites"][0]
        self.assertIsNone(site["simple_alias_possible_target"])

    def test_missing_tab_not_interpreted_as_safe(self):
        src=b"def main():\n    ws.clear()\n"
        obj=inspect(src)
        self.assertEqual(obj["contextual_sites"][0]["tab_references_in_same_function"],[])
        self.assertFalse(obj["call_target_or_field_masks_proven"])

    def test_exact_allowlisted_tab_only(self):
        src=b'''BAD="CSS Project Dashboard - copy"
GOOD="CSS Project Dashboard"
def main():
    ws.update("A2",[[1]])
'''
        obj=inspect(src)
        self.assertEqual(obj["module_known_tab_constants"],{"dashboard":1})

    def test_method_appears_in_main_or_helper(self):
        src=b'''def main():
    ws.update("D2",[[1]])
def helper():
    sheet.batch_update([])
'''
        obj=inspect(src)
        self.assertEqual(obj["candidate_methods_by_scope"],{"helper":1,"main":1})

if __name__=="__main__":
    unittest.main()
