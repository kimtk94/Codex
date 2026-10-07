from datetime import datetime, timezone

import httpx

from engine import prediction_market_layer_v0 as pm


UTC = timezone.utc


def cfg():
    return {
        "quality_gate": {
            "min_liquidity_usd": 5000,
            "min_volume_24h_usd": 1000,
            "max_spread": 0.10,
            "min_hours_to_event": 2,
            "max_source_age_minutes": 360,
        },
        "theme_keywords": {
            "FED_POLICY": ["fed", "fomc", "interest rate"],
            "RECESSION_GROWTH": ["recession"],
        },
        "semantic_rules": {
            "FED_EASING": {
                "patterns": [["fed", "cut"]],
                "risk_prior_sign": 1,
            },
            "RECESSION_RISK": {
                "patterns": [["recession"]],
                "risk_prior_sign": -1,
            },
        },
        "retention_days": 180,
    }


def sample_market(prob="0.64"):
    return {
        "id": "m1",
        "conditionId": "c1",
        "question": "Will the Fed cut interest rates at the next meeting?",
        "outcomes": '["Yes","No"]',
        "outcomePrices": f'["{prob}","{1-float(prob):.2f}"]',
        "clobTokenIds": '["yes-token","no-token"]',
        "liquidityNum": 25000,
        "volume24hr": 120000,
        "spread": 0.02,
        "bestBid": 0.63,
        "bestAsk": 0.65,
        "endDate": "2030-01-01T00:00:00Z",
        "updatedAt": "2026-10-07T11:39:00Z",
        "enableOrderBook": True,
        "acceptingOrders": True,
    }


def test_normalize_binary_yes_market():
    now = datetime(2026, 10, 7, 11, 40, tzinfo=UTC)
    r = pm.normalize_market(sample_market(), observed_at=now, config=cfg())
    assert r is not None
    assert r["poly_prob"] == 0.64
    assert r["yes_token_id"] == "yes-token"
    assert r["theme"] == "FED_POLICY"
    assert r["semantic_channel"] == "FED_EASING"
    assert r["risk_prior_sign"] == 1
    assert r["trade_execution_enabled"] is False
    assert r["challenger_only"] is True


def test_quality_gate_rejects_low_liquidity():
    now = datetime(2026, 10, 7, 11, 40, tzinfo=UTC)
    m = sample_market()
    m["liquidityNum"] = 100
    r = pm.normalize_market(m, observed_at=now, config=cfg())
    ok, reasons = pm.eligibility(r, cfg())
    assert ok is False
    assert "LOW_LIQUIDITY" in reasons


def test_history_deltas_use_point_in_time_snapshot(tmp_path):
    db = tmp_path / "pm.sqlite3"
    with pm.sqlite3.connect(db) as conn:
        pm.init_db(conn)
        t0 = datetime(2026, 10, 7, 10, 40, tzinfo=UTC)
        r0 = pm.normalize_market(sample_market("0.50"), observed_at=t0, config=cfg())
        r0["eligible"] = True
        r0["quality_blockers"] = []
        pm.store_records([r0], conn, t0, 180)

        t1 = datetime(2026, 10, 7, 11, 40, tzinfo=UTC)
        r1 = pm.normalize_market(sample_market("0.64"), observed_at=t1, config=cfg())
        pm.add_history_features([r1], conn, t1)

    assert r1["poly_delta_1h"] == 0.14
    assert r1["poly_delta_10m"] is None


def test_451_is_fail_closed():
    def handler(request):
        return httpx.Response(451, text="Unavailable For Legal Reasons", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        try:
            pm.fetch_gamma_markets(
                {
                    "provider": {
                        "gamma_markets_url": "https://example.test/markets",
                        "max_markets": 5,
                        "page_size": 5,
                    },
                    "quality_gate": {"min_liquidity_usd": 5000},
                },
                client=client,
            )
        except pm.LegalAccessRestricted as exc:
            assert "451" in str(exc)
        else:
            raise AssertionError("451 must fail closed")


def test_blocked_payload_cannot_trade():
    p = pm.blocked_payload(
        datetime(2026, 10, 7, 11, 40, tzinfo=UTC), "HTTP 451"
    )
    assert p["status"] == "BLOCKED_LEGAL_ACCESS"
    assert p["record_count"] == 0
    assert p["safety"]["read_only"] is True
    assert p["safety"]["trade_execution_enabled"] is False
    assert p["safety"]["geoblock_bypass_attempted"] is False
