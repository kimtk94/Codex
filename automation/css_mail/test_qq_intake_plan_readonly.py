#!/usr/bin/env python3
"""Offline-only QQ intake plan tests. No QQ IMAP or Google Sheets access."""
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

import incremental_sync as sync


class DummyIMAP:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def login(self, user, password):
        pass
    def logout(self):
        pass


class QQIntakePlanTests(unittest.TestCase):
    def test_mode_defaults_to_existing_apply_but_allows_plan(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(sync.ingest_mode(), "apply")
        with mock.patch.dict(os.environ, {"CSS_MAIL_MODE": "plan"}):
            self.assertEqual(sync.ingest_mode(), "plan")

    def test_unrecognized_mode_blocks_before_auth(self):
        with mock.patch.dict(os.environ, {"CSS_MAIL_MODE": "apply_unsafe"}), \
             mock.patch.object(sync, "authorize") as authorize:
            with self.assertRaisesRegex(RuntimeError, "CSS_MAIL_MODE_INVALID"):
                sync.main()
            authorize.assert_not_called()

    def test_plan_does_not_create_tab_append_or_send(self):
        calls = []
        def sheets_api(session, method, url, **kwargs):
            calls.append((method, url))
            if method != "GET":
                raise AssertionError("No write permitted in plan mode")
            if "/values/" in url:
                return {"values": [sync.COLS]}
            self.fail("unexpected Sheets API path")
        row = ["new-key", "mid", "456", "INBOX", "uv", "2026-11-17T14:00:00Z"] + [""] * 12
        self.assertEqual(len(row), len(sync.COLS))
        stream = io.StringIO()
        with mock.patch.dict(os.environ, {
                "CSS_MAIL_MODE": "plan",
                "CSS_QQ_MAIL_ADDRESS": "synthetic@example.invalid",
                "CSS_QQ_MAIL_AUTH_CODE": "synthetic"},
                clear=True), \
             mock.patch.object(sync, "authorize", return_value=object()), \
             mock.patch.object(sync, "api", side_effect=sheets_api), \
             mock.patch.object(sync, "ensure_tab") as ensure, \
             mock.patch.object(sync, "existing_keys", side_effect=[set(), set()]) as keys, \
             mock.patch.object(sync.imaplib, "IMAP4_SSL", return_value=DummyIMAP()), \
             mock.patch.object(sync, "folder_names",
                               return_value=[("Sent", "\\sent")]), \
             mock.patch.object(sync, "collect", side_effect=[[row], []]) as collect, \
             redirect_stdout(stream):
            sync.main()
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(x[0] == "GET" for x in calls))
        self.assertEqual(keys.call_count, 2)
        self.assertEqual(collect.call_count, 2)
        ensure.assert_not_called()
        output = stream.getvalue()
        self.assertIn("CSS_MAIL_PLAN_PASS pending_new=1", output)
        self.assertIn("no_business_writes=1", output)
        self.assertNotIn("synthetic@example.invalid", output)
        self.assertNotIn("CSS_MAIL_SYNC_PASS", output)

    def test_read_only_header_preflight_fails_closed(self):
        with mock.patch.object(sync, "api", return_value={"values": []}) as api:
            with self.assertRaisesRegex(RuntimeError, "CSS_MAIL_PLAN_STAGING_HEADER_INVALID"):
                sync.check_tab_readonly(object())
        api.assert_called_once()
        self.assertEqual(api.call_args.args[1], "GET")

    def test_existing_scheduled_apply_mode_still_appends_only_new(self):
        api_calls = []
        def fake_api(s, method, url, **kwargs):
            api_calls.append(method)
            if method == "POST":
                self.assertIn(":append", url)
                self.assertEqual(len(kwargs["json"]["values"]), 1)
            return {}
        row = ["key"] + [""] * (len(sync.COLS) - 1)
        with mock.patch.dict(os.environ, {
                "CSS_MAIL_MODE": "apply",
                "CSS_QQ_MAIL_ADDRESS": "synthetic@example.invalid",
                "CSS_QQ_MAIL_AUTH_CODE": "synthetic"}, clear=True), \
             mock.patch.object(sync, "authorize", return_value=object()), \
             mock.patch.object(sync, "ensure_tab") as ensure, \
             mock.patch.object(sync, "existing_keys", side_effect=[set(), set()]), \
             mock.patch.object(sync.imaplib, "IMAP4_SSL", return_value=DummyIMAP()), \
             mock.patch.object(sync, "folder_names",
                               return_value=[("Sent", "\\sent")]), \
             mock.patch.object(sync, "collect", side_effect=[[row], []]), \
             mock.patch.object(sync, "api", side_effect=fake_api), \
             redirect_stdout(io.StringIO()):
            sync.main()
        ensure.assert_called_once()
        self.assertEqual(api_calls, ["POST"])


if __name__ == "__main__":
    unittest.main()
