from __future__ import annotations

import fcntl
import json
import os
import time
from typing import Any

import httpx

from .config import Settings


BASE_URL = 'https://openapi.tossinvest.com'


class TossClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._token: str | None = None
        self._token_expires_at = 0.0

    def _read_shared_token(self) -> tuple[str | None, float]:
        path = self.settings.toss_token_cache_path
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
            token = str(payload.get('access_token') or '')
            expires_at = float(payload.get('expires_at') or 0)
            if token and time.time() < expires_at - 60:
                return token, expires_at
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return None, 0.0

    def _write_shared_token(self, token: str, expires_at: float) -> None:
        path = self.settings.toss_token_cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump({'access_token': token, 'expires_at': expires_at}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
            os.chmod(path, 0o600)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except FileNotFoundError:
                    pass

    async def _issue_token(self) -> tuple[str, float]:
        if not self.settings.toss_client_id or not self.settings.toss_client_secret:
            raise RuntimeError('Toss credentials are not configured')
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f'{BASE_URL}/oauth2/token',
                data={
                    'grant_type': 'client_credentials',
                    'client_id': self.settings.toss_client_id,
                    'client_secret': self.settings.toss_client_secret,
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )
            response.raise_for_status()
            payload = response.json()
        token = payload['access_token']
        expires_at = time.time() + int(payload.get('expires_in', 3600))
        return token, expires_at

    async def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        token, expires_at = self._read_shared_token()
        if token:
            self._token, self._token_expires_at = token, expires_at
            return token

        cache_path = self.settings.toss_token_cache_path
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = cache_path.with_suffix(cache_path.suffix + '.lock')
        with open(lock_path, 'a+', encoding='utf-8') as lock_file:
            os.chmod(lock_path, 0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                token, expires_at = self._read_shared_token()
                if not token:
                    token, expires_at = await self._issue_token()
                    self._write_shared_token(token, expires_at)
                self._token, self._token_expires_at = token, expires_at
                return token
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    async def _headers(self, account_required: bool = False) -> dict[str, str]:
        token = await self._get_token()
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        if account_required:
            if not self.settings.toss_account:
                raise RuntimeError('TOSS_ACCOUNT (accountSeq) is not configured')
            headers['X-Tossinvest-Account'] = self.settings.toss_account
        return headers

    async def accounts(self) -> Any:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f'{BASE_URL}/api/v1/accounts', headers=await self._headers(False))
            r.raise_for_status()
            return r.json()

    async def prices(self, symbols: list[str]) -> Any:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f'{BASE_URL}/api/v1/prices',
                params={'symbols': ','.join(symbols)},
                headers=await self._headers(False),
            )
            r.raise_for_status()
            return r.json()

    async def exchange_rate(self, base: str = 'USD', quote: str = 'KRW') -> Any:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f'{BASE_URL}/api/v1/exchange-rate',
                params={'baseCurrency': base, 'quoteCurrency': quote},
                headers=await self._headers(False),
            )
            r.raise_for_status()
            return r.json()

    async def market_calendar_us(self, date: str | None = None) -> Any:
        params = {'date': date} if date else None
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f'{BASE_URL}/api/v1/market-calendar/US',
                params=params,
                headers=await self._headers(False),
            )
            r.raise_for_status()
            return r.json()

    async def holdings(self, symbol: str | None = None) -> Any:
        params = {'symbol': symbol.upper()} if symbol else None
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f'{BASE_URL}/api/v1/holdings',
                params=params,
                headers=await self._headers(True),
            )
            r.raise_for_status()
            return r.json()

    async def buying_power(self, currency: str = 'KRW') -> Any:
        currency = currency.upper()
        if currency not in {'KRW', 'USD'}:
            raise ValueError('currency must be KRW or USD')
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f'{BASE_URL}/api/v1/buying-power',
                params={'currency': currency},
                headers=await self._headers(True),
            )
            r.raise_for_status()
            return r.json()

    async def sellable_quantity(self, symbol: str) -> Any:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f'{BASE_URL}/api/v1/sellable-quantity',
                params={'symbol': symbol.upper()},
                headers=await self._headers(True),
            )
            r.raise_for_status()
            return r.json()

    async def orders(self, status: str = 'OPEN') -> Any:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f'{BASE_URL}/api/v1/orders',
                params={'status': status.upper()},
                headers=await self._headers(True),
            )
            r.raise_for_status()
            return r.json()

    async def place_order(self, payload: dict[str, Any]) -> Any:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f'{BASE_URL}/api/v1/orders',
                json=payload,
                headers={**await self._headers(True), 'Content-Type': 'application/json'},
            )
            r.raise_for_status()
            return r.json()

    async def cancel_order(self, order_id: str) -> Any:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f'{BASE_URL}/api/v1/orders/{order_id}/cancel',
                headers=await self._headers(True),
            )
            r.raise_for_status()
            return r.json()
