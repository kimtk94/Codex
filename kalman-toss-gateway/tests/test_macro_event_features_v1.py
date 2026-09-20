from datetime import datetime, timezone

from engine import macro_event_features_v1 as macro


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
    assert coverage == 0.60


def test_feature_payload_activates_consensus_surprise():
    as_of = datetime(2026, 9, 20, 13, 0, tzinfo=UTC)
    releases = [
        {
            "indicator_key": "CPI_HEADLINE_YOY",
            "event_name": "CPI",
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
    assert coverage == 0.65


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
    as_of = datetime(2026, 9, 20, 13, 0, tzinfo=UTC)
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
    policy_rows = [
        {
            "event_name": "CPI",
            "available_at": datetime(2026, 9, 20, 12, 45, tzinfo=UTC),
            "repricing_bps": 8.0,
            "source": "fed_funds_futures",
            "horizon": "NEXT_FOMC",
        }
    ]
    features, coverage = macro.build_feature_payload(
        as_of=as_of,
        config=config(),
        macro_rows=[],
        release_rows=[],
        policy_rows=policy_rows,
        source_states=states,
        dgs2_observations=dgs2,
        dgs2_error=None,
        policy_rate_observations=dff,
        policy_rate_error=None,
    )
    assert features["fed_policy_repricing_bps"] == 8.0
    assert features["fed_policy_repricing_quality"] == "FUTURES_PROVIDER"
    assert features["fed_policy_repricing_source"] == "fed_funds_futures"
    assert features["policy_proxy_quality"] == "MARKET_RATE_MINUS_EFFECTIVE_RATE_PROXY"
    assert coverage == 0.75


def test_macro_shock_interaction_uses_surprise_and_us2y_reaction():
    as_of = datetime(2026, 9, 17, 18, 0, tzinfo=UTC)
    releases = [
        {
            "indicator_key": "CPI_HEADLINE_YOY",
            "event_name": "CPI",
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
