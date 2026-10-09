"""Regression tests for the production OAuth flock deadlock, broker-free."""
from __future__ import annotations

import asyncio
import fcntl
import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import httpx

from app.config import Settings
from app.toss_client import TossClient


class TossOAuthNonblockingLockTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(
            toss_client_id="test-only",
            toss_client_secret="test-only",
            toss_account="test-only",
            toss_token_cache=str(Path(self.temp.name) / "token.json"),
        )

    def _lockfile(self):
        return Path(str(self.settings.toss_token_cache_path) + ".lock")

    async def test_simultaneous_token_users_issue_only_once(self):
        calls = [0]

        async def issue(_):
            calls[0] += 1
            await asyncio.sleep(0.2)
            return "mock-token", time.time() + 3600

        clients = [TossClient(self.settings) for _ in range(8)]
        for client in clients:
            client._issue_token = issue.__get__(client, TossClient)
        tokens = await asyncio.wait_for(
            asyncio.gather(*(client._get_token() for client in clients)),
            timeout=5,
        )
        self.assertEqual(tokens, ["mock-token"] * 8)
        self.assertEqual(calls, [1])

    async def test_token_wait_does_not_block_event_loop(self):
        client = TossClient(self.settings)
        client._issue_token = AsyncMock(return_value=("mock-token", time.time() + 3600))
        with self._lockfile().open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

            async def release_later():
                await asyncio.sleep(0.2)
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

            release_task = asyncio.create_task(release_later())
            token = await asyncio.wait_for(client._get_token(), timeout=3)
            await release_task
        self.assertEqual(token, "mock-token")

    async def test_rejected_token_invalidation_does_not_block_event_loop(self):
        client = TossClient(self.settings)
        cache = self.settings.toss_token_cache_path
        cache.write_text(json.dumps({"access_token": "rejected", "expires_at": time.time() + 3600}))
        with self._lockfile().open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

            async def release_later():
                await asyncio.sleep(0.2)
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

            release_task = asyncio.create_task(release_later())
            await asyncio.wait_for(client._invalidate_rejected_token("rejected"), timeout=3)
            await release_task
        self.assertFalse(cache.exists())

    async def test_401_retries_only_once_with_new_token(self):
        client = TossClient(self.settings)
        client._token = "stale"
        client._token_expires_at = time.time() + 3600
        issued = []
        calls = []

        async def issue(_):
            issued.append(True)
            return "fresh", time.time() + 3600

        client._issue_token = issue.__get__(client, TossClient)

        class FakeHTTP:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def request(self, method, url, headers, **kwargs):
                calls.append(headers.get("Authorization"))
                code = 401 if len(calls) == 1 else 200
                return httpx.Response(
                    code,
                    json={"ok": code == 200},
                    request=httpx.Request(method, url),
                )

        with patch("app.toss_client.httpx.AsyncClient", FakeHTTP):
            result = await asyncio.wait_for(client.accounts(), timeout=3)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, ["Bearer stale", "Bearer fresh"])
        self.assertEqual(len(issued), 1)
        self.assertTrue(client.last_response_meta.get("auth_retry"))

    async def test_newer_token_not_deleted_by_old_401(self):
        client = TossClient(self.settings)
        client._token = "rejected"
        client._token_expires_at = time.time() + 3600
        client._write_shared_token("newer", time.time() + 7200)
        await client._invalidate_rejected_token("rejected")
        self.assertEqual(
            json.loads(self.settings.toss_token_cache_path.read_text())["access_token"],
            "newer",
        )


if __name__ == "__main__":
    unittest.main()
