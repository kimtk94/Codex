"""One-time public market-data probe; no Drive, publication, or trading."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from urllib.request import urlopen
from pathlib import Path
import sys
import tempfile

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pyarrow
import talib
import yfinance

from completed_session_policy import (
    US_KEYS, OTHER_KEYS, fetch_plan, split_selected_universe, reconcile_staged_us,
)
from refresh_ci import select_universe

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "kalman-toss-gateway"))
from engine.market_data.base import ProviderRequest
from engine.market_data.schema import validate_canonical_ohlcv
from engine.market_data.yfinance_provider import YFinanceProvider
from engine.features_v2_002.talib_features import build_talib_features

START = "2024-01-01"
DEFAULT_KEYS = tuple(sorted(US_KEYS | OTHER_KEYS))
CBOE_VIX_HISTORY = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"


def request_from_asset(a, end):
    if a["provider"] != "yfinance":
        raise ValueError("UNEXPECTED_PROVIDER")
    return ProviderRequest(
        symbol=str(a["symbol"]), provider_symbol=str(a.get("provider_symbol") or a["symbol"]),
        market=str(a.get("market") or "UNKNOWN"), currency=str(a.get("currency") or ""),
        kind=str(a.get("kind") or "equity"), start=START, end=end,
        interval=str(a.get("interval") or "1d"), adjusted=bool(a.get("adjusted", False)),
        extra={"group": str(a.get("group") or "UNGROUPED")})


def roundtrip(frame, path):
    frame.to_parquet(path, index=False, engine="pyarrow")
    copy = pd.read_parquet(path, engine="pyarrow")
    pd.testing.assert_frame_equal(frame.reset_index(drop=True), copy, check_exact=True)
    return copy


def coverage(frame, cutoff=None):
    stamp = pd.to_datetime(frame.timestamp, utc=True, errors="raise")
    dates = pd.DatetimeIndex(stamp.dt.tz_convert(None).dt.normalize())
    close = pd.to_numeric(frame.close, errors="coerce")
    num = frame[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    complete = np.isfinite(num).all(axis=1)
    invalid = complete & ((num.min(axis=1) <= 0) |
                          (num.low > num[["open", "close"]].min(axis=1)) |
                          (num.high < num[["open", "close"]].max(axis=1)))
    d = {"rows": len(frame), "first_date": str(dates.min().date()),
         "last_date": str(dates.max().date()),
         "null_close_rows": int(close.isna().sum()),
         "invalid_complete_ohlc_rows": int(invalid.sum()),
         "canonical_issue_count": len(validate_canonical_ohlcv(frame))}
    if cutoff is not None:
        expected = pd.DatetimeIndex(xcals.get_calendar("XNYS").sessions_in_range(START, cutoff))
        if expected.tz is not None:
            expected = expected.tz_convert(None)
        good = dates[np.isfinite(close.to_numpy(float))]
        d["expected_xnys_sessions"] = len(expected)
        d["missing_xnys_labels"] = len(expected.difference(dates))
        d["missing_xnys_valid_closes"] = len(expected.difference(good))
        d["non_xnys_labels"] = len(dates.difference(expected))
        d["non_xnys_finite_close_labels"] = len(good.difference(expected))
        d["non_xnys_null_or_nonfinite_labels"] = d["non_xnys_labels"] - d["non_xnys_finite_close_labels"]
    return d


def compare_feature_outputs(observed, bounded, staged, cutoff):
    """Separate actual TA equality from exact canonical-source equality."""
    mask = pd.to_datetime(observed.timestamp, utc=True).le(pd.Timestamp(cutoff, tz="UTC"))
    prefix = observed.loc[mask].reset_index(drop=True)
    ref = build_talib_features(prefix)
    fresh = build_talib_features(bounded)
    out = {"observed_prefix_rows": len(prefix), "bounded_rows": len(bounded),
           "exact_output_identity": False, "bounded_repeat_identity": False,
           "output_columns": len(staged.columns), "numeric_feature_columns": 0,
           "finite_numeric_pairs": 0, "different_numeric_values": 0,
           "missingness_changes": 0, "max_abs_feature_difference": None}
    try:
        pd.testing.assert_frame_equal(fresh, staged, check_exact=True)
        out["bounded_repeat_identity"] = True
    except AssertionError:
        pass
    try:
        pd.testing.assert_frame_equal(ref, staged, check_exact=True)
        out["exact_output_identity"] = True
    except AssertionError:
        pass
    # Align on daily timestamp and symbol. Do not equate missing rows with zeros.
    identity = ["timestamp", "symbol"]
    a = ref.set_index(identity)
    b = staged.set_index(identity)
    common = a.index.intersection(b.index)
    out["matched_feature_rows"] = len(common)
    out["observed_only_feature_rows"] = len(a.index.difference(b.index))
    out["bounded_only_feature_rows"] = len(b.index.difference(a.index))
    maxima = []
    for col in sorted(set(a.columns) & set(b.columns)):
        if not col.startswith("talib_v2_"):
            continue
        x = a.loc[common, col].to_numpy(dtype=float)
        y = b.loc[common, col].to_numpy(dtype=float)
        out["numeric_feature_columns"] += 1
        finite = np.isfinite(x) & np.isfinite(y)
        out["finite_numeric_pairs"] += int(finite.sum())
        out["different_numeric_values"] += int((x[finite] != y[finite]).sum())
        out["missingness_changes"] += int((np.isfinite(x) != np.isfinite(y)).sum())
        if finite.any():
            maxima.append(float(np.max(np.abs(x[finite] - y[finite]))))
    out["max_abs_feature_difference"] = max(maxima) if maxima else None
    return out


def compare_cboe_history(frame, cutoff):
    """Current published Cboe history is an independent-source comparator,
    not a timestamped certification of past point-in-time source finality."""
    with urlopen(CBOE_VIX_HISTORY, timeout=30) as response:
        if response.geturl() != CBOE_VIX_HISTORY:
            raise ValueError("UNEXPECTED_CBOE_REDIRECT")
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise ValueError("CBOE_HISTORY_TOO_LARGE")
    c = pd.read_csv(io.BytesIO(payload))
    if not {"DATE", "CLOSE"}.issubset(c.columns):
        raise ValueError("CBOE_HISTORY_SCHEMA")
    dates = pd.to_datetime(c.DATE, format="%m/%d/%Y", errors="raise")
    if dates.duplicated().any():
        raise ValueError("CBOE_DUPLICATE_DATES")
    c = pd.Series(pd.to_numeric(c.CLOSE, errors="raise").to_numpy(), index=pd.DatetimeIndex(dates))
    c = c.loc[(c.index >= pd.Timestamp(START)) & (c.index <= pd.Timestamp(cutoff))]
    if c.empty or not np.isfinite(c).all() or (c <= 0).any():
        raise ValueError("CBOE_INVALID_CUTOFF_HISTORY")
    y = pd.Series(pd.to_numeric(frame.close, errors="coerce").to_numpy(),
                  index=pd.DatetimeIndex(pd.to_datetime(frame.timestamp, utc=True).dt.tz_convert(None)))
    if y.index.duplicated().any():
        raise ValueError("YAHOO_DUPLICATE_DATES")
    y = y.loc[(y.index >= pd.Timestamp(START)) & (y.index <= pd.Timestamp(cutoff))]
    finite_y = y[np.isfinite(y)]
    common = c.index.intersection(finite_y.index)
    delta = (finite_y.loc[common] - c.loc[common]).abs()
    expected = pd.DatetimeIndex(xcals.get_calendar("XNYS").sessions_in_range(START, cutoff))
    if expected.tz is not None:
        expected = expected.tz_convert(None)
    return {"source": CBOE_VIX_HISTORY, "source_sha256": hashlib.sha256(payload).hexdigest(),
            "cboe_dates": len(c), "cboe_last_date": str(c.index.max().date()),
            "cboe_non_xnys_dates": len(c.index.difference(expected)),
            "xnys_dates_missing_cboe": len(expected.difference(c.index)),
            "yahoo_finite_dates": len(finite_y), "matched_finite_dates": len(common),
            "yahoo_only_labels": len(y.index.difference(c.index)),
            "yahoo_only_finite_dates": len(finite_y.index.difference(c.index)),
            "cboe_dates_missing_yahoo_finite_close": len(c.index.difference(finite_y.index)),
            "half_cent_agreement_count": int((delta <= .005).sum()),
            "max_abs_close_difference": float(delta.max()) if len(delta) else None,
            "native_calendar_certified": False, "source_finality_certified": False}


def probe_asset(a, end, cutoff, folder, provider):
    key = a["key"]
    result = {"key": key, "status": "BLOCKED_RESEARCH_HOLD",
              "request_end": end, "feature_reproduction_verified": False,
              "source_finality_certified": False, "ready_for_pit_training": False,
              "approved_live": False, "production_writes": False}
    # Actual independent calls to the unchanged production provider implementation.
    original = provider.fetch(request_from_asset(a, None))
    original_frame = roundtrip(original.data, folder / (key + "-observed.parquet"))
    result["observed_coverage"] = coverage(original_frame)
    if key in US_KEYS:
        bounded = provider.fetch(request_from_asset(a, end))
        frame = roundtrip(bounded.data, folder / (key + "-bounded.parquet"))
        result["bounded_coverage"] = coverage(frame, cutoff)
        features = roundtrip(build_talib_features(frame), folder / (key + "-ta.parquet"))
        verdict = reconcile_staged_us(original_frame, frame, features, key=key,
                                      cutoff=cutoff, feature_builder=build_talib_features)
        result["feature_output_comparison"] = compare_feature_outputs(original_frame, frame, features, cutoff)
        if key == "yf_vix":
            try:
                result["cboe_history_comparison"] = compare_cboe_history(frame, cutoff)
            except Exception as exc:
                result["cboe_history_comparison"] = {"status": "UNAVAILABLE_HOLD", "error_type": type(exc).__name__}
        result["reconciliation"] = verdict
        result["feature_reproduction_verified"] = verdict["feature_reproduction_verified"]
        result["rsi_valid_rows"] = int(features.talib_v2_rsi14.notna().sum())
        result["status"] = verdict["status"]
        if not result["rsi_valid_rows"]:
            result["status"] = "NO_VALID_RSI_HOLD"
        # Reconciliation is necessary, not sufficient: coverage/QC is separate.
        c = result["bounded_coverage"]
        result["xnys_expected_session_coverage_complete"] = not any(c[k] for k in (
            "missing_xnys_labels", "missing_xnys_valid_closes"))
        result["strict_xnys_calendar_clean"] = not c["non_xnys_labels"]
        result["coverage_qc_complete"] = (
            result["xnys_expected_session_coverage_complete"]
            and result["strict_xnys_calendar_clean"]
            and not any(c[k] for k in ("null_close_rows", "invalid_complete_ohlc_rows",
                                      "canonical_issue_count")))
        # An XNYS cutoff does not certify the native calendar of VIX or yields.
        result["native_calendar_certified"] = False
    else:
        if end is not None:
            raise ValueError("NON_US_END_CHANGED")
        features = roundtrip(build_talib_features(original_frame), folder / (key + "-ta.parquet"))
        repeat = build_talib_features(original_frame.copy(deep=True))
        pd.testing.assert_frame_equal(features, repeat, check_exact=True)
        pd.testing.assert_frame_equal(
            original_frame[["timestamp", "symbol"]].reset_index(drop=True),
            features[["timestamp", "symbol"]].reset_index(drop=True), check_exact=True)
        result["rsi_valid_rows"] = int(features.talib_v2_rsi14.notna().sum())
        result["feature_reproduction_verified"] = bool(result["rsi_valid_rows"])
        result["status"] = ("NON_US_REQUEST_UNCHANGED_FEATURES_REPRODUCED_HOLD"
                            if result["feature_reproduction_verified"] else "NO_VALID_RSI_HOLD")
        c = result["observed_coverage"]
        result["coverage_qc_complete"] = False  # no US calendar imposed on this asset
        result["observed_canonical_qc_clean"] = not any(c[k] for k in (
            "invalid_complete_ohlc_rows", "canonical_issue_count"))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--keys", nargs="+", choices=sorted(US_KEYS | OTHER_KEYS),
                   default=list(DEFAULT_KEYS))
    p.add_argument("--out", required=True)
    a = p.parse_args()
    if len(a.keys) != len(set(a.keys)):
        raise ValueError("DUPLICATE_KEYS")
    target = Path(a.out)
    if target.exists():
        raise FileExistsError("EXISTING_REPORT")
    now = datetime.now(timezone.utc)
    report = {"schema": "kalman-public-provider-cutoff-probe-v1",
              "research_only": True, "production_writes": False,
              "source_finality_certified": False, "ready_for_pit_training": False,
              "approved_live": False, "raw_rows_published": False,
              "runtime": {"python": sys.version.split()[0], "numpy": np.__version__,
                          "pandas": pd.__version__, "pyarrow": pyarrow.__version__,
                          "talib": talib.__version__, "yfinance": yfinance.__version__},
              "requested_keys": a.keys, "assets": []}
    with tempfile.TemporaryDirectory(prefix="kalman_public_probe_") as tmp:
        folder = Path(tmp)
        cfg = select_universe(ROOT / "kalman-toss-gateway/config/market-data-v2-universe.json",
                              folder / "selected.json")
        groups = split_selected_universe(cfg, now)
        plan = groups["plan"]
        report["plan"] = plan
        report["planned_us_keys"] = len(groups["groups"]["US_COMPLETED"]["config"]["assets"])
        report["planned_other_keys"] = len(groups["groups"]["NON_US_EXISTING"]["config"]["assets"])
        assets = {x["key"]: x for x in cfg["assets"]}
        provider = YFinanceProvider()
        for key in a.keys:
            try:
                result = probe_asset(assets[key], plan["exclusive_end_by_key"][key],
                                     plan["completed_xnys_session"], folder, provider)
            except Exception as exc:
                result = {"key": key, "status": "PROVIDER_OR_REBUILD_ERROR_HOLD",
                          "error_type": type(exc).__name__,
                          "feature_reproduction_verified": False,
                          "source_finality_certified": False,
                          "approved_live": False, "production_writes": False}
            report["assets"].append(result)
            print("PROBE_ASSET", json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    report["temporary_raw_and_features_cleaned"] = True
    report["clock_rollover"] = (
        fetch_plan(datetime.now(timezone.utc))["completed_xnys_session"] !=
        report["plan"]["completed_xnys_session"])
    report["feature_reproduced_assets"] = sum(x.get("feature_reproduction_verified", False)
                                               for x in report["assets"])
    report["us_exact_source_prefixes"] = sum(x.get("reconciliation", {}).get("prefix_identity_verified", False) for x in report["assets"])
    report["us_exact_feature_outputs"] = sum(x.get("feature_output_comparison", {}).get("exact_output_identity", False) for x in report["assets"])
    report["strict_us_coverage_qc_count"] = sum(x.get("coverage_qc_complete", False) for x in report["assets"])
    report["status"] = ("TECHNICAL_REPRODUCTION_RESEARCH_HOLD"
                        if report["feature_reproduced_assets"] == len(a.keys) and not report["clock_rollover"]
                        else "INCOMPLETE_PROBE_RESEARCH_HOLD")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(report, indent=2, allow_nan=False) + "\n").encode()
    with target.open("xb") as f:
        f.write(data)
    print("PROBE_SUMMARY", report["status"], report["feature_reproduced_assets"],
          len(a.keys), hashlib.sha256(data).hexdigest(), flush=True)
    return 0 if report["status"] == "TECHNICAL_REPRODUCTION_RESEARCH_HOLD" else 2


if __name__ == "__main__":
    raise SystemExit(main())
