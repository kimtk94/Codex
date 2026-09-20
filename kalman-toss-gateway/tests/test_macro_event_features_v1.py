from datetime import datetime, timezone

from engine import macro_event_features_v1 as macro
from engine import macro_consensus_provider_v1 as consensus


UTC = timezone.utc


def config():
    return {
        "feature_version": "macro-event-feature-v1",
        "official_macro_sources": ["fed_monetary", "bls_cpi"],
        "broad_macro_sources": ["gdelt_global"],
        "half_life_hours": {
            "official_macro": 12,
            "broad_macro_news": 6,
            "surprise": 24,
        },
        "indicator_normalization": {
            "CPI_HEADLINE_YOY": {
                "scale": 0.1,
                "policy_sign": 1.0,
                "unit": "pct",
            },
            "UNEMPLOYMENT_RATE": {
                "scale": 0.1,
                "policy_sign": -1.0,
                "unit": "pct",
            },
        },
        "fred": {
            "enabled": True,
            "series_id": "DGS2",
            "policy_proxy_series_id": "DFF",
            "policy_proxy_label": "DGS2_MINUS_DFF",
            "reaction_quality": "DAILY_PROXY",
            "reaction_scale_bps": 5.0,
        },
        "coverage_weights": {
            "official_news": 0.35,
            "dgs2_daily_proxy": 0.20,
            "consensus_surprise_provider": 0.25,
            "fed_repricing_provider": 0.10,
            "fed_repricing_proxy": 0.10,
        },
    }


def test_decay_half_life():
    assert abs(macro.decay_weight(12, 12) - 0.5) < 1e-12
    assert abs(macro.decay_weight(24, 12) - 0.25) < 1e-12


def test_normalized_surprise_policy_direction():
    cfg = config()["indicator_normalization"]
    assert macro.normalized_surprise("CPI_HEADLINE_YOY", 3.2, 3.0, cfg) == 2.0
    assert macro.normalized_surprise("UNEMPLOYMENT_RATE", 4.2, 4.1, cfg) == -1.0
    assert macro.normalized_surprise("UNKNOWN", 1.0, 0.0, cfg) is None


def test_dgs2_daily_change_and_event_proxy():
    obs = macro.parse_fred_observations(
        {
            "observations": [
                {"date": "2026-09-15", "value": "4.67"},
                {"date": "2026-09-16", "value": "4.74"},
                {"date": "2026-09-17", "value": "4.67"},
                {"date": "2026-09-18", "value": "."},
            ]
        }
    )
    latest = macro.dgs2_latest_change(obs)
    assert latest["latest_date"] == "2026-09-17"
    assert round(latest["change_bps_1d"], 6) == -7.0

    reaction = macro.dgs2_event_reaction(
        obs, datetime(2026, 9, 17, 12, 30, tzinfo=UTC)
    )
    assert reaction["event_date_et"] == "2026-09-17"
    assert round(reaction["reaction_bps"], 6) == -7.0


def test_no_weekend_event_reaction_is_invented():
    obs = macro.parse_fred_observations(
        {
            "observations": [
                {"date": "2026-09-17", "value": "4.67"},
                {"date": "2026-09-18", "value": "4.65"},
            ]
        }
    )
    reaction = macro.dgs2_event_reaction(
        obs, datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    )
    assert reaction["event_date_et"] == "2026-09-20"
    assert reaction["reaction_bps"] is None


def test_feature_payload_is_challenger_only_and_partial_without_consensus():
    as_of = datetime(2026, 9, 20, 13, 0, tzinfo=UTC)
    macro_rows = [
        {
            "article_id": "a1",
            "source": "fed_monetary",
            "title": "Federal Reserve statement",
            "available_at": datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
            "importance": 1.0,
            "confidence": 1.0,
        },
        {
            "article_id": "a2",
            "source": "gdelt_global",
            "title": "Macro markets update",
            "available_at": datetime(2026, 9, 20, 12, 30, tzinfo=UTC),
            "importance": 0.5,
            "confidence": 0.5,
        },
    ]
    states = [
        {
            "source": "fed_monetary",
            "last_success_at": datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
            "last_error": None,
        },
        {
            "source": "bls_cpi",
            "last_success_at": datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
            "last_error": None,
        },
    ]
    obs = macro.parse_fred_observations(
        {
            "observations": [
                {"date": "2026-09-16", "value": "4.74"},
                {"date": "2026-09-17", "value": "4.67"},
            ]
        }
    )

    features, coverage = macro.build_feature_payload(
        as_of=as_of,
        config=config(),
        macro_rows=macro_rows,
        release_rows=[],
        policy_rows=[],
        source_states=states,
        dgs2_observations=obs,
        dgs2_error=None,
        policy_rate_observations=macro.parse_fred_observations(
            {
                "observations": [
                    {"date": "2026-09-16", "value": "5.00"},
                    {"date": "2026-09-17", "value": "5.00"},
                ]
            }
        ),
        policy_rate_error=None,
    )

    assert features["official_macro_count_6h"] == 1
    assert features["broad_macro_count_6h"] == 1
    assert features["policy_pressure_surprise_latest"] is None
    assert features["fed_policy_repricing_bps"] is None
    assert features["us2y_reaction_quality"] == "DAILY_PROXY"
    assert features["r51_scoring_enabled"] is False
    assert features["trade_execution_enabled"] is False
    assert features["challenger_only"] is True
    assert coverage == 0.65


def test_feature_payload_activates_consensus_surprise():
    as_of = datetime(2026, 9, 20, 13, 0, tzinfo=UTC)
    releases = [
        {
            "indicator_key": "CPI_HEADLINE_YOY",
            "event_name": "CPI",
            "market": "US",
            "actual": 3.2,
            "consensus": 3.0,
            "available_at": datetime(2026, 9, 20, 12, 30, tzinfo=UTC),
        }
    ]
    states = [
        {
            "source": "fed_monetary",
            "last_success_at": datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
            "last_error": None,
        },
        {
            "source": "bls_cpi",
            "last_success_at": datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
            "last_error": None,
        },
    ]
    features, coverage = macro.build_feature_payload(
        as_of=as_of,
        config=config(),
        macro_rows=[],
        release_rows=releases,
        policy_rows=[],
        source_states=states,
        dgs2_observations=[],
        dgs2_error="test",
        policy_rate_observations=[],
        policy_rate_error="test",
    )
    assert features["policy_pressure_surprise_latest"] == 2.0
    assert features["consensus_surprise_count_72h"] == 1
    assert coverage == 0.60


def test_policy_proxy_spread_change():
    dgs2 = macro.parse_fred_observations(
        {
            "observations": [
                {"date": "2026-09-16", "value": "4.74"},
                {"date": "2026-09-17", "value": "4.67"},
            ]
        }
    )
    dff = macro.parse_fred_observations(
        {
            "observations": [
                {"date": "2026-09-16", "value": "5.00"},
                {"date": "2026-09-17", "value": "4.98"},
            ]
        }
    )
    latest = macro.rate_spread_latest_change(dgs2, dff)
    assert round(latest["latest_spread_bps"], 6) == -31.0
    assert round(latest["change_bps_1d"], 6) == -5.0

    reaction = macro.rate_spread_event_reaction(
        dgs2, dff, datetime(2026, 9, 17, 12, 30, tzinfo=UTC)
    )
    assert round(reaction["reaction_bps"], 6) == -5.0


def test_feature_payload_prefers_external_repricing_provider():
    as_of = datetime(2026, 9, 17, 18, 0, tzinfo=UTC)
    cfg = config()
    cfg["policy_repricing_match_hours"] = 6
    releases = [
        {
            "indicator_key": "CPI_HEADLINE_YOY",
            "event_name": "CPI",
            "market": "US",
            "actual": 3.2,
            "consensus": 3.0,
            "available_at": datetime(2026, 9, 17, 12, 30, tzinfo=UTC),
        }
    ]
    states = [
        {
            "source": "fed_monetary",
            "last_success_at": datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
            "last_error": None,
        },
        {
            "source": "bls_cpi",
            "last_success_at": datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
            "last_error": None,
        },
    ]
    dgs2 = macro.parse_fred_observations(
        {
            "observations": [
                {"date": "2026-09-16", "value": "4.74"},
                {"date": "2026-09-17", "value": "4.80"},
            ]
        }
    )
    dff = macro.parse_fred_observations(
        {
            "observations": [
                {"date": "2026-09-16", "value": "5.00"},
                {"date": "2026-09-17", "value": "4.98"},
            ]
        }
    )
    policy_rows = [
        {
            "event_name": "CPI",
            "event_at": datetime(2026, 9, 17, 12, 30, tzinfo=UTC),
            "available_at": datetime(2026, 9, 17, 12, 45, tzinfo=UTC),
            "repricing_bps": 8.0,
            "source": "fed_funds_futures",
            "horizon": "NEXT_FOMC",
        }
    ]
    features, coverage = macro.build_feature_payload(
        as_of=as_of,
        config=cfg,
        macro_rows=[],
        release_rows=releases,
        policy_rows=policy_rows,
        source_states=states,
        dgs2_observations=dgs2,
        dgs2_error=None,
        policy_rate_observations=dff,
        policy_rate_error=None,
    )
    assert features["fed_policy_repricing_bps"] == 8.0
    assert features["fed_policy_repricing_quality"] == "FUTURES_PROVIDER_EVENT_MATCHED"
    assert features["fed_policy_repricing_source"] == "fed_funds_futures"
    assert features["fed_policy_repricing_event_gap_minutes"] == 0.0
    assert features["macro_event_signal_ready"] is True
    assert features["macro_event_signal_full_provider_ready"] is True
    assert features["macro_event_signal_quality"] == "FULL_PROVIDER_CONFIRMATION"
    assert features["policy_proxy_quality"] == "MARKET_RATE_MINUS_EFFECTIVE_RATE_PROXY"
    assert coverage == 1.0

def test_macro_shock_interaction_uses_surprise_and_us2y_reaction():
    as_of = datetime(2026, 9, 17, 18, 0, tzinfo=UTC)
    releases = [
        {
            "indicator_key": "CPI_HEADLINE_YOY",
            "event_name": "CPI",
            "market": "US",
            "actual": 3.2,
            "consensus": 3.0,
            "available_at": datetime(2026, 9, 17, 12, 30, tzinfo=UTC),
        }
    ]
    dgs2 = macro.parse_fred_observations(
        {
            "observations": [
                {"date": "2026-09-16", "value": "4.70"},
                {"date": "2026-09-17", "value": "4.80"},
            ]
        }
    )
    dff = macro.parse_fred_observations(
        {
            "observations": [
                {"date": "2026-09-16", "value": "5.00"},
                {"date": "2026-09-17", "value": "5.00"},
            ]
        }
    )
    features, _ = macro.build_feature_payload(
        as_of=as_of,
        config=config(),
        macro_rows=[],
        release_rows=releases,
        policy_rows=[],
        source_states=[],
        dgs2_observations=dgs2,
        dgs2_error=None,
        policy_rate_observations=dff,
        policy_rate_error=None,
    )
    assert features["policy_pressure_surprise_latest"] == 2.0
    assert round(features["us2y_event_reaction_z"], 6) == 2.0
    assert round(features["macro_shock_interaction"], 6) == 4.0
    assert features["policy_alignment"] == 1


def test_trading_economics_value_parser_preserves_model_units():
    assert consensus.parse_calendar_value("3.2%", "pct") == 3.2
    assert consensus.parse_calendar_value("178K", "thousands") == 178.0
    assert consensus.parse_calendar_value("7.2M", "thousands") == 7200.0
    assert consensus.parse_calendar_value("(0.4%)", "pct") == -0.4


def test_trading_economics_calendar_row_maps_actual_and_consensus():
    as_of = datetime(2026, 9, 17, 13, 0, tzinfo=UTC)
    cfg = config()
    cfg["trading_economics"] = {
        "enabled": True,
        "event_map": {
            "Inflation Rate YoY": "CPI_HEADLINE_YOY",
        },
    }
    row = {
        "CalendarId": "12345",
        "Date": "2026-09-17T12:30:00",
        "Country": "United States",
        "Category": "Inflation Rate",
        "Event": "Inflation Rate YoY",
        "Actual": "3.2%",
        "Previous": "3.1%",
        "Forecast": "3.0%",
        "TEForecast": "3.1%",
        "DateSpan": "0",
        "LastUpdate": "2026-09-17T12:30:05",
        "Unit": "%",
        "Ticker": "USCPIYOY",
        "Symbol": "USCPIYOY",
        "Source": "U.S. Bureau of Labor Statistics",
    }

    mapped = consensus.normalize_calendar_row(row, cfg, as_of)
    assert mapped is not None
    assert mapped["indicator_key"] == "CPI_HEADLINE_YOY"
    assert mapped["actual"] == 3.2
    assert mapped["consensus"] == 3.0
    assert mapped["previous"] == 3.1
    assert mapped["time_quality"] == "PROVIDER_RELEASE_TS"
    assert mapped["source"] == "trading_economics_calendar"


def test_consensus_provider_is_fail_closed_without_runtime_gate(monkeypatch):
    monkeypatch.setenv("KALMAN_MACRO_CONSENSUS_ENABLED", "false")
    rows, status = consensus.fetch_calendar_rows(
        {"trading_economics": {"enabled": True}},
        datetime(2026, 9, 20, 14, 0, tzinfo=UTC),
    )
    assert rows == []
    assert status["status"] == "DISABLED_RUNTIME"


def test_consensus_provider_active_window_is_quota_aware():
    provider = {
        "active_weekdays": [0, 1, 2, 3, 4],
        "active_window_utc": {"start": "12:00", "end": "16:15"},
    }
    assert consensus.within_active_window(
        datetime(2026, 9, 21, 12, 30, tzinfo=UTC), provider
    )
    assert not consensus.within_active_window(
        datetime(2026, 9, 21, 18, 0, tzinfo=UTC), provider
    )
    assert not consensus.within_active_window(
        datetime(2026, 9, 20, 13, 0, tzinfo=UTC), provider
    )


def test_consensus_provider_rejects_demo_credentials(monkeypatch):
    monkeypatch.setenv("KALMAN_MACRO_CONSENSUS_ENABLED", "true")
    monkeypatch.setenv("TRADING_ECONOMICS_API_KEY", "guest:guest")
    rows, status = consensus.fetch_calendar_rows(
        {
            "trading_economics": {
                "enabled": True,
                "active_weekdays": [0, 1, 2, 3, 4],
                "active_window_utc": {"start": "12:00", "end": "16:15"},
            }
        },
        datetime(2026, 9, 21, 12, 30, tzinfo=UTC),
    )
    assert rows == []
    assert status["status"] == "DEMO_CREDENTIALS_REJECTED"


def test_consensus_provider_error_redaction():
    exc = RuntimeError("request failed for ?c=secret-client:secret-key")
    text = consensus.sanitize_provider_error(exc, "secret-client:secret-key")
    assert "secret-client:secret-key" not in text
    assert "***" in text



def test_us2y_anchor_ignores_newer_bok_event():
    as_of = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
    cfg = config()
    cfg["us_reaction_anchor_sources"] = [
        "fed_monetary", "bls_cpi", "bls_employment", "bls_jolts", "bea_releases"
    ]
    official_rows = [
        {
            "source": "bls_cpi",
            "title": "Consumer Price Index",
            "available_at": datetime(2026, 9, 17, 12, 30, tzinfo=UTC),
        },
        {
            "source": "bok_statistics",
            "title": "Korea producer prices",
            "available_at": datetime(2026, 9, 17, 21, 0, tzinfo=UTC),
        },
    ]

    anchor, meta = macro.select_us_reaction_anchor([], official_rows, cfg)
    assert anchor == datetime(2026, 9, 17, 12, 30, tzinfo=UTC)
    assert meta["kind"] == "US_OFFICIAL_NEWS_PROXY"
    assert meta["source"] == "bls_cpi"


def test_us2y_anchor_is_none_when_only_non_us_official_event_exists():
    cfg = config()
    cfg["us_reaction_anchor_sources"] = [
        "fed_monetary", "bls_cpi", "bls_employment", "bls_jolts", "bea_releases"
    ]
    official_rows = [
        {
            "source": "bok_statistics",
            "title": "Korea producer prices",
            "available_at": datetime(2026, 9, 17, 21, 0, tzinfo=UTC),
        }
    ]
    anchor, meta = macro.select_us_reaction_anchor([], official_rows, cfg)
    assert anchor is None
    assert meta["kind"] == "NONE"


def test_structured_us_release_takes_precedence_for_us2y_anchor():
    cfg = config()
    cfg["us_reaction_anchor_sources"] = ["bls_cpi"]
    releases = [
        {
            "market": "US",
            "source": "trading_economics_calendar",
            "event_name": "Inflation Rate YoY",
            "indicator_key": "CPI_HEADLINE_YOY",
            "available_at": datetime(2026, 9, 17, 12, 30, tzinfo=UTC),
            "actual": 3.2,
            "consensus": 3.0,
        }
    ]
    official_rows = [
        {
            "source": "bls_cpi",
            "title": "Consumer Price Index",
            "available_at": datetime(2026, 9, 17, 12, 31, tzinfo=UTC),
        }
    ]
    anchor, meta = macro.select_us_reaction_anchor(releases, official_rows, cfg)
    assert anchor == datetime(2026, 9, 17, 12, 30, tzinfo=UTC)
    assert meta["kind"] == "STRUCTURED_US_RELEASE"
    assert meta["indicator_key"] == "CPI_HEADLINE_YOY"


def test_feature_payload_does_not_attribute_bok_event_to_us2y():
    as_of = datetime(2026, 9, 17, 22, 0, tzinfo=UTC)
    cfg = config()
    cfg["official_macro_sources"] = ["bok_statistics"]
    cfg["us_reaction_anchor_sources"] = ["fed_monetary", "bls_cpi"]
    dgs2 = macro.parse_fred_observations(
        {
            "observations": [
                {"date": "2026-09-16", "value": "4.74"},
                {"date": "2026-09-17", "value": "4.67"},
            ]
        }
    )
    dff = macro.parse_fred_observations(
        {
            "observations": [
                {"date": "2026-09-16", "value": "5.00"},
                {"date": "2026-09-17", "value": "5.00"},
            ]
        }
    )
    features, _ = macro.build_feature_payload(
        as_of=as_of,
        config=cfg,
        macro_rows=[
            {
                "article_id": "bok-1",
                "source": "bok_statistics",
                "title": "Korea producer prices",
                "available_at": datetime(2026, 9, 17, 21, 0, tzinfo=UTC),
                "importance": 1.0,
                "confidence": 1.0,
            }
        ],
        release_rows=[],
        policy_rows=[],
        source_states=[
            {
                "source": "bok_statistics",
                "last_success_at": datetime(2026, 9, 17, 21, 0, tzinfo=UTC),
                "last_error": None,
            }
        ],
        dgs2_observations=dgs2,
        dgs2_error=None,
        policy_rate_observations=dff,
        policy_rate_error=None,
    )
    assert features["reaction_anchor_kind"] == "NONE"
    assert features["us2y_event_reaction_bps"] is None
    assert features["policy_proxy_event_reaction_bps"] is None
    assert features["component_status"]["us2y_event_reaction"]["status"] == "NO_US_EVENT_ANCHOR"


def test_macro_schema_accepts_provider_timestamp_contract():
    schema = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "research" / "quant_stack" / "macro_event_features_v1.sql"
    ).read_text(encoding="utf-8")
    assert "PROVIDER_RELEASE_TS" in schema
    assert "PROVIDER_ESTIMATED_TS" in schema



def test_macro_event_signal_uses_policy_proxy_when_external_provider_missing():
    as_of = datetime(2026, 9, 17, 18, 0, tzinfo=UTC)
    releases = [
        {
            "indicator_key": "CPI_HEADLINE_YOY",
            "event_name": "CPI",
            "market": "US",
            "actual": 3.2,
            "consensus": 3.0,
            "available_at": datetime(2026, 9, 17, 12, 30, tzinfo=UTC),
        }
    ]
    dgs2 = macro.parse_fred_observations(
        {"observations": [
            {"date": "2026-09-16", "value": "4.70"},
            {"date": "2026-09-17", "value": "4.80"},
        ]}
    )
    dff = macro.parse_fred_observations(
        {"observations": [
            {"date": "2026-09-16", "value": "5.00"},
            {"date": "2026-09-17", "value": "4.98"},
        ]}
    )
    features, _ = macro.build_feature_payload(
        as_of=as_of,
        config=config(),
        macro_rows=[],
        release_rows=releases,
        policy_rows=[],
        source_states=[],
        dgs2_observations=dgs2,
        dgs2_error=None,
        policy_rate_observations=dff,
        policy_rate_error=None,
    )
    assert features["macro_event_signal_ready"] is True
    assert features["macro_event_signal_full_provider_ready"] is False
    assert features["macro_event_signal_quality"] == "DGS2_DFF_PROXY_CONFIRMATION"
    assert features["macro_event_signal_blockers"] == []
    assert features["component_status"]["fed_repricing_proxy"]["status"] == "READY_EVENT_MATCHED"


def test_macro_event_signal_is_blocked_without_consensus_surprise():
    as_of = datetime(2026, 9, 17, 18, 0, tzinfo=UTC)
    dgs2 = macro.parse_fred_observations(
        {"observations": [
            {"date": "2026-09-16", "value": "4.70"},
            {"date": "2026-09-17", "value": "4.80"},
        ]}
    )
    dff = macro.parse_fred_observations(
        {"observations": [
            {"date": "2026-09-16", "value": "5.00"},
            {"date": "2026-09-17", "value": "4.98"},
        ]}
    )
    features, _ = macro.build_feature_payload(
        as_of=as_of,
        config=config(),
        macro_rows=[
            {
                "article_id": "bls-1",
                "source": "bls_cpi",
                "title": "Consumer Price Index",
                "available_at": datetime(2026, 9, 17, 12, 30, tzinfo=UTC),
                "importance": 1.0,
                "confidence": 1.0,
            }
        ],
        release_rows=[],
        policy_rows=[],
        source_states=[],
        dgs2_observations=dgs2,
        dgs2_error=None,
        policy_rate_observations=dff,
        policy_rate_error=None,
    )
    assert features["reaction_anchor_kind"] == "US_OFFICIAL_NEWS_PROXY"
    assert features["macro_event_signal_ready"] is False
    assert "CONSENSUS_SURPRISE_UNAVAILABLE" in features["macro_event_signal_blockers"]


def test_policy_repricing_must_match_same_event_window():
    anchor = datetime(2026, 9, 17, 12, 30, tzinfo=UTC)
    rows = [
        {
            "event_name": "OLD_EVENT",
            "event_at": datetime(2026, 9, 16, 12, 30, tzinfo=UTC),
            "available_at": datetime(2026, 9, 16, 12, 45, tzinfo=UTC),
            "repricing_bps": 12.0,
        },
        {
            "event_name": "CPI",
            "event_at": datetime(2026, 9, 17, 12, 35, tzinfo=UTC),
            "available_at": datetime(2026, 9, 17, 12, 45, tzinfo=UTC),
            "repricing_bps": 7.0,
        },
    ]
    matched, gap = macro.select_matched_policy_repricing(rows, anchor, 6)
    assert matched is not None
    assert matched["event_name"] == "CPI"
    assert gap == 5.0

    stale, stale_gap = macro.select_matched_policy_repricing(rows[:1], anchor, 6)
    assert stale is None
    assert stale_gap is None
