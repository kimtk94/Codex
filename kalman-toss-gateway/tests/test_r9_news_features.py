import pandas as pd

from research.r9_news_features import (
    NEWS_FEATURES,
    attach_news_features,
    build_daily_features,
)


def test_calendar_completion_and_missing_symbol_zero_fill():
    mentions = pd.DataFrame([
        {"symbol": "AAA", "day_utc": 20240801, "mention_count": 3},
        {"symbol": "AAA", "day_utc": 20240803, "mention_count": 1},
    ])
    daily = build_daily_features(
        mentions,
        ["AAA", "BBB"],
        history_start=pd.Timestamp("2024-08-01", tz="UTC"),
        history_end_exclusive=pd.Timestamp("2024-08-05", tz="UTC"),
    )
    a = daily.loc[daily["symbol"] == "AAA"].set_index("day")
    b = daily.loc[daily["symbol"] == "BBB"].set_index("day")
    assert float(a.loc[pd.Timestamp("2024-08-02", tz="UTC"), "mention_count"]) == 0.0
    assert float(b["mention_count"].sum()) == 0.0
    assert set(NEWS_FEATURES).issubset(daily.columns)


def test_attach_uses_prior_utc_day_only():
    mentions = pd.DataFrame([
        {"symbol": "AAA", "day_utc": 20240801, "mention_count": 1},
        {"symbol": "AAA", "day_utc": 20240802, "mention_count": 7},
    ])
    daily = build_daily_features(
        mentions,
        ["AAA"],
        history_start=pd.Timestamp("2024-08-01", tz="UTC"),
        history_end_exclusive=pd.Timestamp("2024-08-04", tz="UTC"),
    )
    frame = pd.DataFrame([
        {"symbol": "AAA", "timestamp": "2024-08-02T13:30:00Z"},
    ])
    out, audit = attach_news_features(frame, daily)
    assert out.loc[0, "news_day_used"] == pd.Timestamp("2024-08-01", tz="UTC")
    expected = daily.loc[
        (daily["symbol"] == "AAA")
        & (daily["day"] == pd.Timestamp("2024-08-01", tz="UTC")),
        "ngram_log1p_d1",
    ].iloc[0]
    assert out.loc[0, "ngram_log1p_d1"] == expected
    assert audit["same_day_forbidden"] is True


def test_same_day_mention_change_cannot_change_signal_feature():
    base = pd.DataFrame([
        {"symbol": "AAA", "day_utc": 20240801, "mention_count": 2},
        {"symbol": "AAA", "day_utc": 20240802, "mention_count": 1},
    ])
    altered = base.copy()
    altered.loc[altered["day_utc"] == 20240802, "mention_count"] = 999999

    kwargs = {
        "history_start": pd.Timestamp("2024-08-01", tz="UTC"),
        "history_end_exclusive": pd.Timestamp("2024-08-04", tz="UTC"),
    }
    d1 = build_daily_features(base, ["AAA"], **kwargs)
    d2 = build_daily_features(altered, ["AAA"], **kwargs)
    frame = pd.DataFrame([
        {"symbol": "AAA", "timestamp": "2024-08-02T13:30:00Z"},
    ])
    x1, _ = attach_news_features(frame, d1)
    x2, _ = attach_news_features(frame, d2)
    for col in NEWS_FEATURES:
        assert x1.loc[0, col] == x2.loc[0, col]


def test_duplicate_symbol_day_rejected():
    mentions = pd.DataFrame([
        {"symbol": "AAA", "day_utc": 20240801, "mention_count": 1},
        {"symbol": "AAA", "day_utc": 20240801, "mention_count": 2},
    ])
    try:
        build_daily_features(
            mentions,
            ["AAA"],
            history_start=pd.Timestamp("2024-08-01", tz="UTC"),
            history_end_exclusive=pd.Timestamp("2024-08-03", tz="UTC"),
        )
        assert False, "expected duplicate rejection"
    except ValueError as exc:
        assert "duplicate" in str(exc).lower()
