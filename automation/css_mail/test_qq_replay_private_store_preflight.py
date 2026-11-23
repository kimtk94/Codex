"""All synthetic metadata and read-only API tests; no real GitHub writes."""
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from automation.css_mail.qq_replay_private_store_preflight import (
    check_private_repository, _read_metadata, _RejectRedirects, main,
)


def good():
    return {
        "id": 987654321,
        "full_name": "kimtk94/qq-private-invoice-receipts",
        "owner": {"login": "kimtk94", "type": "User"},
        "private": True,
        "visibility": "private",
        "fork": False,
        "archived": False,
        "disabled": False,
        "permissions": {"pull": True, "push": True},
    }


class StorePreflightTests(unittest.TestCase):
    def test_private_metadata_is_insufficient_for_authorized_execution(self):
        d=check_private_repository(good(), good()["full_name"])
        self.assertEqual(d["private_repo_metadata_verified"], 1)
        self.assertEqual(d["reason_code"], "PRIVATE_METADATA_OK_NO_EXECUTION_AUTHORITY")
        self.assertEqual(d["status"], "HOLD")
        for k in ("repository_write_access_verified",
                  "independent_case_approvals_verified",
                  "external_writer_exclusion_verified",
                  "durable_real_receipts_verified",
                  "cross_system_atomicity_verified",
                  "qq_stage_writes","qq_cursor_writes","qq_canonical_writes"):
            self.assertEqual(d[k],0)
        self.assertFalse(d["can_execute_replay"])
        self.assertNotIn(good()["full_name"],json.dumps(d))

    def test_public_repo_fork_and_archived_fail_closed(self):
        for patch,reason in (
            ({"private":False,"visibility":"public"},"PRIVATE_REPO_NOT_PRIVATE"),
            ({"fork":True},"PRIVATE_REPO_FORK_OR_UNKNOWN"),
            ({"archived":True},"PRIVATE_REPO_ARCHIVED_DISABLED_OR_UNKNOWN"),
            ({"disabled":True},"PRIVATE_REPO_ARCHIVED_DISABLED_OR_UNKNOWN"),
            ({"id":None},"PRIVATE_REPO_STABLE_ID_INVALID"),
            ({"owner":{"login":"different"}},"PRIVATE_REPO_OWNER_MISMATCH"),
            ({"full_name":"someone-else/repo"},"PRIVATE_REPO_IDENTITY_MISMATCH"),
        ):
            with self.subTest(patch=patch):
                r=check_private_repository({**good(),**patch},good()["full_name"])
                self.assertEqual(r["reason_code"],reason)
                self.assertEqual(r["private_repo_metadata_verified"],0)

    def test_own_public_codex_is_explicitly_rejected(self):
        metadata={**good(),"full_name":"kimtk94/Codex"}
        r=check_private_repository(metadata,"kimtk94/Codex")
        self.assertEqual(r["reason_code"],"PRIVATE_REPO_NOT_DEDICATED")

    def test_missing_or_unknown_repo_owner_fails(self):
        for name in ("", "other/qq-private-invoice-receipts",
                     "../oops", "kimtk94/.hidden", "kimtk94/bad name"):
            with self.subTest(name=name):
                self.assertEqual(
                    check_private_repository(good(),name)["private_repo_metadata_verified"],0)

    def test_metadata_fetch_only_get_and_token_not_logged(self):
        calls=[]
        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,*args):return json.dumps(good()).encode("utf-8")
        def fake_opener(req,timeout):
            calls.append((req.get_method(),req.full_url,req.get_header("Authorization")))
            self.assertEqual(timeout,15)
            return FakeResponse()
        result=_read_metadata(good()["full_name"],"synthetic-token",opener=fake_opener)
        self.assertEqual(result,good())
        self.assertEqual(calls[0][0],"GET")
        self.assertIn("api.github.com/repos/",calls[0][1])
        self.assertEqual(calls[0][2],"Bearer synthetic-token")

    def test_http_redirect_never_forwards_private_token(self):
        guard=_RejectRedirects()
        result=guard.redirect_request(
            None,None,302,"Found",{},"https://untrusted.invalid/steal")
        self.assertIsNone(result)

    def test_without_secrets_preflight_prints_only_safe_hold(self):
        stdout=io.StringIO()
        with mock.patch.dict(os.environ,{
                "QQ_REPLAY_PRIVATE_JOURNAL_REPO":"",
                "QQ_REPLAY_PRIVATE_JOURNAL_READ_TOKEN":"",
            }),redirect_stdout(stdout):
            code=main()
        self.assertEqual(code,0)
        report=json.loads(stdout.getvalue().split("=",1)[1])
        self.assertEqual(report["reason_code"],"PRIVATE_JOURNAL_READER_NOT_CONFIGURED")
        self.assertEqual(report["qq_stage_writes"],0)
        self.assertEqual(report["durable_real_receipts_verified"],0)

    def test_fetch_failure_never_echoes_private_token(self):
        stdout=io.StringIO()
        with mock.patch.dict(os.environ,{
                "QQ_REPLAY_PRIVATE_JOURNAL_REPO":good()["full_name"],
                "QQ_REPLAY_PRIVATE_JOURNAL_READ_TOKEN":"synthetic-private-token",
            }),mock.patch(
                "automation.css_mail.qq_replay_private_store_preflight._read_metadata",
                side_effect=RuntimeError("synthetic-private-token"),
            ),redirect_stdout(stdout):
            self.assertEqual(main(),0)
        self.assertNotIn("synthetic-private-token",stdout.getvalue())
        self.assertEqual(json.loads(stdout.getvalue().split("=",1)[1])["status"],"HOLD")


if __name__=="__main__":
    unittest.main()
