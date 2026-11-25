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


def split_selected_universe(config, now_utc):
    """Plan two separate CLI requests from the exact existing 19-key selection.

    Pure planning only. No files, downloads or subprocesses are executed here.
    """
    from copy import deepcopy
    assets = config.get("assets")
    if not isinstance(assets, list) or config.get("comparisons") != []:
        raise ValueError("INVALID_SELECTED_UNIVERSE")
    keys = [a.get("key") for a in assets]
    if (len(keys) != len(set(keys)) or set(keys) != US_KEYS | OTHER_KEYS
            or any(a.get("provider") != "yfinance" for a in assets)):
        raise ValueError("NOT_EXACT_19_KEY_YAHOO_UNIVERSE")
    plan = fetch_plan(now_utc)
    groups = {}
    for name, selected in (("US_COMPLETED", US_KEYS), ("NON_US_EXISTING", OTHER_KEYS)):
        group = deepcopy(config)
        group["assets"] = [deepcopy(a) for a in assets if a["key"] in selected]
        groups[name] = {
            "config": group,
            "exclusive_end": next(iter({plan["exclusive_end_by_key"][a["key"]]
                                        for a in group["assets"]})),
        }
    return {"plan": plan, "groups": groups, "executed": False,
            "research_only": True, "production_writes": False}


def reconcile_staged_us(observed, bounded, staged_features, *, key, cutoff, feature_builder):
    """Audit a separately fetched US prefix and freshly built TA in memory.

    A changed eligible row (except retrieval-time metadata), a missing/invalid
    cutoff, or a different/missing feature value is HOLD. Never publishes,
    changes a frame, or certifies a provider. Caller must still verify manifests,
    required coverage and all existing QC gates across the complete candidate.
    """
    report = {"key": key, "cutoff": cutoff, "status": "STAGED_PREFIX_HOLD",
              "reasons": [], "research_only": True, "production_writes": False,
              "source_finality_certified": False, "ready_for_pit_training": False,
              "approved_live": False, "prefix_identity_verified": False,
              "feature_reproduction_verified": False}
    original = inspect_us_prefix(observed, key, cutoff)
    staged = inspect_us_prefix(bounded, key, cutoff)
    report["observed_tail"] = original
    report["staged_tail"] = staged
    if not original["cutoff_row_valid"] or not staged["cutoff_row_valid"]:
        report["reasons"].append("CUTOFF_ROW_MISSING_OR_INVALID")
    if staged["post_cutoff_rows"]:
        report["reasons"].append("STAGED_POST_CUTOFF_ROWS")
    if report["reasons"]:
        return report
    # Only the retrieval clock may differ between two independently fetched
    # snapshots. Source-asof, adjustment flag, symbol and all price values
    # must remain identical. Do not round, interpolate or fill missing rows.
    required = {"timestamp", "market", "symbol", "open", "high", "low",
                "close", "adj_close", "volume", "currency", "source",
                "source_asof", "retrieved_at", "is_adjusted"}
    if not required.issubset(observed.columns) or not required.issubset(bounded.columns):
        report["reasons"].append("CANONICAL_SCHEMA_MISSING")
        return report
    mask = pd.to_datetime(observed.timestamp, utc=True).le(pd.Timestamp(cutoff, tz="UTC"))
    prefix = observed.loc[mask].reset_index(drop=True)
    bounded = bounded.reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(prefix.drop(columns="retrieved_at"),
                                      bounded.drop(columns="retrieved_at"),
                                      check_exact=True)
    except AssertionError:
        report["reasons"].append("ELIGIBLE_PREFIX_CHANGED")
        return report
    report["prefix_identity_verified"] = True
    if not {"timestamp", "symbol"}.issubset(staged_features.columns):
        report["reasons"].append("FEATURE_IDENTITY_SCHEMA_MISSING")
        return report
    identity = ["timestamp", "symbol"]
    try:
        pd.testing.assert_frame_equal(
            bounded[identity], staged_features[identity].reset_index(drop=True),
            check_exact=True)
    except AssertionError:
        report["reasons"].append("RAW_FEATURE_ROW_IDENTITY_MISMATCH")
        return report
    try:
        reference = feature_builder(prefix.copy(deep=True))
        fresh = feature_builder(bounded.copy(deep=True))
        pd.testing.assert_frame_equal(reference.reset_index(drop=True),
                                      fresh.reset_index(drop=True), check_exact=True)
        pd.testing.assert_frame_equal(fresh.reset_index(drop=True),
                                      staged_features.reset_index(drop=True), check_exact=True)
    except AssertionError:
        report["reasons"].append("FEATURE_VALUES_OR_SCHEMA_MISMATCH")
        return report
    except Exception:
        report["reasons"].append("FEATURE_REBUILD_UNAVAILABLE")
        return report
    report["feature_reproduction_verified"] = True
    report["status"] = "STAGED_PREFIX_AND_FEATURES_RECONCILED_RESEARCH_HOLD"
    return report
