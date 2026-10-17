from pathlib import Path

import numpy as np
import pandas as pd

from research.quant_stack import prediction_market_archive_v0 as archive
from research.quant_stack import prediction_market_leadlag_v0 as leadlag
from research.quant_stack import prediction_market_stratified_v0 as stratified


def config():
    return {
        "theme_keywords": {
            "FED_POLICY": ["fed", "federal reserve", "fomc", "interest rate", "rate cut"],
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
    }


def metadata():
    return pd.DataFrame(
        [
            {
                "slug": "fed-cut",
                "question": "Will the Fed cut interest rates?",
                "category": "macro",
                "theme": "FED_POLICY",
                "semantic_channel": "FED_EASING",
                "risk_prior_sign": 1,
            },
            {
                "slug": "sports-market",
                "question": "Who wins?",
                "category": "sports",
                "theme": "OTHER",
                "semantic_channel": "UNMAPPED",
                "risk_prior_sign": None,
            },
        ]
    )


def quote_rows():
    times = pd.date_range("2026-08-01T12:00:00Z", periods=7, freq="10min")
    rows = []
    probs = [0.40, 0.42, 0.43, 0.44, 0.46, 0.48, 0.55]
    for ts, p in zip(times, probs):
        rows.append(
            {
                "ts": ts,
                "slug": "fed-cut",
                "category": "macro",
                "bid": p - 0.01,
                "ask": p + 0.01,
                "mid": p,
                "spread": 0.02,
                "volume24hr": np.nan,
                "segment": 2,
            }
        )
    return pd.DataFrame(rows)


def test_archive_normalization_and_exact_one_hour_delta():
    out = archive.normalize_quotes(
        quote_rows(),
        metadata(),
        config=config(),
        categories={"macro"},
    )
    assert len(out) == 7
    last = out.iloc[-1]
    assert round(float(last["poly_delta_1h"]), 12) == 0.15
    assert last["quote_price_kind"] == "MIDPOINT_NOT_TRADE"
    assert bool(last["traded_price_available"]) is False
    assert last["volume24hr_quality"] == "MISSING_KNOWN_DATASET_LIMITATION"
    assert last["known_gap_guard"] == "SEGMENT_SCOPED"


def test_crossed_book_is_removed():
    q = quote_rows().iloc[:1].copy()
    q.loc[q.index[0], "bid"] = 0.60
    q.loc[q.index[0], "ask"] = 0.50
    out = archive.normalize_quotes(
        q,
        metadata(),
        config=config(),
        categories={"macro"},
    )
    assert out.empty


def test_delta_never_crosses_segment_boundary():
    q = pd.DataFrame(
        [
            {
                "ts": pd.Timestamp("2026-07-17T17:20:00Z"),
                "slug": "fed-cut",
                "category": "macro",
                "bid": 0.39,
                "ask": 0.41,
                "mid": 0.40,
                "spread": 0.02,
                "volume24hr": 1.0,
                "segment": 1,
            },
            {
                "ts": pd.Timestamp("2026-07-22T10:40:00Z"),
                "slug": "fed-cut",
                "category": "macro",
                "bid": 0.69,
                "ask": 0.71,
                "mid": 0.70,
                "spread": 0.02,
                "volume24hr": np.nan,
                "segment": 2,
            },
        ]
    )
    out = archive.normalize_quotes(
        q,
        metadata(),
        config=config(),
        categories={"macro"},
    )
    assert out["poly_delta_10m"].isna().all()
    assert out["poly_delta_1h"].isna().all()


def test_build_event_hours_converts_probability_move_to_risk_shift():
    pm = pd.DataFrame(
        [
            {
                "ts": "2026-08-01T14:10:00Z",
                "slug": "fed-cut",
                "theme": "FED_POLICY",
                "semantic_channel": "FED_EASING",
                "risk_prior_sign": 1,
                "poly_delta_1h": 0.10,
            },
            {
                "ts": "2026-08-01T14:20:00Z",
                "slug": "recession",
                "theme": "RECESSION_GROWTH",
                "semantic_channel": "RECESSION_RISK",
                "risk_prior_sign": -1,
                "poly_delta_1h": 0.08,
            },
        ]
    )
    events = leadlag.build_event_hours(pm, min_abs_delta_1h=0.05)
    assert len(events) == 1
    # Mean of +0.10 risk-on Fed easing and -0.08 recession-risk shift.
    assert round(float(events.iloc[0]["event_score"]), 12) == 0.01
    assert int(events.iloc[0]["market_count"]) == 2


def test_asset_alignment_uses_first_bar_at_or_after_event():
    events = pd.DataFrame(
        [
            {
                "event_hour": pd.Timestamp("2026-08-03T13:00:00Z"),
                "event_score": 0.2,
                "market_count": 1,
                "mean_abs_delta_1h": 0.2,
                "dominant_channel": "FED_EASING",
                "dominant_theme": "FED_POLICY",
            }
        ]
    )
    asset = pd.DataFrame(
        {
            "ts": pd.to_datetime(
                [
                    "2026-08-03T12:00:00Z",
                    "2026-08-03T13:30:00Z",
                    "2026-08-03T14:30:00Z",
                    "2026-08-03T15:30:00Z",
                    "2026-08-03T16:30:00Z",
                    "2026-08-03T17:30:00Z",
                    "2026-08-03T18:30:00Z",
                    "2026-08-03T19:30:00Z",
                    "2026-08-03T20:30:00Z",
                ],
                utc=True,
            ),
            "price": [99, 100, 101, 102, 103, 104, 105, 106, 107],
            "symbol": "QQQ",
        }
    )
    for bars in (1, 4, 7):
        asset[f"fwd_return_{bars}bar"] = asset["price"].shift(-bars) / asset["price"] - 1
    aligned = leadlag.align_asset(events, asset)
    assert aligned.iloc[0]["price"] == 100
    assert aligned.iloc[0]["entry_lag_minutes"] == 30
    assert round(float(aligned.iloc[0]["fwd_return_1bar"]), 12) == 0.01


def test_us2y_confirmation_only_applies_to_fed_direction():
    events = pd.DataFrame(
        [
            {
                "event_hour": pd.Timestamp("2026-08-03T14:00:00Z"),
                "event_score": 0.2,
                "market_count": 1,
                "mean_abs_delta_1h": 0.2,
                "dominant_channel": "FED_EASING",
                "dominant_theme": "FED_POLICY",
            },
            {
                "event_hour": pd.Timestamp("2026-08-04T14:00:00Z"),
                "event_score": -0.2,
                "market_count": 1,
                "mean_abs_delta_1h": 0.2,
                "dominant_channel": "RECESSION_RISK",
                "dominant_theme": "RECESSION_GROWTH",
            },
        ]
    )
    rates = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2026-08-03T12:00:00Z", "2026-08-04T12:00:00Z"], utc=True),
            "us2y_change_bps": [-5.0, -7.0],
        }
    )
    out = leadlag.attach_us2y(events, rates)
    assert bool(out.iloc[0]["us2y_confirmation"]) is True
    assert pd.isna(out.iloc[1]["us2y_confirmation"])


def test_dynamic_asset_loader_accepts_kalman_style_columns(tmp_path: Path):
    path = tmp_path / "QQQ.csv"
    pd.DataFrame(
        {
            "datetime": ["2026-08-03T13:00:00Z", "2026-08-03T14:00:00Z"],
            "open": [100, 101],
            "high": [101, 102],
            "low": [99, 100],
            "close": [100.5, 101.5],
        }
    ).to_csv(path, index=False)
    out = leadlag.load_asset_history(path, "QQQ")
    assert list(out["symbol"].unique()) == ["QQQ"]
    assert list(out["price"]) == [100.5, 101.5]


def test_dynamic_asset_loader_accepts_compact_t_c_columns(tmp_path: Path):
    path = tmp_path / "QQQ_compact.csv"
    pd.DataFrame(
        {
            "t": ["2026-08-03T13:00:00Z", "2026-08-03T14:00:00Z"],
            "o": [100, 101],
            "h": [101, 102],
            "l": [99, 100],
            "c": [100.5, 101.5],
        }
    ).to_csv(path, index=False)
    out = leadlag.load_asset_history(path, "QQQ")
    assert list(out["price"]) == [100.5, 101.5]


def test_near_session_summary_filters_long_entry_lag():
    frame = pd.DataFrame(
        {
            "event_score": [0.2, -0.2],
            "price": [100.0, 100.0],
            "entry_lag_minutes": [60.0, 180.0],
            "fwd_return_1bar": [0.01, -0.01],
            "fwd_return_4bar": [0.02, -0.02],
            "fwd_return_7bar": [0.03, -0.03],
        }
    )
    all_rows = leadlag.summarize_aligned(frame, "QQQ")
    near = leadlag.summarize_aligned(frame, "QQQ", max_entry_lag_minutes=90)
    assert all_rows["aligned_rows"] == 2
    assert near["aligned_rows"] == 1
    assert near["median_entry_lag_minutes"] == 60.0


def test_fred_dgs2_date_is_available_at_new_york_close(tmp_path: Path):
    path = tmp_path / "DGS2.csv"
    pd.DataFrame(
        {
            "observation_date": ["2026-08-03", "2026-08-04"],
            "DGS2": [4.00, 3.95],
        }
    ).to_csv(path, index=False)
    out = leadlag.load_us2y(path)
    assert out.iloc[0]["ts"] == pd.Timestamp("2026-08-03T20:00:00Z")
    assert round(float(out.iloc[1]["us2y_change_bps"]), 8) == -5.0


def test_cluster_signflip_reports_positive_date_rate():
    frame = pd.DataFrame(
        {
            "event_at": pd.to_datetime(
                [
                    "2026-08-03T14:00:00Z",
                    "2026-08-04T14:00:00Z",
                    "2026-08-05T14:00:00Z",
                    "2026-08-06T14:00:00Z",
                ],
                utc=True,
            ),
            "signed_return": [0.01, 0.02, 0.015, 0.005],
        }
    )
    p, positive_rate = stratified.cluster_signflip_p(
        frame,
        "signed_return",
        date_col="event_at",
    )
    assert 0.0 < float(p) <= 1.0
    assert positive_rate == 1.0


def test_benjamini_hochberg_is_monotone_and_bounded():
    p = pd.Series([0.01, 0.02, 0.5], index=["a", "b", "c"])
    q = stratified.benjamini_hochberg(p)
    assert 0.0 <= q.min() <= q.max() <= 1.0
    assert q["a"] <= q["b"] <= q["c"]


def test_promotion_gate_requires_fdr():
    matrix = pd.DataFrame(
        [
            {
                "n": 30,
                "unique_dates": 10,
                "hit_rate": 0.65,
                "positive_date_rate": 0.8,
                "mean_signed_return": 0.004,
                "bootstrap_ci_low": 0.001,
                "fdr_q": 0.5,
            }
        ]
    )
    out = stratified.promotion_candidates(matrix)
    assert out.empty
