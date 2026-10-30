"""Quota-error replay policy: GET may retry; Sheets writes never do."""
import unittest
from unittest.mock import patch

import followup_stage1 as m


class FakeResponse:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self.ok = status < 400
        self.content = b"{}"
        self.body = body if body is not None else {"error": {"status": "RESOURCE_EXHAUSTED"}}
        self.headers = headers or {}

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


class QuotaRetryTests(unittest.TestCase):
    @patch.object(m.time, "sleep")
    def test_get_retries_429_then_succeeds(self, sleep):
        session = FakeSession([
            FakeResponse(429),
            FakeResponse(429, headers={"Retry-After": "15"}),
            FakeResponse(200, body={"values": [["ok"]]}),
        ])
        self.assertEqual({"values": [["ok"]]}, m.call(session, "GET", "https://sheets.test/x", stage="quota_read"))
        self.assertEqual(3, len(session.calls))
        self.assertEqual([10, 20], [c.args[0] for c in sleep.call_args_list])

    @patch.object(m.time, "sleep")
    def test_get_rate_limit_exhaustion_is_bounded(self, sleep):
        session = FakeSession([FakeResponse(429)] * 4)
        with self.assertRaisesRegex(RuntimeError, "stage=quota_read HTTP=429"):
            m.call(session, "GET", "https://sheets.test/x", stage="quota_read")
        self.assertEqual(4, len(session.calls))
        self.assertEqual(3, sleep.call_count)

    @patch.object(m.time, "sleep")
    def test_post_write_never_retried(self, sleep):
        session = FakeSession([FakeResponse(429), FakeResponse(200)])
        with self.assertRaisesRegex(RuntimeError, "HTTP=429"):
            m.call(session, "POST", "https://sheets.test/clear", stage="clear", json={})
        self.assertEqual(1, len(session.calls))
        sleep.assert_not_called()

    @patch.object(m.time, "sleep")
    def test_nonquota_403_not_retried(self, sleep):
        session = FakeSession([FakeResponse(403, {"error": {"status": "PERMISSION_DENIED"}})])
        with self.assertRaisesRegex(RuntimeError, "HTTP=403"):
            m.call(session, "GET", "https://sheets.test/x", stage="denied")
        self.assertEqual(1, len(session.calls))
        sleep.assert_not_called()

    @patch.object(m.time, "sleep")
    def test_retry_after_respected_and_capped(self, sleep):
        session = FakeSession([FakeResponse(429, headers={"Retry-After": "500"}), FakeResponse(200, {})])
        m.call(session, "GET", "https://sheets.test/x", stage="backoff")
        sleep.assert_called_once_with(60.0)


if __name__ == "__main__":
    unittest.main()
