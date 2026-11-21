#!/usr/bin/env python3
"""Yahoo factor lineage diagnostics ONLY. Never certify Yahoo factors by Yahoo data.

The existing 25 adjusted Daily20 bars are immutable input. This separate
read-only download observes Yahoo's split-adjusted Close, Adj Close, dividend
and split event series per date and flags retrospective drift. Neither Yahoo's
ratio nor its self-reported events is independent corporate-action evidence.
Never reconstruct a raw exchange price or change LIVE/first-seal signals here.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from hashlib import sha256
import json
import math
from pathlib import Path

import pandas as pd

from daily20 import load_spec, market_file, write_json

VERSION = "daily20-yahoo-factor-lineage-v2"
REQUIRED = ("Close", "Adj Close", "Dividends", "Stock Splits")
PRICE_TOLERANCE_USD = 0.005


def fetch_yahoo(symbol, start, end_exclusive):
    """Separate vendor observation; NO implicit auto_adjust/repaired data."""
    import yfinance as yf
    return yf.Ticker(symbol).history(
        start=start, end=end_exclusive, interval="1d",
        auto_adjust=False, actions=True, repair=False,
        raise_errors=True,
    )


def fetch_yahoo_repaired(symbol, start, end_exclusive):
    """Replay with the production setting repair=True (still Yahoo-origin)."""
    import yfinance as yf
    return yf.Ticker(symbol).history(
        start=start, end=end_exclusive, interval="1d",
        auto_adjust=False, actions=True, repair=True,
        raise_errors=True,
    )


def _as_dates(frame, *, source):
    if source:
        index = pd.DatetimeIndex(pd.to_datetime(frame.index, errors="raise"))
        if index.tz is None:
            # A Yahoo NYSE session date is local, not an arbitrary UTC instant.
            index = index.tz_localize("America/New_York")
        return index.tz_convert("America/New_York").strftime("%Y-%m-%d").tolist()
    index = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    return index.dt.strftime("%Y-%m-%d").tolist()


def diagnose(symbol, history, cached, session):
    """Return (status summary, stable CSV bytes) with explicit source semantics."""
    if not isinstance(history, pd.DataFrame) or history.empty:
        raise ValueError("YAHOO_EMPTY_HISTORY")
    if not set(REQUIRED).issubset(history.columns):
        raise ValueError("YAHOO_ACTION_OR_PRICE_FIELDS_MISSING")
    if not {"timestamp", "close", "is_adjusted"}.issubset(cached.columns):
        raise ValueError("CACHED_MARKET_SCHEMA_MISSING")
    if cached.empty or cached["is_adjusted"].nunique() != 1 or not bool(cached["is_adjusted"].iloc[0]):
        raise ValueError("CACHED_BAR_MUST_BE_ADJUSTED")
    dates = _as_dates(history, source=True)
    if len(set(dates)) != len(dates):
        raise ValueError("YAHOO_DUPLICATE_SESSION")
    source = pd.DataFrame({
        "session": dates,
        "yahoo_close_split_adjusted": pd.to_numeric(history["Close"], errors="coerce").to_numpy(dtype=float),
        "yahoo_adj_close": pd.to_numeric(history["Adj Close"], errors="coerce").to_numpy(dtype=float),
        "yahoo_dividend": pd.to_numeric(history["Dividends"], errors="coerce").to_numpy(dtype=float),
        "yahoo_stock_split": pd.to_numeric(history["Stock Splits"], errors="coerce").to_numpy(dtype=float),
    })
    source = source.loc[source["session"] <= session].sort_values("session").reset_index(drop=True)
    if source.empty:
        raise ValueError("YAHOO_NO_COMPLETED_SESSION")
    prices = source[["yahoo_close_split_adjusted", "yahoo_adj_close"]]
    events = source[["yahoo_dividend", "yahoo_stock_split"]]
    if not prices.notna().all().all() or not (prices > 0).all().all():
        raise ValueError("YAHOO_PRICE_INVALID")
    if not events.notna().all().all() or (source["yahoo_stock_split"] < 0).any():
        raise ValueError("YAHOO_ACTION_INVALID")
    source["yahoo_adj_over_close"] = (source["yahoo_adj_close"] / source["yahoo_close_split_adjusted"])
    if not source["yahoo_adj_over_close"].map(math.isfinite).all():
        raise ValueError("YAHOO_FACTOR_INVALID")

    cached_dates = _as_dates(cached, source=False)
    if len(set(cached_dates)) != len(cached_dates):
        raise ValueError("CACHED_DUPLICATE_SESSION")
    stored = pd.DataFrame({
        "session": cached_dates,
        "daily20_adjusted_close": pd.to_numeric(cached["close"], errors="coerce").to_numpy(dtype=float),
    })
    combined = source.merge(stored, on="session", how="left", validate="one_to_one")
    checked = combined.loc[combined["daily20_adjusted_close"].notna()].copy()
    checked["abs_diff"] = (checked["yahoo_adj_close"] - checked["daily20_adjusted_close"]).abs()
    drifts = checked.loc[checked["abs_diff"] > PRICE_TOLERANCE_USD]
    last_available = source["session"].iloc[-1]
    asof_in_source = bool((source["session"] == session).any())
    asof_in_cached = bool((stored["session"] == session).any())
    last_diff = checked.loc[checked["session"] == session, "abs_diff"]
    latest_diff = float(last_diff.iloc[0]) if len(last_diff) == 1 else None

    if not asof_in_source or not asof_in_cached:
        status = "YAHOO_ASOF_SESSION_MISSING_HOLD"
    elif len(drifts):
        status = "YAHOO_ADJUSTED_COMPARISON_DIFFERENCE_HOLD"
    elif not len(checked):
        status = "YAHOO_CACHED_OVERLAP_MISSING_HOLD"
    else:
        status = "YAHOO_FACTOR_OBSERVED_UNATTESTED"

    # Plain CSV has a deterministic digest independent of gzip headers.
    canonical = combined.to_csv(index=False, float_format="%.12g").encode("utf-8")
    details = {
        "symbol": symbol,
        "status": status,
        "source": "Yahoo/yfinance auto_adjust=False actions=True repair=False",
        "adjustment_semantics": "yahoo_close_is_split_adjusted;ratio_excludes_independent_split_proof",
        "vendor_observed_not_independently_attested": True,
        "history_first": source["session"].iloc[0],
        "history_latest": last_available,
        "history_rows": int(len(source)),
        "overlap_days": int(len(checked)),
        "mismatch_gt_half_cent_days": int(len(drifts)),
        "mismatch_examples": drifts["session"].head(8).tolist(),
        "latest_abs_diff_usd": latest_diff,
        "max_overlap_abs_diff_usd": float(checked["abs_diff"].max()) if len(checked) else None,
        "yahoo_dividend_events": int((source["yahoo_dividend"] != 0).sum()),
        "yahoo_split_events": int((source["yahoo_stock_split"] != 0).sum()),
        "serialized_csv_sha256": sha256(canonical).hexdigest(),
    }
    return details, canonical


def run(spec, market, qc_path, out_dir, *, fetcher=fetch_yahoo,
        repaired_fetcher=fetch_yahoo_repaired, fetched_at=None):
    qc = json.loads(Path(qc_path).read_text())
    session = qc.get("expected_session")
    date.fromisoformat(session)
    if qc.get("status") != "READY" or qc.get("ready") != 26:
        raise RuntimeError("LINEAGE_REQUIRES_READY_26_ASSET_QC")
    equities = [s for s in spec["core"] + spec["context"] if s != "^VIX"]
    if len(equities) != 25 or len(set(equities)) != 25:
        raise RuntimeError("LINEAGE_EXACTLY_25_EQUITY_ETF_EXPECTED")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = fetched_at or pd.Timestamp.now(tz="UTC").isoformat()
    rows = []
    for symbol in equities:
        try:
            cached = pd.read_parquet(market_file(market, symbol))
            end = (date.fromisoformat(session) + timedelta(days=1)).isoformat()
            history = fetcher(symbol, spec["start_date"], end)
            detail, canonical = diagnose(symbol, history, cached, session)
            # Preserve Yahoo un-repaired vendor observations with a digest.
            # The production provider uses repair=True, so a raw-vs-cached
            # difference alone is NOT evidence of an upstream price revision.
            import gzip
            original_status = detail["status"]
            detail["unrepaired_comparison_status"] = original_status
            output = out_dir / (symbol.lower() + ".csv.gz")
            with gzip.open(output, "wb", compresslevel=6) as f:
                f.write(canonical)
            detail["csv_gzip_file"] = output.name
            detail["production_repair_setting"] = True
            detail["unrepaired_diagnostic_setting"] = False
            if original_status == "YAHOO_ADJUSTED_COMPARISON_DIFFERENCE_HOLD":
                try:
                    repaired = repaired_fetcher(symbol, spec["start_date"], end)
                    repaired_detail, repaired_csv = diagnose(symbol, repaired, cached, session)
                    rp = out_dir / (symbol.lower() + "_repaired.csv.gz")
                    with gzip.open(rp, "wb", compresslevel=6) as f:
                        f.write(repaired_csv)
                    detail["repaired_csv_gzip_file"] = rp.name
                    detail["repaired_csv_sha256"] = repaired_detail["serialized_csv_sha256"]
                    detail["repair_true_mismatch_days"] = repaired_detail["mismatch_gt_half_cent_days"]
                    detail["repair_true_max_abs_diff_usd"] = repaired_detail["max_overlap_abs_diff_usd"]
                    detail["repair_true_latest_abs_diff_usd"] = repaired_detail["latest_abs_diff_usd"]
                    detail["repair_true_comparison_status"] = repaired_detail["status"]
                    if repaired_detail["status"] == "YAHOO_FACTOR_OBSERVED_UNATTESTED":
                        detail["status"] = "REPAIR_POLICY_DIFFERENCE_OBSERVED"
                    else:
                        detail["status"] = "SAME_REPAIR_SETTING_MISMATCH_RESEARCH_HOLD"
                except Exception as exc:
                    detail["status"] = "REPAIR_TRUE_REFERENCE_UNAVAILABLE_HOLD"
                    detail["repaired_fetch_error_class"] = type(exc).__name__
            elif original_status == "YAHOO_FACTOR_OBSERVED_UNATTESTED":
                # No second Yahoo fetch is needed if the un-repaired history
                # already matches every available cached session.
                detail["status"] = "YAHOO_FACTOR_OBSERVED_UNATTESTED"
            else:
                detail["status"] = original_status
        except Exception as exc:
            # A missing/denied vendor response must be visible, not counted as
            # an empty event list or as certified/no-actions history.
            detail = {"symbol": symbol, "status": "SOURCE_OR_SCHEMA_UNAVAILABLE_HOLD",
                      "error_class": type(exc).__name__,
                      "vendor_observed_not_independently_attested": True}
        rows.append(detail)
    result = {
        "version": VERSION, "session": session, "fetched_at_utc": stamp,
        "research_only": True, "production_writes": False,
        "strategy_promoted": False, "independent_corporate_actions_certified": 0,
        "finality_verified": 0, "required": 25,
        "vendor_history_observed": sum("csv_gzip_file" in x for x in rows),
        "unrepaired_source_alignment": sum(
            x["status"] == "YAHOO_FACTOR_OBSERVED_UNATTESTED" for x in rows),
        "repair_policy_differences": sum(
            x["status"] == "REPAIR_POLICY_DIFFERENCE_OBSERVED" for x in rows),
        "same_repair_unresolved": sum(
            x["status"] == "SAME_REPAIR_SETTING_MISMATCH_RESEARCH_HOLD" for x in rows),
        "current_source_alignment": sum(x["status"] in (
            "YAHOO_FACTOR_OBSERVED_UNATTESTED",
            "REPAIR_POLICY_DIFFERENCE_OBSERVED") for x in rows),
        "overall_status": "CORPORATE_ACTION_FACTORS_RESEARCH_HOLD",
        "rows": rows,
    }
    write_json(out_dir / "report.json", result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="research/kalman_daily20/universe.json")
    p.add_argument("--market", required=True)
    p.add_argument("--qc", required=True)
    p.add_argument("--out-dir", required=True)
    a = p.parse_args()
    report = run(load_spec(a.config), a.market, a.qc, a.out_dir)
    print("DAILY20_YAHOO_FACTOR_TRACE", report["vendor_history_observed"], "/25",
          "unaligned_or_missing", 25-report["current_source_alignment"],
          "CERTIFIED", report["independent_corporate_actions_certified"], "/25 HOLD")


if __name__ == "__main__":
    main()
