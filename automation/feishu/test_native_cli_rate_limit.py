#!/usr/bin/env python3
"""Synthetic, no-credentials tests for Feishu native widget rate limiting."""
import types
import unittest
from unittest import mock
import native_dashboard_cli as native

class RateLimitTests(unittest.TestCase):
    def reply(self,code,stderr="",stdout=""):
        return types.SimpleNamespace(returncode=code,stderr=stderr,stdout=stdout)
    def test_retry_only_backend_rate_limited_800004135(self):
        responses=[
            self.reply(1,stderr='{"error":{"code":800004135,"message":"method limited"}}'),
            self.reply(0,stdout='{"ok":true}')
        ]
        with mock.patch.object(native.subprocess,"run",side_effect=responses) as process, \
             mock.patch.object(native.time,"sleep") as sleep:
            result=native.cli("+dashboard-block-update","--base-token","testToken")
        self.assertTrue(result["ok"])
        self.assertEqual(process.call_count,2)
        sleep.assert_called_once_with(2)
    def test_auth_or_validation_failure_never_retries(self):
        with mock.patch.object(native.subprocess,"run",return_value=self.reply(
                1,stderr='{"error":{"code":999,"message":"unauthorized"}}')) as process, \
             mock.patch.object(native.time,"sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError,"FEISHU_CLI_COMMAND_FAILED"):
                native.cli("+dashboard-block-update")
        process.assert_called_once()
        sleep.assert_not_called()
    def test_throttle_exhaustion_is_bounded(self):
        response=self.reply(1,stderr='{"error":{"code":800004135}}')
        with mock.patch.object(native.subprocess,"run",return_value=response) as run, \
             mock.patch.object(native.time,"sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError,"FEISHU_CLI_COMMAND_FAILED"):
                native.cli("+dashboard-block-update")
        self.assertEqual(run.call_count,6)
        self.assertEqual([x.args[0] for x in sleep.call_args_list],[2,4,8,16,28])
    def test_json_result_parser_still_accepts_success(self):
        with mock.patch.object(native.subprocess,"run",return_value=self.reply(
                0,stdout='{"items":[{"name":"Chart"}]}')), \
             mock.patch.object(native.time,"sleep") as sleep:
            self.assertEqual(len(native.cli("+dashboard-block-list")["items"]),1)
        sleep.assert_not_called()

if __name__=="__main__":
    unittest.main()
