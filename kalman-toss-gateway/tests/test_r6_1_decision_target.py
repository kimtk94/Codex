import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))

import r6_1_decision_target as r6


def test_positive_returns_have_zero_mdd():
    assert r6.max_dd([0.01, 0.02, 0.03]) == 0.0


def test_holm_adjust_is_bounded_and_monotone_by_rank():
    p = np.array([0.01, 0.04, 0.20])
    adj = r6.holm_adjust(p)
    assert np.all((adj >= 0) & (adj <= 1))
    assert adj[0] <= adj[1] <= adj[2]


def test_gap_features_stop_first_conservative():
    seq = np.arange(0, 8)
    t = pd.date_range("2026-01-01", periods=len(seq), freq="h", tz="UTC")
    close = np.full(len(seq), 100.0)
    high = np.full(len(seq), 101.0)
    low = np.full(len(seq), 99.0)

    # For decision at seq=0, the first future bar touches both stop and TP.
    high[1] = 125.0
    low[1] = 95.0

    obs = pd.DataFrame({
        "expected_seq": seq,
        "timestamp": t,
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.full(len(seq), 1000.0),
    })
    q_ts = pd.Series(t, index=seq)
    out = r6.gap_features(obs, q_ts)
    row = out.loc[out["expected_seq"] == 0].iloc[0]
    assert abs(float(row["proxy_ret_4b"]) - r6.STOP) < 1e-12


def test_gap_features_time_exit_when_no_barrier():
    seq = np.arange(0, 8)
    t = pd.date_range("2026-01-01", periods=len(seq), freq="h", tz="UTC")
    close = np.array([100, 100, 100, 100, 102, 102, 102, 102], dtype=float)
    obs = pd.DataFrame({
        "expected_seq": seq,
        "timestamp": t,
        "open": close,
        "high": close * 1.005,
        "low": close * 0.995,
        "close": close,
        "volume": np.full(len(seq), 1000.0),
    })
    q_ts = pd.Series(t, index=seq)
    out = r6.gap_features(obs, q_ts)
    row = out.loc[out["expected_seq"] == 0].iloc[0]
    assert abs(float(row["proxy_ret_4b"]) - 0.02) < 1e-12
