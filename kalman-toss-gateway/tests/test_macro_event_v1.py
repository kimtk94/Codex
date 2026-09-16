import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.macro_event.build_macro_event_features import build_event_features
from research.macro_event.merge_macro_v4 import (
    build_rates_context_panel,
    decision_cutoffs,
    merge_market_matrix,
)
from research.macro_event.run_macro_v4 import _macro_selection_summary


def spec():
    return {
        "version": "test",
        "surprise_z_min_history": 2,
        "surprise_z_clip": 6.0,
        "release_shock_z_min_history": 2,
        "release_shock_z_clip": 6.0,
        "max_event_age_hours": 168,
        "event_definitions": {
            "CPI_MOM": {
                "category": "INFLATION",
                "hawkish_sign": 1,
                "half_life_hours": 48,
                "release_transform": "pct_change",
            },
            "UNEMPLOYMENT_RATE": {
                "category": "LABOR",
                "hawkish_sign": -1,
                "half_life_hours": 48,
                "release_transform": "diff",
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
            "macro_signal_z": [1.5],
            "hawkish_surprise_z": [np.nan],
            "release_shock_z": [1.5],
            "hawkish_release_shock_z": [1.5],
            "half_life_hours": [48.0],
            "us2y_daily_bp": [6.0],
            "rates_confirmation_daily_bp": [6.0],
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


def test_macro_selection_summary(tmp_path):
    market_dir = tmp_path / "us"
    market_dir.mkdir(parents=True)
    (market_dir / "fold_metrics.json").write_text(
        json.dumps(
            [
                {
                    "outer_fold": {"fold_id": 1},
                    "selected_features": [
                        "yf_spy__ret5",
                        "macro__inflation_shock",
                        "macro__event_count_72h",
                    ],
                },
                {
                    "outer_fold": {"fold_id": 2},
                    "selected_features": ["yf_spy__ret20"],
                },
            ]
        ),
        encoding="utf-8",
    )
    out = _macro_selection_summary(tmp_path, "US")
    assert out["fold_count"] == 2
    assert out["folds_with_macro"] == 1
    assert out["macro_fold_share"] == 0.5
    assert out["selected_macro_features"] == [
        "macro__event_count_72h",
        "macro__inflation_shock",
    ]



def test_model_safe_rates_context_does_not_backfill_before_available_date():
    rates = pd.DataFrame(
        {
            "date": ["2017-01-03", "2017-01-04", "2017-01-05", "2017-01-06"],
            "us_treasury_2y": [np.nan, np.nan, 1.22, 1.24],
            "us_treasury_10y": [np.nan, np.nan, 2.45, 2.46],
            "us_10y_2y_spread": [np.nan, np.nan, 1.23, 1.22],
            "us_fed_funds_effective": [0.55, 0.55, 0.66, 0.66],
            "us_treasury_2y_available_flag": [0, 0, 1, 1],
            "us_treasury_2y_changed_flag": [0, 0, 1, 1],
        }
    )
    as_of = pd.Series(
        pd.to_datetime(
            ["2017-01-03", "2017-01-05", "2017-01-06"], utc=True
        )
    )
    panel = build_rates_context_panel(as_of, rates)
    assert pd.isna(panel.loc[0, "rates__us2y_level"])
    assert panel.loc[1, "rates__us2y_level"] == 1.22
    assert panel.loc[2, "rates__us2y_level"] == 1.24
    assert np.isclose(panel.loc[2, "rates__us2y_chg1d_bp"], 2.0)
    assert panel.loc[1, "rates__us2y_available_flag"] == 1


def test_rates_context_keeps_event_reaction_namespace_separate():
    rates = pd.DataFrame(
        {
            "date": ["2026-09-11"],
            "us_treasury_2y": [4.43],
            "us_treasury_10y": [4.83],
            "us_10y_2y_spread": [0.40],
        }
    )
    panel = build_rates_context_panel(
        pd.Series(pd.to_datetime(["2026-09-11"], utc=True)),
        rates,
    )
    assert "rates__us2y_level" in panel.columns
    assert "macro__us2y_30m_bp_latest" not in panel.columns


def test_free_release_shock_fallback_without_consensus():
    e = pd.DataFrame(
        {
            "event_id": ["f1", "f2", "f3", "f4"],
            "event_type": ["CPI_MOM"] * 4,
            "release_time": pd.to_datetime(
                [
                    "2020-01-14 13:30Z",
                    "2020-02-13 13:30Z",
                    "2020-03-11 12:30Z",
                    "2020-04-10 12:30Z",
                ]
            ),
            "available_time": pd.to_datetime(
                [
                    "2020-01-14 13:30Z",
                    "2020-02-13 13:30Z",
                    "2020-03-11 12:30Z",
                    "2020-04-10 12:30Z",
                ]
            ),
            "actual": [100.0, 101.0, 103.0, 104.0],
        }
    )
    out = build_event_features(e, spec())
    last = out.iloc[-1]
    assert pd.isna(last["surprise_z"])
    assert np.isfinite(last["release_shock_z"])
    assert np.isfinite(last["macro_signal_z"])
    assert last["signal_source"] == "INITIAL_RELEASE_CHANGE_PROXY"


def test_free_unemployment_release_direction_is_hawkish_when_rate_falls():
    e = pd.DataFrame(
        {
            "event_id": ["u1", "u2", "u3", "u4"],
            "event_type": ["UNEMPLOYMENT_RATE"] * 4,
            "release_time": pd.to_datetime(
                [
                    "2020-01-03 13:30Z",
                    "2020-02-07 13:30Z",
                    "2020-03-06 13:30Z",
                    "2020-04-03 12:30Z",
                ]
            ),
            "available_time": pd.to_datetime(
                [
                    "2020-01-03 13:30Z",
                    "2020-02-07 13:30Z",
                    "2020-03-06 13:30Z",
                    "2020-04-03 12:30Z",
                ]
            ),
            "actual": [4.0, 4.2, 4.6, 4.5],
        }
    )
    out = build_event_features(e, spec())
    last = out.iloc[-1]
    assert last["release_change_raw"] < 0
    assert last["release_shock_z"] < 0
    assert last["hawkish_release_shock_z"] > 0
    assert last["macro_signal_z"] > 0
