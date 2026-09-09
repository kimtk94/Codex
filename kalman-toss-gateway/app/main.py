import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import Settings, get_settings
from .executor import TradeLedger, execute_order, prepare_order
from .risk import validate_order
from .toss_client import TossClient

app = FastAPI(title='Kalman Toss Gateway', version='0.2.0')


class OrderProbe(BaseModel):
    symbol: str
    amount_krw: int


class LiveOrder(BaseModel):
    client_order_id: str = Field(min_length=1, max_length=36, pattern=r'^[A-Za-z0-9_-]+$')
    symbol: str
    side: str = 'BUY'
    order_type: str = 'MARKET'
    time_in_force: str = 'DAY'
    quantity: str | None = None
    order_amount: str | None = None
    price: str | None = None


def authorize_gateway(
    x_gateway_secret: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.hub_gateway_secret:
        raise HTTPException(status_code=503, detail='Gateway secret is not configured')
    if x_gateway_secret != settings.hub_gateway_secret:
        raise HTTPException(status_code=401, detail='Unauthorized')


@app.exception_handler(httpx.HTTPStatusError)
async def toss_http_status_error(_, exc: httpx.HTTPStatusError):
    response = exc.response
    try:
        upstream_body = response.json()
    except Exception:
        upstream_body = response.text[:1000]
    return JSONResponse(
        status_code=response.status_code,
        content={
            'error': 'TOSS_UPSTREAM_HTTP_ERROR',
            'upstreamStatus': response.status_code,
            'upstreamBody': upstream_body,
        },
    )


@app.exception_handler(httpx.RequestError)
async def toss_request_error(_, exc: httpx.RequestError):
    return JSONResponse(
        status_code=502,
        content={
            'error': 'TOSS_UPSTREAM_CONNECTION_ERROR',
            'detail': exc.__class__.__name__,
        },
    )


@app.exception_handler(RuntimeError)
async def gateway_runtime_error(_, exc: RuntimeError):
    return JSONResponse(status_code=503, content={'error': 'GATEWAY_ERROR', 'detail': str(exc)})


@app.exception_handler(ValueError)
async def gateway_value_error(_, exc: ValueError):
    return JSONResponse(status_code=400, content={'error': 'INVALID_ORDER', 'detail': str(exc)})


@app.get('/health')
async def health(settings: Settings = Depends(get_settings)):
    return {
        'status': 'ok',
        'service': 'kalman-toss-gateway',
        'version': '0.2.0',
        'tradingEnabled': settings.trading_enabled,
        'liveGateOpen': settings.live_gate_open,
        'allowedSymbols': sorted(settings.allowed_symbols),
        'limits': {
            'dailyTotalKrw': settings.live_micro_total_limit_krw,
            'singleOrderKrw': settings.max_single_order_krw,
        },
    }


@app.get('/api/accounts', dependencies=[Depends(authorize_gateway)])
async def accounts(settings: Settings = Depends(get_settings)):
    return await TossClient(settings).accounts()


@app.get('/api/prices', dependencies=[Depends(authorize_gateway)])
async def prices(
    symbols: str = Query('QQQ,NVDA,IONQ'),
    settings: Settings = Depends(get_settings),
):
    return await TossClient(settings).prices(
        [s.strip().upper() for s in symbols.split(',') if s.strip()]
    )


@app.get('/api/holdings', dependencies=[Depends(authorize_gateway)])
async def holdings(settings: Settings = Depends(get_settings)):
    return await TossClient(settings).holdings()


@app.get('/api/buying-power', dependencies=[Depends(authorize_gateway)])
async def buying_power(
    currency: str = Query('KRW'),
    settings: Settings = Depends(get_settings),
):
    return await TossClient(settings).buying_power(currency)


@app.get('/api/orders', dependencies=[Depends(authorize_gateway)])
async def orders(
    status: str = Query('OPEN'),
    settings: Settings = Depends(get_settings),
):
    return await TossClient(settings).orders(status)


@app.post('/api/order-probe', dependencies=[Depends(authorize_gateway)])
async def order_probe(order: OrderProbe, settings: Settings = Depends(get_settings)):
    ledger = TradeLedger(settings.state_db_path)
    decision = validate_order(
        settings,
        order.symbol,
        order.amount_krw,
        ledger.daily_committed(),
    )
    return {
        'symbol': order.symbol.upper(),
        'amountKrw': order.amount_krw,
        'allowed': decision.allowed,
        'reason': decision.reason,
        'executionAttempted': False,
    }


@app.post('/api/order-preview', dependencies=[Depends(authorize_gateway)])
async def order_preview(order: LiveOrder, settings: Settings = Depends(get_settings)):
    prepared = await prepare_order(settings, order)
    ledger = TradeLedger(settings.state_db_path)
    decision = validate_order(
        settings,
        order.symbol,
        prepared.estimated_notional_krw,
        ledger.daily_committed(),
    )
    return {
        'allowed': decision.allowed,
        'reason': decision.reason,
        'executionAttempted': False,
        'estimatedNotionalKrw': prepared.estimated_notional_krw,
        'currency': prepared.currency,
        'tossPayload': prepared.payload,
    }


@app.post('/api/orders/live', dependencies=[Depends(authorize_gateway)])
async def live_order(order: LiveOrder, settings: Settings = Depends(get_settings)):
    return await execute_order(settings, order)
