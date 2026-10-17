"""Synthetic regression tests for AST sink classifier; no production CSS files."""
from __future__ import annotations

import ast
import unittest
from g16_static_sink_inventory import inventory, name_of, candidate_categories


class SinkInventoryTests(unittest.TestCase):
    def test_pure_ast_name_drops_args_and_literals(self):
        node = ast.parse("sheet.open_by_key('private-spreadsheet-token')").body[0].value
        self.assertEqual(name_of(node.func), "sheet.open_by_key")
        self.assertNotIn("private-spreadsheet-token", name_of(node.func))

    def test_no_function_execution(self):
        src = b"""
raise RuntimeError('if executed')
def main():
    send_message('never-execute')
"""
        result = inventory(src)
        self.assertTrue(result["has_main"])
        self.assertFalse(result["module_import_or_main_executed"])

    def test_import_and_main_sinks(self):
        src = b"""
import sqlite3
import gspread
import subprocess
subprocess.run(['pip', 'install', 'fixture'])
def main():
    helper()
def helper():
    sqlite3.connect('not-accessed')
    gspread.authorize('not-used')
"""
        result = inventory(src)
        self.assertEqual(result["candidate_sinks_import_time"]["subprocess"], 1)
        self.assertGreaterEqual(result["candidate_sinks_main_reachable_approx"]["sql"], 1)
        self.assertGreaterEqual(result["candidate_sinks_main_reachable_approx"]["sheets"], 1)
        self.assertEqual(result["reachable_helpers_approx"], 2)

    def test_exception_sink_is_found(self):
        src = b"""
def main():
    try:
        raise ValueError()
    except Exception:
        backup_runtime_db()
"""
        self.assertGreaterEqual(inventory(src)["candidate_sinks_exception_handlers"]["filesystem"], 1)

    def test_dynamic_sink_is_not_claimed_safe(self):
        src = b"""
def main():
    operation = getattr(object(), 'x')
    operation()
"""
        out = inventory(src)
        self.assertGreaterEqual(out["dynamic_call_sites"], 1)
        self.assertFalse(out["classification_is_exhaustive"])

    def test_main_guard_does_not_count_inert_branch_as_import(self):
        src = b"""
if __name__ == '__main__':
    subprocess.run(['not-executed'])
else:
    sqlite3.connect('would-run-if-imported')
"""
        out = inventory(src)
        self.assertEqual(out["candidate_sinks_import_time"].get("subprocess", 0), 0)
        self.assertGreaterEqual(out["candidate_sinks_import_time"].get("sql", 0), 1)

    def test_no_raw_strings_in_report(self):
        src = b"""
def main():
    gspread.authorize('dummy-confidential-token')
    sqlite3.connect('/private/client-db')
"""
        rendered = str(inventory(src))
        self.assertNotIn("dummy-confidential-token", rendered)
        self.assertNotIn("/private/client-db", rendered)

    def test_module_source_proprietary_not_exposed(self):
        src = b"def secret_impl():\n    pass\n"
        result = inventory(src)
        self.assertNotIn("secret_impl", str(result))

    def test_non_sinks_remain_unclassified(self):
        self.assertEqual(candidate_categories("sum"), set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
