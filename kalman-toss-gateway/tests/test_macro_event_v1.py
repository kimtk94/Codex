from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.macro_event.build_macro_event_features import build_event_features
from research.macro_event.merge_macro_v4 import decision_cutoffs, merge_market_matrix


def spec():
    return {
        "version": "test",
        "surprise_z_min_history": 2,
        "surprise_z_clip": 6.0,
        "max_event_age_hours": 168,
        "event_definitions": {
            "CPI_MOM": {
                "category": "INFLATION",
                "hawkish_sign": 1,
                "half_life_hours": 48,
            },
            "UNEMPLOYMENT_RATE": {
                "category": "LABOR",
                "hawkish_sign": -1,
                "half_life_hours": 48,
            },
        },
    }


def test_surprise_z_uses_prior_events_only():
    e = pd.DataFrame(
        {
            "event_id": ["a", "b", "c", "d"],
            "event_type": ["CPI_MOM"] * 4,
            "release_time": pd.to_datetime(
                [
                    "2020-01-01 13:30Z",
                    "2020-02-01 13:30Z",
                    "2020-03-01 13:30Z",
                    "2020-04-01 13:30Z",
                ]
            ),
            "available_time": pd.to_datetime(
                [
                    "2020-01-01 13:30Z",
                    "2020-02-01 13:30Z",
                    "2020-03-01 13:30Z",
                    "2020-04-01 13:30Z",
                ]
            ),
            "actual": [1.0, 2.0, 3.0, 100.0],
            "consensus": [0.0, 0.0, 0.0, 0.0],
        }
    )
    out = build_event_features(e, spec())
    third = out.loc[out.event_id == "c"].iloc[0]
    prior_std = np.std([1.0, 2.0], ddof=1)
    assert np.isclose(third.surprise_scale_prior, prior_std)
    assert np.isclose(third.surprise_z, 3.0 / prior_std)


def test_hawkish_sign_inverts_unemployment_surprise():
    e = pd.DataFrame(
        {
            "event_id": ["u1", "u2", "u3"],
            "event_type": ["UNEMPLOYMENT_RATE"] * 3,
            "release_time": pd.to_datetime(
                [
                    "2020-01-01 13:30Z",
                    "2020-02-01 13:30Z",
                    "2020-03-01 13:30Z",
                ]
            ),
            "available_time": pd.to_datetime(
                [
                    "2020-01-01 13:30Z",
                    "2020-02-01 13:30Z",
                    "2020-03-01 13:30Z",
                ]
            ),
            "actual": [4.0, 4.2, 4.6],
            "consensus": [4.1, 4.1, 4.1],
        }
    )
    out = build_event_features(e, spec())
    last = out.iloc[-1]
    assert last.surprise_z > 0
    assert last.hawkish_surprise_z < 0


def test_us_cutoff_respects_dst():
    s = pd.Series(
        pd.to_datetime(["2026-01-15", "2026-07-15"], utc=True)
    )
    cut = decision_cutoffs(s, "US")
    assert cut[0].hour == 21
    assert cut[1].hour == 20


def _event(available_time: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_id": ["event"],
            "category": ["INFLATION"],
            "available_time": pd.to_datetime([available_time]),
            "hawkish_surprise_z": [1.5],
            "half_life_hours": [48.0],
            "us2y_5m_bp": [5.0],
            "us2y_30m_bp": [8.0],
            "fed_reprice_30m_bp": [6.0],
            "fed_reprice_next_bp": [5.0],
            "rates_confirmation_30m_bp": [8.0],
            "policy_confirmation_30m_bp": [6.0],
            "nq_5m_ret": [-0.004],
            "soxx_5m_ret": [-0.006],
            "dxy_5m_ret": [0.003],
            "gold_5m_ret": [-0.002],
            "btc_5m_ret": [-0.005],
        }
    )


def test_event_after_us_close_does_not_leak_same_day():
    matrix = pd.DataFrame(
        {
            "as_of": pd.to_datetime(
                ["2026-09-10", "2026-09-11", "2026-09-14"], utc=True
            ),
            "anchor_close": [100, 101, 102],
            "target_forward_return": [0.01, 0.01, np.nan],
            "target_label": [1, 1, np.nan],
        }
    )
    out = merge_market_matrix(
        matrix,
        _event("2026-09-11 21:30Z"),
        market="US",
        max_age_hours=168,
    )
    assert out.loc[1, "macro__inflation_shock"] == 0.0
    assert out.loc[1, "macro__active_event_window"] == 0.0
    assert out.loc[2, "macro__inflation_shock"] > 0
    assert out.loc[2, "macro__active_event_window"] == 1.0


def test_event_before_us_close_is_available_same_day():
    matrix = pd.DataFrame(
        {
            "as_of": pd.to_datetime(["2026-09-11"], utc=True),
            "anchor_close": [100],
            "target_forward_return": [0.01],
            "target_label": [1],
        }
    )
    out = merge_market_matrix(
        matrix,
        _event("2026-09-11 12:30Z"),
        market="US",
        max_age_hours=168,
    )
    assert out.loc[0, "macro__inflation_shock"] > 0
    reaction = out.loc[0, "macro__us2y_30m_bp_latest"]
    assert 0.0 < reaction < 8.0


def test_unavailable_reaction_source_remains_nan_not_fake_zero():
    matrix = pd.DataFrame(
        {
            "as_of": pd.to_datetime(["2026-09-11", "2026-09-14"], utc=True),
            "anchor_close": [100, 101],
            "target_forward_return": [0.01, np.nan],
            "target_label": [1, np.nan],
        }
    )
    events = _event("2026-09-11 12:30Z")
    events["us2y_30m_bp"] = np.nan
    out = merge_market_matrix(
        matrix,
        events,
        market="US",
        max_age_hours=168,
    )
    assert out["macro__us2y_30m_bp_latest"].isna().all()


def test_available_reaction_source_is_zero_outside_active_window():
    matrix = pd.DataFrame(
        {
            "as_of": pd.to_datetime(["2026-09-01", "2026-09-11"], utc=True),
            "anchor_close": [99, 100],
            "target_forward_return": [0.0, np.nan],
            "target_label": [0, np.nan],
        }
    )
    out = merge_market_matrix(
        matrix,
        _event("2026-09-11 12:30Z"),
        market="US",
        max_age_hours=168,
    )
    assert out.loc[0, "macro__us2y_30m_bp_latest"] == 0.0
    assert out.loc[1, "macro__us2y_30m_bp_latest"] > 0.0
