from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .config import Settings, get_settings
from .risk import validate_order
from .toss_client import TossClient

app = FastAPI(title='Kalman Toss Gateway', version='0.1.0')


class OrderProbe(BaseModel):
    symbol: str
    amount_krw: int


def authorize_gateway(
    x_gateway_secret: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.hub_gateway_secret:
        raise HTTPException(status_code=503, detail='Gateway secret is not configured')
    if x_gateway_secret != settings.hub_gateway_secret:
        raise HTTPException(status_code=401, detail='Unauthorized')


@app.get('/health')
async def health(settings: Settings = Depends(get_settings)):
    return {
        'status': 'ok',
        'service': 'kalman-toss-gateway',
        'tradingEnabled': settings.trading_enabled,
        'allowedSymbols': sorted(settings.allowed_symbols),
        'limits': {
            'totalKrw': settings.live_micro_total_limit_krw,
            'singleOrderKrw': settings.max_single_order_krw,
        },
    }


@app.get('/api/prices', dependencies=[Depends(authorize_gateway)])
async def prices(settings: Settings = Depends(get_settings)):
    client = TossClient(settings)
    return await client.prices(['QQQ', 'NVDA', 'IONQ'])


@app.get('/api/holdings', dependencies=[Depends(authorize_gateway)])
async def holdings(settings: Settings = Depends(get_settings)):
    client = TossClient(settings)
    return await client.holdings()


@app.get('/api/buying-power', dependencies=[Depends(authorize_gateway)])
async def buying_power(settings: Settings = Depends(get_settings)):
    client = TossClient(settings)
    return await client.buying_power()


@app.post('/api/order-probe', dependencies=[Depends(authorize_gateway)])
async def order_probe(order: OrderProbe, settings: Settings = Depends(get_settings)):
    decision = validate_order(settings, order.symbol, order.amount_krw)
    return {
        'symbol': order.symbol.upper(),
        'amountKrw': order.amount_krw,
        'allowed': decision.allowed,
        'reason': decision.reason,
        'executionAttempted': False,
    }
