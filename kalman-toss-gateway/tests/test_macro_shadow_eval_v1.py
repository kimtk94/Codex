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
