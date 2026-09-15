import json

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
        'version': '0.3.0',
        'tradingEnabled': settings.trading_enabled,
        'liveGateOpen': settings.live_gate_open,
        'manualTradingEnabled': settings.manual_trading_enabled,
        'manualLiveGateOpen': settings.manual_live_gate_open,
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


@app.get('/api/shadow-bakeoff', dependencies=[Depends(authorize_gateway)])
async def shadow_bakeoff(settings: Settings = Depends(get_settings)):
    path = settings.shadow_bakeoff_status_path
    if not path.exists():
        raise HTTPException(status_code=404, detail='Shadow bakeoff status is not available')

    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=f'Shadow bakeoff status unreadable: {type(exc).__name__}') from exc

    if payload.get('status') != 'READY':
        raise HTTPException(status_code=503, detail='Shadow bakeoff status is not READY')

    invariants = payload.get('invariants') or {}
    required_false = (
        'production_write',
        'neon_write',
        'toss_execution',
        'live_execution',
        'auto_trade_visible',
        'dashboard_snapshot_created',
    )
    if invariants.get('file_only') is not True:
        raise HTTPException(status_code=503, detail='Shadow bakeoff file_only invariant failed')
    for key in required_false:
        if invariants.get(key) is not False:
            raise HTTPException(status_code=503, detail=f'Shadow bakeoff invariant failed: {key}')

    safe_signals: dict[str, dict] = {}
    for market, signal in (payload.get('signal_status') or {}).items():
        if not isinstance(signal, dict):
            continue
        safe_signals[str(market)] = {
            'market': signal.get('market') or market,
            'symbol': signal.get('symbol'),
            'as_of': signal.get('as_of'),
            'signal': signal.get('signal'),
            'entry_allowed': bool(signal.get('entry_allowed')),
            'model_family': signal.get('model_family'),
            'missing_feature_ratio': signal.get('missing_feature_ratio'),
            'selected_feature_count': signal.get('selected_feature_count'),
            'probability': signal.get('probability'),
            'probability_threshold': signal.get('probability_threshold'),
            'predicted_return': signal.get('predicted_return'),
            'regime_probability': signal.get('regime_probability'),
            'entry_return_threshold': signal.get('entry_return_threshold'),
            'research_only': True,
            'shadow_only': True,
            'live_execution': False,
            'toss_execution': False,
        }

    ranking = []
    for row in payload.get('forward_ranking') or []:
        if not isinstance(row, dict):
            continue
        ranking.append(
            {
                'strategy': row.get('strategy'),
                'status': row.get('status'),
                'forward_rank': row.get('forward_rank'),
                'total_return': row.get('total_return'),
                'cagr': row.get('cagr'),
                'sharpe': row.get('sharpe'),
                'max_drawdown': row.get('max_drawdown'),
                'latest_target': row.get('latest_target'),
            }
        )

    return {
        'schema_version': 'kalman-shadow-readonly-v1',
        'status': 'READY',
        'experiment': payload.get('experiment'),
        'tracking_status': payload.get('tracking_status'),
        'seed_end': payload.get('seed_end'),
        'latest_as_of': payload.get('latest_as_of'),
        'updated_at': payload.get('updated_at'),
        'post_seed_return_rows': payload.get('post_seed_return_rows'),
        'has_post_seed_signal': payload.get('has_post_seed_signal'),
        'signals': safe_signals,
        'forward_ranking': ranking,
        'invariants': {
            'read_only': True,
            'file_only_source': True,
            'trade_execution': False,
            'auto_trade_visible': False,
        },
    }


@app.post('/api/order-probe', dependencies=[Depends(authorize_gateway)])
async def order_probe(order: OrderProbe, settings: Settings = Depends(get_settings)):
    ledger = TradeLedger(settings.state_db_path)
    decision = validate_order(
        settings,
        order.symbol,
        order.amount_krw,
        ledger.daily_committed(),
        execution_channel='MANUAL',
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
        execution_channel='MANUAL',
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
    return await execute_order(
        settings,
        order,
        execution_channel='MANUAL',
    )
