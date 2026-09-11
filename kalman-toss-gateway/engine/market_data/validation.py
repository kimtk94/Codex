from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .schema import validate_canonical_ohlcv


def _close_by_day(frame: pd.DataFrame) -> pd.Series:
    ts = pd.to_datetime(frame["timestamp"], errors="coerce").dt.normalize()
    close = pd.to_numeric(frame["close"], errors="coerce")
    series = pd.Series(close.to_numpy(), index=ts, dtype=float)
    series = series.loc[~series.index.isna()]
    return series.groupby(level=0).last().sort_index()


def compare_close(
    primary: pd.DataFrame,
    secondary: pd.DataFrame,
    *,
    primary_name: str,
    secondary_name: str,
) -> dict[str, Any]:
    """Measure provider disagreement without silently choosing a winner."""
    primary_issues = validate_canonical_ohlcv(primary)
    secondary_issues = validate_canonical_ohlcv(secondary)
    if primary_issues or secondary_issues:
        return {
            "status": "FAIL",
            "primary": primary_name,
            "secondary": secondary_name,
            "primary_issues": primary_issues,
            "secondary_issues": secondary_issues,
            "overlap_rows": 0,
        }

    p = _close_by_day(primary).rename("primary")
    s = _close_by_day(secondary).rename("secondary")
    joined = pd.concat([p, s], axis=1, join="inner").dropna()
    if joined.empty:
        return {
            "status": "FAIL",
            "primary": primary_name,
            "secondary": secondary_name,
            "primary_issues": [],
            "secondary_issues": [],
            "overlap_rows": 0,
            "reason": "no_overlapping_close_observations",
        }

    denominator = joined["secondary"].replace(0, np.nan)
    relative_diff = joined["primary"] / denominator - 1.0
    primary_ret = joined["primary"].pct_change(fill_method=None)
    secondary_ret = joined["secondary"].pct_change(fill_method=None)
    correlation = primary_ret.corr(secondary_ret)
    last = joined.iloc[-1]

    return {
        "status": "READY",
        "comparison_only": True,
        "primary": primary_name,
        "secondary": secondary_name,
        "overlap_rows": int(len(joined)),
        "first_overlap": joined.index[0].date().isoformat(),
        "last_overlap": joined.index[-1].date().isoformat(),
        "primary_last_close": float(last["primary"]),
        "secondary_last_close": float(last["secondary"]),
        "last_close_relative_diff": None
        if not np.isfinite(relative_diff.iloc[-1])
        else float(relative_diff.iloc[-1]),
        "mean_abs_close_relative_diff": None
        if relative_diff.dropna().empty
        else float(relative_diff.abs().mean()),
        "max_abs_close_relative_diff": None
        if relative_diff.dropna().empty
        else float(relative_diff.abs().max()),
        "daily_return_correlation": None
        if correlation is None or not np.isfinite(correlation)
        else float(correlation),
        "primary_observation_count": int(len(p)),
        "secondary_observation_count": int(len(s)),
    }
