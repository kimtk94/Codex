from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.quant_stack.r5_topk_portfolio_backtest import (
    PORTFOLIOS,
    PriceLookup,
    evaluate_portfolios,
    normalize_rankings,
    portfolio_weights,
    rank_diagnostics,
)


def test_portfolio_weight_contracts():
    scores = np.asarray([5.0, 3.0, 2.0, 1.0])
    expected = {
        "TOP1": [1.0, 0.0, 0.0, 0.0],
        "TOP2_EQUAL": [0.5, 0.5, 0.0, 0.0],
        "TOP3_EQUAL": [1 / 3, 1 / 3, 1 / 3, 0.0],
        "TOP3_50_30_20": [0.5, 0.3, 0.2, 0.0],
        "TOP3_SCORE_PROP": [0.5, 0.3, 0.2, 0.0],
        "TOP4_EQUAL": [0.25, 0.25, 0.25, 0.25],
    }

    assert set(expected) == set(PORTFOLIOS)

    for name, target in expected.items():
        got = portfolio_weights(name, scores)
        assert np.allclose(got, np.asarray(target))
        assert abs(float(got.sum()) - 1.0) < 1e-12


def test_score_prop_falls_back_to_equal_when_top3_nonpositive():
    got = portfolio_weights(
        "TOP3_SCORE_PROP",
        np.asarray([-1.0, -2.0, -3.0, -4.0]),
    )
    assert np.allclose(
        got,
        np.asarray([1 / 3, 1 / 3, 1 / 3, 0.0]),
    )


def test_rankings_are_sorted_by_score_and_ranked():
    frame = pd.DataFrame(
        {
            "expected_seq": [10, 10, 10, 10],
            "symbol": ["B", "A", "D", "C"],
            "score": [0.8, 0.9, 0.6, 0.7],
        }
    )

    got = normalize_rankings(frame)

    assert got["symbol"].tolist() == ["A", "B", "C", "D"]
    assert got["rank"].tolist() == [1, 2, 3, 4]


def test_friday_flat_prevents_weekend_hold(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()

    rows = pd.DataFrame(
        {
            "expected_seq": [100, 101, 102, 103, 104],
            "timestamp": pd.to_datetime(
                [
                    "2026-10-02T18:30:00Z",
                    "2026-10-02T19:30:00Z",
                    "2026-10-02T20:00:00Z",
                    "2026-10-05T13:30:00Z",
                    "2026-10-05T14:30:00Z",
                ],
                utc=True,
            ),
            "close": [100, 101, 102, 103, 104],
        }
    )

    rows.to_parquet(
        locked / "AAA_1h_gap_aware.parquet",
        index=False,
    )

    lookup = PriceLookup(locked)
    got = lookup.friday_flat_exit_seq(
        "AAA",
        100,
        104,
    )

    assert got == 102


def test_portfolio_evaluation_uses_same_common_admissions_and_cost():
    panel = pd.DataFrame(
        [
            {
                "expected_seq": 10,
                "fixed_exit_seq": 14,
                "actual_exit_seq": 14,
                "friday_flat_applied": False,
                "entry_timestamp": pd.Timestamp(
                    "2026-09-01T14:30:00Z"
                ),
                "exit_timestamp": pd.Timestamp(
                    "2026-09-01T18:30:00Z"
                ),
                "admission_timestamp": pd.Timestamp(
                    "2026-09-01T14:30:00Z"
                ),
                "rank1_symbol": "A",
                "rank1_score": 5.0,
                "rank1_raw_return": 0.10,
                "rank2_symbol": "B",
                "rank2_score": 3.0,
                "rank2_raw_return": 0.04,
                "rank3_symbol": "C",
                "rank3_score": 2.0,
                "rank3_raw_return": -0.02,
                "rank4_symbol": "D",
                "rank4_score": 1.0,
                "rank4_raw_return": 0.00,
            }
        ]
    )

    detail, summary = evaluate_portfolios(
        panel,
        cost_bps=10.0,
    )

    assert len(detail) == len(PORTFOLIOS)

    top1 = detail.loc[
        detail["portfolio"].eq("TOP1")
    ].iloc[0]
    weighted = detail.loc[
        detail["portfolio"].eq("TOP3_50_30_20")
    ].iloc[0]

    assert abs(float(top1["net_return"]) - 0.099) < 1e-12

    expected_weighted = (
        0.5 * 0.10
        + 0.3 * 0.04
        + 0.2 * -0.02
    )
    assert abs(
        float(weighted["gross_return"])
        - expected_weighted
    ) < 1e-12

    assert set(summary["portfolio"]) == set(PORTFOLIOS)


def test_rank_diagnostics_reports_excess_and_correlation():
    panel = pd.DataFrame(
        {
            "rank1_raw_return": [0.1, -0.1, 0.2],
            "rank2_raw_return": [0.05, -0.05, 0.1],
            "rank3_raw_return": [0.02, -0.02, 0.04],
            "rank4_raw_return": [0.0, -0.01, 0.01],
        }
    )

    stats, corr = rank_diagnostics(panel)

    assert len(stats) == 4
    assert len(corr) == 4

    rank2 = stats.loc[
        stats["rank"].eq(2)
    ].iloc[0]

    assert float(
        rank2["mean_excess_vs_rank1"]
    ) < 0
