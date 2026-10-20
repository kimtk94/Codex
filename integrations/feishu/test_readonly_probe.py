"""Offline regression tests; no Feishu credentials or outbound requests required."""
import contextlib
import importlib.util
import io
import os
import pathlib
import unittest
from unittest import mock

SCRIPT = pathlib.Path(__file__).with_name("readonly_probe.py")
SPEC = importlib.util.spec_from_file_location("readonly_probe", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

class ProbeTests(unittest.TestCase):
    def test_missing_credentials_fails_closed(self):
        with mock.patch.dict(os.environ, {"FEISHU_APP_ID": "", "FEISHU_APP_SECRET": ""}):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = probe.main()
            self.assertEqual(code, 2)
            self.assertIn("CONFIG_MISSING", out.getvalue())

    def test_success_uses_get_only_for_company_data_and_never_logs_values(self):
        confidential = "DO_NOT_LEAK_CUSTOMER_DATA"
        calls = []
        def fake_request(method, path, token=None, body=None):
            calls.append((method, path, token, body))
            if "tenant_access_token" in path:
                return {"code": 0, "tenant_access_token": "TEST_ONLY_TOKEN"}
            if "get_node" in path:
                return {"code": 0, "data": {"node": {"obj_type": "bitable", "obj_token": "app_test"}}}
            if path.endswith("fields?page_size=1"):
                return {"code": 0, "data": {"items": [{"field_name": confidential}], "has_more": True}}
            if path.endswith("records?page_size=1"):
                return {"code": 0, "data": {"items": [{"fields": {"company": confidential}}], "has_more": True}}
            raise AssertionError("Unexpected API path")
        with mock.patch.dict(os.environ, {"FEISHU_APP_ID": "cli_test", "FEISHU_APP_SECRET": "TEST_SECRET"}), mock.patch.object(probe, "request", side_effect=fake_request):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = probe.main()
        self.assertEqual(code, 0)
        self.assertIn("PROBE_PASS", out.getvalue())
        self.assertNotIn(confidential, out.getvalue())
        self.assertNotIn("TEST_SECRET", out.getvalue())
        self.assertNotIn("TEST_ONLY_TOKEN", out.getvalue())
        self.assertEqual([x[0] for x in calls], ["POST", "GET", "GET", "GET"])
        self.assertTrue(all(x[0] == "GET" for x in calls[1:]))
        self.assertTrue(all(x[2] == "TEST_ONLY_TOKEN" for x in calls[1:]))

    def test_missing_wiki_permission_fails_without_exposing_message(self):
        def fake_request(method, path, token=None, body=None):
            if method == "POST":
                return {"code": 0, "tenant_access_token": "SECRET_TOKEN"}
            return {"code": 99991672, "msg": "SENSITIVE_DETAILS"}
        with mock.patch.dict(os.environ, {"FEISHU_APP_ID": "cli_test", "FEISHU_APP_SECRET": "TEST_SECRET"}), mock.patch.object(probe, "request", side_effect=fake_request):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = probe.main()
        self.assertEqual(code, 1)
        self.assertIn("99991672", out.getvalue())
        self.assertNotIn("SENSITIVE_DETAILS", out.getvalue())
        self.assertNotIn("SECRET_TOKEN", out.getvalue())

    def test_non_bitable_wiki_node_is_rejected(self):
        def fake_request(method, path, token=None, body=None):
            if method == "POST":
                return {"code": 0, "tenant_access_token": "T"}
            return {"code": 0, "data": {"node": {"obj_type": "docx", "obj_token": "obj"}}}
        with mock.patch.dict(os.environ, {"FEISHU_APP_ID": "id", "FEISHU_APP_SECRET": "secret"}), mock.patch.object(probe, "request", side_effect=fake_request):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(probe.main(), 1)

if __name__ == "__main__":
    unittest.main()
