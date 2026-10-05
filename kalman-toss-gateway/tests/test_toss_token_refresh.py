from __future__ import annotations

import json
import time
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import httpx

from app.config import Settings
from app.toss_client import TossClient


class FakeAsyncClient:
    responses: list[tuple[int, dict]] = []
    calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method: str, url: str, **kwargs):
        self.__class__.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(kwargs.get("headers") or {}),
                "params": kwargs.get("params"),
                "json": kwargs.get("json"),
            }
        )
        status, payload = self.__class__.responses.pop(0)
        request = httpx.Request(method, url)
        return httpx.Response(status, json=payload, request=request)


class TossTokenRefreshTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        FakeAsyncClient.responses = []
        FakeAsyncClient.calls = []

    def _client(self, tmp: str) -> TossClient:
        settings = Settings(
            toss_client_id="client-id",
            toss_client_secret="client-secret",
            toss_account="account-seq",
            toss_token_cache=f"{tmp}/toss_oauth_token.json",
        )
        return TossClient(settings)

    async def test_401_invalidates_token_refreshes_and_retries_once(self) -> None:
        with TemporaryDirectory() as tmp:
            client = self._client(tmp)
            old_expires = time.time() + 3600
            client._token = "old-token"
            client._token_expires_at = old_expires
            client._write_shared_token("old-token", old_expires)

            FakeAsyncClient.responses = [
                (401, {"error": "invalid_token"}),
                (200, {"accounts": [{"accountSeq": "account-seq"}]}),
            ]
            issue_token = AsyncMock(return_value=("new-token", time.time() + 7200))

            with (
                patch("app.toss_client.httpx.AsyncClient", FakeAsyncClient),
                patch.object(client, "_issue_token", issue_token),
            ):
                payload = await client.accounts()

            self.assertEqual(payload["accounts"][0]["accountSeq"], "account-seq")
            self.assertEqual(len(FakeAsyncClient.calls), 2)
            self.assertEqual(
                FakeAsyncClient.calls[0]["headers"]["Authorization"],
                "Bearer old-token",
            )
            self.assertEqual(
                FakeAsyncClient.calls[1]["headers"]["Authorization"],
                "Bearer new-token",
            )
            issue_token.assert_awaited_once()
            self.assertTrue(client.last_response_meta.get("auth_retry"))

            cached = json.loads(
                client.settings.toss_token_cache_path.read_text(encoding="utf-8")
            )
            self.assertEqual(cached["access_token"], "new-token")

    async def test_second_401_raises_after_exactly_one_retry(self) -> None:
        with TemporaryDirectory() as tmp:
            client = self._client(tmp)
            client._token = "old-token"
            client._token_expires_at = time.time() + 3600

            FakeAsyncClient.responses = [
                (401, {"error": "invalid_token"}),
                (401, {"error": "invalid_token_again"}),
            ]
            issue_token = AsyncMock(return_value=("new-token", time.time() + 7200))

            with (
                patch("app.toss_client.httpx.AsyncClient", FakeAsyncClient),
                patch.object(client, "_issue_token", issue_token),
            ):
                with self.assertRaises(httpx.HTTPStatusError):
                    await client.accounts()

            self.assertEqual(len(FakeAsyncClient.calls), 2)
            issue_token.assert_awaited_once()
            self.assertIsNone(client._token)
            self.assertFalse(client.settings.toss_token_cache_path.exists())

    async def test_401_does_not_delete_newer_shared_token_from_other_process(self) -> None:
        with TemporaryDirectory() as tmp:
            client = self._client(tmp)
            client._token = "rejected-token"
            client._token_expires_at = time.time() + 3600
            client._write_shared_token("newer-shared-token", time.time() + 7200)

            FakeAsyncClient.responses = [
                (401, {"error": "invalid_token"}),
                (200, {"ok": True}),
            ]
            issue_token = AsyncMock(return_value=("should-not-be-issued", time.time() + 7200))

            with (
                patch("app.toss_client.httpx.AsyncClient", FakeAsyncClient),
                patch.object(client, "_issue_token", issue_token),
            ):
                payload = await client.accounts()

            self.assertTrue(payload["ok"])
            self.assertEqual(
                FakeAsyncClient.calls[1]["headers"]["Authorization"],
                "Bearer newer-shared-token",
            )
            issue_token.assert_not_awaited()

            cached = json.loads(
                client.settings.toss_token_cache_path.read_text(encoding="utf-8")
            )
            self.assertEqual(cached["access_token"], "newer-shared-token")


if __name__ == "__main__":
    unittest.main()
