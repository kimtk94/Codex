"""Synthetic-only G12 AST classifier tests. Production source is never read."""
import unittest

from css_g12_writer_surface_audit import extract


class AuditTests(unittest.TestCase):
    def test_identifies_full_frame_rewrite_and_control_reference(self):
        src = b"def main():\n    overwrite_dataframe(ws, df_sample_intake)\n"
        result = extract(src)
        self.assertEqual(result["candidate_count"], 1)
        site = result["sites"][0]
        self.assertEqual(site["risk"], "DESTRUCTIVE_OR_FULL_REWRITE_CANDIDATE")
        self.assertEqual(site["known_frame_refs"], ["df_sample_intake"])
        self.assertEqual(site["scope"], "main")

    def test_flags_clear_and_resize_on_sheet_object(self):
        src = b"def x():\n  ws.clear()\n  sheet.resize(42)\n"
        result = extract(src)
        self.assertEqual(result["risk_counts"]["DESTRUCTIVE_OR_FULL_REWRITE_CANDIDATE"], 2)

    def test_generic_dict_update_not_mistaken_for_sheet(self):
        src = b"def x():\n  data.update(other)\n  mylist.sort()\n"
        self.assertEqual(extract(src)["candidate_count"], 0)

    def test_worksheet_update_remains_unknown_without_field_mask(self):
        src = b"def main():\n  worksheet.update('A2', [[1]])\n"
        result = extract(src)
        self.assertEqual(result["sites"][0]["risk"], "API_EFFECT_UNKNOWN")
        self.assertFalse(result["actual_writer_ranges_proven"])

    def test_private_literal_not_exported(self):
        src = b"def main():\n  sheet.update('PVT-SHEET-ID', [['customer@example.org']])\n"
        rendered = str(extract(src))
        self.assertNotIn("PVT-SHEET-ID", rendered)
        self.assertNotIn("customer@example.org", rendered)

    def test_no_import_execution(self):
        src = b"raise RuntimeError('do not execute')\ndef main():\n  sheet.clear()\n"
        result = extract(src)
        self.assertFalse(result["production_source_executed"])
        self.assertEqual(result["candidate_count"], 1)

    def test_async_scope_and_append(self):
        src = b"async def pipeline():\n  worksheet.append_rows([[1]])\n"
        result = extract(src)
        self.assertEqual(result["risk_counts"]["STRUCTURAL_APPEND_CANDIDATE"], 1)
        self.assertEqual(result["sites"][0]["scope"], "helper")

    def test_not_proof_of_field_protection(self):
        result = extract(b"def main():\n  pass\n")
        self.assertEqual(result["candidate_count"], 0)
        self.assertFalse(result["high_risk_sheet_protection_proven"])
        self.assertFalse(result["actual_writer_ranges_proven"])

    def test_bounded_summary_output(self):
        src = b"def main():\n" + b"    sheet.update('A1', [1])\n"*200
        result = extract(src)
        self.assertGreater(result["candidate_count"], 150)
        self.assertEqual(len(result["sites"]), 150)
        self.assertTrue(result["sites_truncated"])


if __name__ == "__main__":
    unittest.main()
