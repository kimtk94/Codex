#!/usr/bin/env python3
"""Offline view setup safety and isolation tests."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import setup_sales_web as w
from qq_mail_ingest import SafeError


class SalesWebTests(unittest.TestCase):
    def test_no_business_record_writes_in_script(self):
        self.assertEqual(set(w.VIEWS), {
            "QQ Mail Intake", "Accounts", "Contacts", "Opportunities",
            "Quotes", "Projects", "Revenue"
        })
        self.assertEqual(w.VIEWS["QQ Mail Intake"][1], ("수신 메일", "INBOUND"))

    def test_filter_match(self):
        view = {"property": {"filter_info": {"conjunction": "and",
                 "conditions": [{"field_id": "fldD", "operator": "is",
                                 "value": '["INBOUND"]'}]}}}
        self.assertTrue(w.filter_matches(view, "fldD", "INBOUND"))
        self.assertFalse(w.filter_matches(view, "fldD", "OUTBOUND"))

    def test_pending_name_prevents_unfiltered_final_view(self):
        with mock.patch.object(w, "list_views", return_value={}), \
             mock.patch.object(w, "api", return_value={"view": {"view_id": "vew1"}}) as api:
            view_id, created = w.resolve_view("token", "/table", "수신 메일", True)
        self.assertEqual(view_id, "vew1")
        self.assertTrue(created)
        payload = api.call_args.kwargs["data"]
        self.assertEqual(payload["view_name"], "설정중_수신 메일")

    def test_existing_view_not_recreated(self):
        with mock.patch.object(w, "list_views", return_value={"수신 메일": "vew1"}), \
             mock.patch.object(w, "api") as api:
            view_id, created = w.resolve_view("token", "/table", "수신 메일", True)
        self.assertEqual(view_id, "vew1")
        self.assertFalse(created)
        api.assert_not_called()

    def test_unknown_base_refuses_before_auth(self):
        with mock.patch.dict(os.environ, {"FEISHU_SALES_BASE_APP_TOKEN": "other"}), \
             mock.patch.object(w, "auth") as auth:
            with self.assertRaisesRegex(SafeError, "REFUSE_UNRECOGNIZED_FEISHU_BASE"):
                w.main()
            auth.assert_not_called()

    def test_missing_table_aborts_before_view_writes(self):
        with mock.patch.object(w, "list_all", return_value=[{"name": "QQ Mail Intake", "table_id": "tbl1"}]):
            with self.assertRaisesRegex(SafeError, "SALES_WEB_REQUIRED_TABLES_MISSING"):
                w.find_tables("token", "/root")


if __name__ == "__main__":
    unittest.main()
