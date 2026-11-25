"""Read-only research plan for completed-session fetches. Not a publisher."""
from datetime import date, timedelta

import exchange_calendars as xcals
import numpy as np
import pandas as pd

US_KEYS = frozenset("yf_spy yf_qqq yf_smh yf_vix yf_tnx yf_hyg yf_lqd yf_tlt yf_gld yf_iwm yf_dia yf_soxx yf_sp500 yf_ixic".split())
OTHER_KEYS = frozenset("yf_dxy yf_usdkrw yf_btc yf_kospi yf_kosdaq".split())


def fetch_plan(now_utc):
    """Freeze one explicit aware clock; end is exclusive, not source certification."""
    now = pd.Timestamp(now_utc)
    if pd.isna(now) or now.tzinfo is None:
        raise ValueError("EXPLICIT_AWARE_CLOCK_REQUIRED")
    now = now.tz_convert("UTC")
    cal = xcals.get_calendar("XNYS")
    session = cal.date_to_session(now.tz_localize(None).normalize(), direction="previous")
    if cal.session_close(session) + pd.Timedelta(minutes=30) > now:
        session = cal.previous_session(session)
    cutoff = session.date()
    end = (cutoff + timedelta(days=1)).isoformat()
    return {
        "schema": "kalman-completed-session-plan-v1",
        "clock_utc": now.isoformat(),
        "completed_xnys_session": cutoff.isoformat(),
        "exclusive_end_by_key": {key: end if key in US_KEYS else None
                                 for key in sorted(US_KEYS | OTHER_KEYS)},
        "research_only": True, "production_writes": False,
        "source_finality_certified": False, "ready_for_pit_training": False,
        "approved_live": False,
    }


def inspect_us_prefix(frame, key, cutoff):
    """Return metadata only. Never delete rows, repair prices or approve a candidate."""
    if key not in US_KEYS:
        raise ValueError("NOT_XNYS_POLICY_KEY")
    if not isinstance(cutoff, str) or date.fromisoformat(cutoff).isoformat() != cutoff:
        raise ValueError("INVALID_CUTOFF")
    cut = pd.Timestamp(cutoff, tz="UTC")
    cols = ["timestamp", "open", "high", "low", "close"]
    if not set(cols).issubset(frame.columns) or frame.empty:
        raise ValueError("INVALID_SCHEMA")
    ts = pd.to_datetime(frame.timestamp, utc=True, errors="coerce")
    if ts.isna().any() or ts.duplicated().any() or not ts.is_monotonic_increasing:
        raise ValueError("INVALID_TIMESTAMP_SEQUENCE")
    if not ts.eq(ts.dt.normalize()).all():
        raise ValueError("NOT_DAILY_SESSION_LABELS")
    tail = ts.gt(cut)
    prefix = frame.loc[~tail]
    at = frame.loc[ts.eq(cut), cols[1:]].apply(pd.to_numeric, errors="coerce")
    valid = False
    if len(at) == 1:
        o, h, l, c = at.iloc[0].to_numpy(dtype=float)
        valid = bool(np.isfinite([o, h, l, c]).all() and min(o, h, l, c) > 0
                     and l <= min(o, c) <= max(o, c) <= h)
    status = ("CUTOFF_ROW_MISSING_OR_INVALID_HOLD" if not valid else
              "POST_CUTOFF_ROWS_OBSERVED_HOLD" if tail.any() else
              "CUTOFF_ROW_PRESENT_RESEARCH_HOLD")
    return {"status": status, "key": key, "cutoff": cutoff,
            "original_rows": len(frame), "prefix_rows": len(prefix),
            "post_cutoff_rows": int(tail.sum()), "cutoff_row_valid": valid,
            "post_cutoff_dates": [x.date().isoformat() for x in ts[tail]],
            "features_recomputed": False, "source_finality_certified": False,
            "ready_for_pit_training": False, "production_writes": False,
            "approved_live": False}
