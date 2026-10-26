#!/usr/bin/env python3
"""Offline regression tests for Lead outgoing-email audit guards."""
import ast
import datetime
import pathlib
import unittest

SOURCE = pathlib.Path("automation/css/lead_sent_audit_refresh.py")
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
FUNCTIONS = [n for n in TREE.body if isinstance(n, ast.FunctionDef)]
DATE = next(n for n in FUNCTIONS if n.name == "date")
namespace = {"datetime": datetime}
exec(compile(ast.Module(body=[DATE], type_ignores=[]), str(SOURCE), "exec"), namespace)

class LeadAuditSafetyTest(unittest.TestCase):
    def test_naive_timestamp_uses_kst(self):
        self.assertEqual(namespace["date"]("2026-10-26T12:00:00").utcoffset(), datetime.timedelta(hours=9))

    def test_explicit_offset_preserved(self):
        self.assertEqual(namespace["date"]("2026-10-26T12:00:00+08:00").utcoffset(), datetime.timedelta(hours=8))

    def test_invalid_timestamp_is_not_evidence(self):
        self.assertIsNone(namespace["date"]("not-a-date"))

    def test_duplicate_guards_and_source_headers_present(self):
        source = SOURCE.read_text(encoding="utf-8")
        for expected in ("Duplicate audit Lead ID", "Duplicate source Lead ID", "Unexpected email evidence columns"):
            self.assertIn(expected, source)

    def test_formula_error_sent_count_is_safe(self):
        source = SOURCE.read_text(encoding='utf-8')
        self.assertIn("str(val(old,3) or '0').isdigit() else 0", source)

    def test_stale_source_blocks_scheduled_writes(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("if not dry and source_stale:", source)
        self.assertIn("raise RuntimeError('Lead audit source is stale; refusing writes')", source)
        self.assertLess(source.index("if not dry and source_stale:"), source.index("if not dry:"))

    def test_independent_reconciliation_and_default_dry_run(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('if not dry:', source)
        self.assertIn('if sf_updates:', source)
        self.assertIn('os.getenv("DRY_RUN","true")', source)
        self.assertNotIn('if not dry and updates:', source)

if __name__ == "__main__":
    unittest.main()
