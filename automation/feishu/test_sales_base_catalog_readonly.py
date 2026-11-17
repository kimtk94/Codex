#!/usr/bin/env python3
"""Offline tests for read-only Feishu Base catalog diagnostics."""
import io
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

    def test_unavailable_catalog_source_never_passes(self):
        with mock.patch.dict("os.environ", {"FEISHU_BASE_APP_TOKEN": EXPECTED_BASE}), \
             mock.patch.object(q, "auth", return_value=("tok", "/app")), \
             mock.patch.object(q, "list_all", side_effect=q.SafeError("CATALOG_SOURCE_UNAVAILABLE")):
            with self.assertRaisesRegex(q.SafeError, "CATALOG_SOURCE_UNAVAILABLE"):
                catalog.main()


if __name__ == "__main__":
    unittest.main()
