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


def _write_panel(tmp_path, both=False, time_exit=False):
    canon = tmp_path / "canon"
    live = tmp_path / "live"
    canon.mkdir()
    live.mkdir()

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

    q = pd.DataFrame({
        "expected_seq": seq,
        "timestamp": t,
        "high": high,
        "low": low,
        "close": close,
    })
    q.to_parquet(canon / "X_1h_gap_aware.parquet", index=False)

    frozen = pd.DataFrame({
        "symbol": ["X"],
        "expected_seq": [0],
        "timestamp": [t[0]],
        "fwd_ret_4b": [close[4] / close[0] - 1.0],
    })
    return canon, live, frozen


def test_path_proxy_stop_first_conservative(tmp_path):
    canon, live, frozen = _write_panel(tmp_path, both=True)
    out, audit = r6.attach_path_proxy(frozen, canon, live)
    row = out.iloc[0]
    assert bool(row["path_complete"])
    assert abs(float(row["proxy_ret_4b"]) - r6.STOP) < 1e-12
    assert audit["fwd_parity_max_abs_diff"] < 1e-12


def test_path_proxy_time_exit_when_no_barrier(tmp_path):
    canon, live, frozen = _write_panel(tmp_path, time_exit=True)
    out, audit = r6.attach_path_proxy(frozen, canon, live)
    row = out.iloc[0]
    assert bool(row["path_complete"])
    assert abs(float(row["proxy_ret_4b"]) - 0.02) < 1e-12
    assert audit["fwd_parity_max_abs_diff"] < 1e-12


def test_schedule_audit_exact():
    t = pd.date_range("2026-01-01", periods=3, freq="4h", tz="UTC")
    a = pd.DataFrame({"timestamp": t, "fold": ["E1"] * 3})
    b = a.copy()
    x = r6.schedule_audit(a, b)
    assert x["exact_match"]
    assert x["matched_rows"] == 3


def test_bool_series_accepts_common_true_values():
    s = pd.Series(["true", "1", "yes", "false", "0"])
    out = r6._bool_series(s)
    assert out.tolist() == [True, True, True, False, False]
