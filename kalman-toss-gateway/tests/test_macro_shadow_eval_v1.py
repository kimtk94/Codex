from datetime import datetime, timezone

from engine import macro_shadow_eval_v1 as shadow


UTC = timezone.utc


def config():
    return {
        "max_macro_snapshot_age_minutes": 30,
        "min_macro_coverage": 0.65,
        "regime_thresholds_bps": {
            "tightening": 10,
            "easing": -10,
            "mixed_min_abs": 5,
        },
    }


def test_free_macro_regimes_are_descriptive_only():
    cfg = config()
    assert shadow.classify_free_macro_regime(
        {"us2y_change_bps_1d": 12, "policy_proxy_change_bps_1d": 11}, cfg
    ) == "TIGHTENING"
    assert shadow.classify_free_macro_regime(
        {"us2y_change_bps_1d": -12, "policy_proxy_change_bps_1d": -11}, cfg
    ) == "EASING"
    assert shadow.classify_free_macro_regime(
        {"us2y_change_bps_1d": 8, "policy_proxy_change_bps_1d": -9}, cfg
    ) == "MIXED"
    assert shadow.classify_free_macro_regime(
        {"us2y_change_bps_1d": 3, "policy_proxy_change_bps_1d": -2}, cfg
    ) == "NEUTRAL"
    assert shadow.classify_free_macro_regime(
        {"us2y_change_bps_1d": None, "policy_proxy_change_bps_1d": -2}, cfg
    ) == "UNKNOWN"


def test_eval_status_requires_point_in_time_freshness_and_coverage():
    cfg = config()
    signal = datetime(2026, 9, 21, 14, 30, tzinfo=UTC)

    status, age = shadow.evaluation_status(
        signal_as_of=signal,
        macro_as_of=datetime(2026, 9, 21, 14, 15, tzinfo=UTC),
        coverage_confidence=0.65,
        config=cfg,
    )
    assert status == "READY"
    assert age == 900.0

    status, _ = shadow.evaluation_status(
        signal_as_of=signal,
        macro_as_of=datetime(2026, 9, 21, 13, 45, tzinfo=UTC),
        coverage_confidence=0.90,
        config=cfg,
    )
    assert status == "STALE_MACRO_SNAPSHOT"

    status, _ = shadow.evaluation_status(
        signal_as_of=signal,
        macro_as_of=datetime(2026, 9, 21, 14, 15, tzinfo=UTC),
        coverage_confidence=0.64,
        config=cfg,
    )
    assert status == "LOW_MACRO_COVERAGE"

    status, age = shadow.evaluation_status(
        signal_as_of=signal,
        macro_as_of=None,
        coverage_confidence=None,
        config=cfg,
    )
    assert status == "NO_MACRO_SNAPSHOT"
    assert age is None


def test_eval_id_is_deterministic():
    a = shadow.deterministic_eval_id(
        "11111111-1111-1111-1111-111111111111",
        "macro-event-feature-v1",
    )
    b = shadow.deterministic_eval_id(
        "11111111-1111-1111-1111-111111111111",
        "macro-event-feature-v1",
    )
    c = shadow.deterministic_eval_id(
        "22222222-2222-2222-2222-222222222222",
        "macro-event-feature-v1",
    )
    assert a == b
    assert a != c
    assert a.startswith("macro-eval-")


def test_sync_insert_placeholder_count_matches_params(monkeypatch):
    cfg = {
        "feature_version": "macro-event-feature-v1",
        "research_contract": {"observation_only": True},
        "regime_thresholds_bps": {
            "tightening": 10,
            "easing": -10,
            "mixed_min_abs": 5,
        },
        "max_macro_snapshot_age_minutes": 30,
        "min_macro_coverage": 0.65,
    }

    row = {
        "benchmark_id": "11111111-1111-1111-1111-111111111111",
        "market": "US",
        "strategy_version": "R5.1_BASE_HGB",
        "benchmark_name": "TOP1_4B_10BP",
        "signal_as_of": datetime(2026, 9, 21, 14, 30, tzinfo=UTC),
        "baseline_gross_return": 0.01,
        "baseline_net_return": 0.009,
        "benchmark_metadata": {},
        "macro_as_of": datetime(2026, 9, 21, 14, 15, tzinfo=UTC),
        "macro_run_id": "MACRO-TEST",
        "coverage_confidence": 0.65,
        "macro_features": {
            "us2y_change_bps_1d": 12.0,
            "policy_proxy_change_bps_1d": 11.0,
            "policy_proxy_spread_bps": 70.0,
            "official_macro_decay": 1.0,
            "broad_macro_decay": 2.0,
            "macro_event_free_reaction_score": 1.2,
            "macro_event_free_reaction_direction": "HAWKISH_TIGHTENING",
            "macro_event_free_reaction_ready": True,
        },
    }

    monkeypatch.setattr(shadow, "fetch_candidates", lambda conn, config: [row])

    calls = []

    class FakeConn:
        def execute(self, sql, params=None):
            calls.append((sql, params))
            return []
        def commit(self):
            pass

    result = shadow.sync_evaluations(FakeConn(), cfg)
    assert result["upserted"] == 1
    assert len(calls) == 1
    sql, params = calls[0]
    assert sql.count("%s") == len(params)
    assert len(params) == 24
