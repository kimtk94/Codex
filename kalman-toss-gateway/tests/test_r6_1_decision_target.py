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


def _toy_rows(both=False, time_exit=False):
    seq = np.arange(0, 8)
    t = pd.date_range("2026-01-01", periods=len(seq), freq="h", tz="UTC")
    close = np.full(len(seq), 100.0)
    if time_exit:
        close[4:] = 102.0

    high = close * 1.005
    low = close * 0.995
    if both:
        high[1] = 125.0
        low[1] = 95.0

    fwd = np.full(len(seq), np.nan)
    for i in range(4):
        fwd[i] = close[i + 4] / close[i] - 1.0

    return pd.DataFrame({
        "symbol": ["X"] * len(seq),
        "expected_seq": seq,
        "timestamp": t,
        "high": high,
        "low": low,
        "close": close,
        "fwd_ret_4b": fwd,
    })


def test_path_proxy_stop_first_conservative():
    out = r6.add_path_proxy(_toy_rows(both=True))
    row = out.loc[out["expected_seq"] == 0].iloc[0]
    assert bool(row["path_complete"])
    assert abs(float(row["proxy_ret_4b"]) - r6.STOP) < 1e-12


def test_path_proxy_time_exit_when_no_barrier():
    out = r6.add_path_proxy(_toy_rows(time_exit=True))
    row = out.loc[out["expected_seq"] == 0].iloc[0]
    assert bool(row["path_complete"])
    assert abs(float(row["proxy_ret_4b"]) - 0.02) < 1e-12


def test_schedule_audit_exact():
    t = pd.date_range("2026-01-01", periods=3, freq="4h", tz="UTC")
    a = pd.DataFrame({"timestamp": t, "fold": ["E1"] * 3})
    b = a.copy()
    x = r6.schedule_audit(a, b)
    assert x["exact_match"]
    assert x["matched_rows"] == 3
