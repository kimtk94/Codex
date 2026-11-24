#!/usr/bin/env python3
"""Offline transport regression for throttled KPI source reads; no credentials."""
import contextlib
import io
import json
import unittest
import urllib.error
from email.message import Message
from unittest import mock

import qq_mail_ingest as q
import sales_kpi_dashboard as dashboard


def response(obj, headers=None):
    result = io.BytesIO(json.dumps(obj).encode())
    result.headers = Message()
    for name, value in (headers or {}).items():
        result.headers[name] = value
    return result


def http_error(code, headers=None):
    result = Message()
    for name, value in (headers or {}).items():
        result[name] = value
    return urllib.error.HTTPError("https://example.invalid/", code, "private body", result, None)


class ReadThrottleTests(unittest.TestCase):
    def test_throttled_second_page_retries_same_cursor_without_duplicate_rows(self):
        responses = [
            response({"code": 0, "data": {"items": [{"record_id": "one"}],
                      "has_more": True, "page_token": "next/page"}}),
            response({"code": 1254290, "msg": "private body"}),
            response({"code": 0, "data": {"items": [{"record_id": "two"}]}}),
        ]
        with mock.patch.object(q.urllib.request, "urlopen", side_effect=responses) as call, \
             mock.patch.object(q.time, "sleep") as sleep:
            rows = q.list_all("/records", "private-token", "dashboard_source_read")
        self.assertEqual(rows, [{"record_id": "one"}, {"record_id": "two"}])
        urls = [c.args[0].full_url for c in call.call_args_list]
        self.assertNotEqual(urls[0], urls[1])
        self.assertEqual(urls[1], urls[2])
        self.assertIn("page_token=next%2Fpage", urls[1])
        sleep.assert_called_once_with(2)

    def test_http_429_respects_server_delta_seconds(self):
        replies = [http_error(429, {"Retry-After": "7"}),
                   response({"code": 0, "data": {"items": []}})]
        with mock.patch.object(q.urllib.request, "urlopen", side_effect=replies) as call, \
             mock.patch.object(q.time, "sleep") as sleep:
            self.assertEqual(q.api("GET", "/records"), {"items": []})
        self.assertEqual(call.call_count, 2)
        sleep.assert_called_once_with(7)

    def test_gateway_hint_and_excessive_cooldown_are_bounded(self):
        for headers, expected_calls, expected_delay in [
            ({"X-Ogw-Ratelimit-Reset": "9", "Retry-After": "3"}, 2, 9),
            ({"Retry-After": "120"}, 1, None),
        ]:
            with self.subTest(headers=headers), \
                 mock.patch.object(q.urllib.request, "urlopen", side_effect=[
                     response({"code": 1254290}, headers),
                     response({"code": 0, "data": {}})]) as call, \
                 mock.patch.object(q.time, "sleep") as sleep:
                if expected_delay is None:
                    with self.assertRaisesRegex(q.SafeError, "^feishu_api_CODE_1254290$"):
                        q.api("GET", "/records")
                    sleep.assert_not_called()
                else:
                    q.api("GET", "/records")
                    sleep.assert_called_once_with(expected_delay)
                self.assertEqual(call.call_count, expected_calls)

    def test_repeated_throttling_fails_closed_with_sanitized_error(self):
        output = io.StringIO()
        with mock.patch.object(q.urllib.request, "urlopen", side_effect=lambda *a, **k:
                response({"code": 1254290, "msg": "private customer body"})) as call, \
             mock.patch.object(q.time, "sleep") as sleep, \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            with self.assertRaisesRegex(q.SafeError, "^dashboard_source_read_CODE_1254290$"):
                q.api("GET", "/records", "private-token", action="dashboard_source_read")
        self.assertEqual(call.call_count, 6)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4, 8, 16, 32])
        self.assertEqual(output.getvalue(), "")

    def test_writes_and_auth_are_never_replayed(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            for outcome in ("body", "http"):
                with self.subTest(method=method, outcome=outcome), \
                     mock.patch.object(q.urllib.request, "urlopen", side_effect=[
                         response({"code": 1254290}) if outcome == "body" else http_error(429)
                     ]) as call, mock.patch.object(q.time, "sleep") as sleep:
                    with self.assertRaises(q.SafeError):
                        q.api(method, "/open-apis/auth/v3/tenant_access_token/internal",
                              data={"app_secret": "private"})
                    call.assert_called_once()
                    sleep.assert_not_called()

    def test_other_errors_and_network_failures_do_not_retry(self):
        for result, expected in (
            (response({"code": 1254302, "msg": "permission denied"}), "CODE_1254302"),
            (http_error(403), "HTTP_403"),
            (urllib.error.URLError("private url"), "NETWORK_ERROR"),
            (TimeoutError("private url"), "NETWORK_ERROR"),
        ):
            with self.subTest(expected=expected), \
                 mock.patch.object(q.urllib.request, "urlopen", side_effect=[result]) as call, \
                 mock.patch.object(q.time, "sleep") as sleep:
                with self.assertRaisesRegex(q.SafeError, "^feishu_api_" + expected + "$"):
                    q.api("GET", "/records")
                call.assert_called_once()
                sleep.assert_not_called()

    def test_unavailable_source_stops_dashboard_before_any_write(self):
        with mock.patch.dict(q.os.environ, {
                "FEISHU_BASE_APP_TOKEN": dashboard.EXPECTED_BASE,
                "FEISHU_DASHBOARD_MODE": "apply"}), \
             mock.patch.object(dashboard, "auth", return_value=("token", "/base")), \
             mock.patch.object(dashboard, "table_ids", return_value={}), \
             mock.patch.object(dashboard, "load", side_effect=q.SafeError(
                 "dashboard_source_read_CODE_1254290")), \
             mock.patch.object(dashboard, "ensure_table") as ensure, \
             mock.patch.object(dashboard, "upsert") as write:
            with self.assertRaises(q.SafeError):
                dashboard.main()
        ensure.assert_not_called()
        write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
