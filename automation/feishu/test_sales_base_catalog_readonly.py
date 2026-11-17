#!/usr/bin/env python3
"""Offline tests for read-only Feishu Base catalog diagnostics."""
import io
import hashlib
import unittest
from contextlib import redirect_stdout
from unittest import mock

import sales_base_catalog_readonly as catalog
import qq_mail_ingest as q
from setup_sales_web import EXPECTED_BASE


def tables(names):
    return [{"name": name, "table_id": "tbl" + str(i)} for i, name in enumerate(names)]


class SalesBaseCatalogTests(unittest.TestCase):
    def test_mail_only_is_business_block(self):
        info = catalog.analyze(tables([q.TABLE]))
        self.assertEqual(info["reason"], "ONLY_MAIL_INTAKE_VISIBLE")
        self.assertEqual(info["required_missing"], 6)
        self.assertEqual(info["visible_total"], 1)
        self.assertEqual(info["unrecognized_visible"], 0)

    def test_complete_catalog_pass(self):
        info = catalog.analyze(tables(sorted(catalog.REQUIRED)))
        self.assertEqual(info["status"], "PASS")
        self.assertEqual(info["required_unique"], 7)

    def test_renamed_or_unexpected_name_is_not_pass(self):
        info = catalog.analyze(tables([q.TABLE, "Accounts Renamed"]))
        self.assertEqual(info["status"], "BLOCK")
        self.assertEqual(info["reason"], "CATALOG_NAME_OR_VISIBILITY_REVIEW")
        self.assertEqual(info["unrecognized_visible"], 1)

    def test_duplicate_required_name_fails(self):
        info = catalog.analyze(tables([q.TABLE, q.TABLE]))
        self.assertEqual(info["status"], "BLOCK")
        self.assertEqual(info["required_duplicated"], 1)

    def test_blank_table_id_fails(self):
        entries = tables(sorted(catalog.REQUIRED))
        entries[0]["table_id"] = ""
        info = catalog.analyze(entries)
        self.assertEqual(info["status"], "BLOCK")
        self.assertEqual(info["invalid_metadata"], 1)

    def test_missing_mail_intake_fails(self):
        info = catalog.analyze(tables(sorted(catalog.EXPECTED_BUSINESS_TABLES)))
        self.assertEqual(info["status"], "BLOCK")
        self.assertEqual(info["mail_intake_count"], 0)

    def test_wrong_base_blocks_before_network(self):
        with mock.patch.dict("os.environ", {"FEISHU_BASE_APP_TOKEN": "WRONG"}), \
             mock.patch.object(q, "auth") as auth:
            with self.assertRaisesRegex(q.SafeError, "CATALOG_WRONG_TARGET_BASE"):
                catalog.main()
            auth.assert_not_called()

    def test_catalog_probe_never_writes_and_fails_closed(self):
        stream = io.StringIO()
        with mock.patch.dict("os.environ", {"FEISHU_BASE_APP_TOKEN": EXPECTED_BASE}), \
             mock.patch.object(q, "auth", return_value=("tok", "/app")), \
             mock.patch.object(q, "list_all", return_value=tables([q.TABLE])), \
             mock.patch.object(q, "api") as api, redirect_stdout(stream):
            with self.assertRaisesRegex(q.SafeError, "CATALOG_NOT_READY_ONLY_MAIL"):
                catalog.main()
            api.assert_not_called()
        self.assertIn("SALES_BASE_CATALOG_REQUIRED_MISSING=6", stream.getvalue())
        self.assertIn("read_only=1", stream.getvalue())

    def test_schema_fingerprint_matches_are_aggregate_only(self):
        entries = tables(["A", "B"])
        def fields(token, path):
            if path.endswith("/tbl0"):
                return [{"field_name": field} for field in catalog.SCHEMA_SIGNATURES["ACCOUNTS"]]
            return [{"field_name": "Quote ID"}, {"field_name": "Unit"}]
        with mock.patch.object(q, "get_fields", side_effect=fields), \
             mock.patch.object(q, "api") as api:
            result = catalog.signature_counts("token", "/base", entries)
            api.assert_not_called()
        self.assertEqual(result["SCHEMA_TABLES_SCANNED"], 2)
        self.assertEqual(result["SCHEMA_ACCOUNTS_EXACT_CANDIDATES"], 1)
        self.assertEqual(result["SCHEMA_QUOTES_PARTIAL_CANDIDATES"], 1)
        self.assertNotIn("tbl0", str(result))
        self.assertNotIn("A", list(result.values()))

    def test_schema_scan_refuses_more_than_100_tables(self):
        with self.assertRaisesRegex(q.SafeError, "CATALOG_SCHEMA_SCAN_TOO_LARGE"):
            catalog.signature_counts("tok", "/base", tables(["x"] * 101))

    def test_schema_scan_field_unavailable_fails_closed(self):
        with mock.patch.object(q, "get_fields", side_effect=q.SafeError("SCHEMA_READ_FAILED")):
            with self.assertRaisesRegex(q.SafeError, "SCHEMA_READ_FAILED"):
                catalog.signature_counts("tok", "/base", tables(["x"]))

    def test_historic_ids_preserved_even_when_names_changed(self):
        digests = {
            "ACCOUNTS": hashlib.sha256(b"tblPriorAccount").hexdigest(),
            "MAIL": hashlib.sha256(b"tblPriorMail").hexdigest(),
        }
        with mock.patch.object(catalog, "HISTORIC_TABLE_ID_SHA256", digests):
            state = catalog.historic_table_identity([
                {"name": "New Account Name", "table_id": "tblPriorAccount"},
                {"name": q.TABLE, "table_id": "tblPriorMail"},
            ])
        self.assertEqual(state["HISTORIC_ACCOUNTS_STATUS"], "PRESENT_CHANGED_NAME")
        self.assertEqual(state["HISTORIC_MAIL_STATUS"], "PRESENT_SAME_NAME")
        self.assertEqual(state["HISTORIC_NOT_VISIBLE_COUNT"], 0)
        self.assertNotIn("tblPriorAccount", str(state))

    def test_historic_identity_not_visible_is_not_deletion_proof(self):
        digests = {"ACCOUNTS": hashlib.sha256(b"tblMissing").hexdigest()}
        with mock.patch.object(catalog, "HISTORIC_TABLE_ID_SHA256", digests):
            state = catalog.historic_table_identity(tables(["Unrelated Table"]))
        self.assertEqual(state["HISTORIC_ACCOUNTS_STATUS"], "NOT_VISIBLE")
        self.assertEqual(state["HISTORIC_NOT_VISIBLE_COUNT"], 1)

    def test_historic_identity_duplicate_id_fails(self):
        with self.assertRaisesRegex(q.SafeError, "HISTORIC_CATALOG_DUPLICATE_TABLE_ID"):
            catalog.historic_table_identity([
                {"name": q.TABLE, "table_id": "tblSame"},
                {"name": "Other", "table_id": "tblSame"},
            ])

    def test_historic_identity_empty_id_fails(self):
        with self.assertRaisesRegex(q.SafeError, "HISTORIC_CATALOG_TABLE_ID_MISSING"):
            catalog.historic_table_identity([{"name": q.TABLE, "table_id": ""}])

    def test_operational_catalog_actual_schema_and_absent_separately(self):
        entries = tables(["Project Progress Board", "Monthly Tax Invoice",
                          "Weekly Quote Review", "00 영업 홈"])
        def readfields(token, path):
            name = entries[int(path.rsplit("tbl", 1)[1])]["name"]
            found = next((markers for title, markers in catalog.OPERATIONAL_SIGNATURES.values()
                          if title == name), frozenset())
            return [{"field_name": col} for col in found]
        with mock.patch.object(q, "get_fields", side_effect=readfields):
            state = catalog.operational_table_metadata("tok", "/base", entries)
        self.assertEqual(state["OPERATIONAL_PROJECT_PROGRESS_STATUS"], "SCHEMA_PASS")
        self.assertEqual(state["OPERATIONAL_MONTHLY_TAX_STATUS"], "SCHEMA_PASS")
        self.assertEqual(state["OPERATIONAL_WEEKLY_REVIEW_STATUS"], "SCHEMA_PASS")
        self.assertEqual(state["OPERATIONAL_SALES_HOME_STATUS"], "SCHEMA_PASS")
        self.assertEqual(state["OPERATIONAL_WEEKLY_KPI_STATUS"], "MISSING")
        self.assertEqual(state["OPERATIONAL_VISIBLE_COUNT"], 4)
        self.assertEqual(state["OPERATIONAL_REQUIRED_TOTAL"], 10)

    def test_operational_catalog_detects_drift_and_duplicates(self):
        entries = tables(["Project Progress Board", "Project Progress Board",
                          "Monthly Tax Invoice", "Mail Identity 2026"])
        with mock.patch.object(q, "get_fields", return_value=[
                {"field_name": "Source Key"}]):
            state = catalog.operational_table_metadata("tok", "/base", entries)
        self.assertEqual(state["OPERATIONAL_PROJECT_PROGRESS_STATUS"], "DUPLICATED")
        self.assertEqual(state["OPERATIONAL_MONTHLY_TAX_STATUS"], "SCHEMA_DRIFT")
        self.assertEqual(state["OPERATIONAL_MAIL_IDENTITY_STATUS"], "VISIBLE_SCHEMA_UNCHECKED")

    def test_operational_catalog_field_unavailable_fails_closed(self):
        with mock.patch.object(q, "get_fields", side_effect=q.SafeError("FIELD_API_UNAVAILABLE")):
            with self.assertRaisesRegex(q.SafeError, "FIELD_API_UNAVAILABLE"):
                catalog.operational_table_metadata("tok", "/base",
                    tables(["Project Progress Board"]))

    def test_unavailable_catalog_source_never_passes(self):
        with mock.patch.dict("os.environ", {"FEISHU_BASE_APP_TOKEN": EXPECTED_BASE}), \
             mock.patch.object(q, "auth", return_value=("tok", "/app")), \
             mock.patch.object(q, "list_all", side_effect=q.SafeError("CATALOG_SOURCE_UNAVAILABLE")):
            with self.assertRaisesRegex(q.SafeError, "CATALOG_SOURCE_UNAVAILABLE"):
                catalog.main()


if __name__ == "__main__":
    unittest.main()
