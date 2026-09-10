from __future__ import annotations

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

    async def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
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
        self._token = payload['access_token']
        self._token_expires_at = time.time() + int(payload.get('expires_in', 3600))
        return self._token

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
