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

        async with httpx.AsyncClient(timeout=10.0) as client:
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
        expires_in = int(payload.get('expires_in', 3600))
        self._token_expires_at = time.time() + expires_in
        return self._token

    async def _headers(self, account_required: bool = False) -> dict[str, str]:
        token = await self._get_token()
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        if account_required:
            if not self.settings.toss_account:
                raise RuntimeError('TOSS_ACCOUNT is not configured')
            headers['X-Tossinvest-Account'] = self.settings.toss_account
        return headers

    async def prices(self, symbols: list[str]) -> Any:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f'{BASE_URL}/api/v1/prices',
                params={'symbols': ','.join(symbols)},
                headers=await self._headers(False),
            )
            response.raise_for_status()
            return response.json()

    async def holdings(self) -> Any:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f'{BASE_URL}/api/v1/holdings',
                headers=await self._headers(True),
            )
            response.raise_for_status()
            return response.json()

    async def buying_power(self) -> Any:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f'{BASE_URL}/api/v1/buying-power',
                headers=await self._headers(True),
            )
            response.raise_for_status()
            return response.json()
