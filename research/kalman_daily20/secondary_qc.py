#!/usr/bin/env python3
"""Diagnostic-only secondary-provider and expected-session comparison.

No live execution and no unconditional second-source independence claim.
FinanceDataReader may itself route through Yahoo/third-party upstreams.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from daily20 import load_bars, market_file, write_json

PROBES = ("SPY", "QQQ", "NVDA", "XOM")


def compare_return_series(primary_close, alternate_close, *, threshold_median=0.006, threshold_p95=0.02):
    primary = pd.to_numeric(primary_close, errors="coerce").sort_index()
    alternate = pd.to_numeric(alternate_close, errors="coerce").sort_index()
    primary.index = pd.to_datetime(primary.index).normalize()
    alternate.index = pd.to_datetime(alternate.index).normalize()
    joined = pd.concat({"primary": primary, "alternate": alternate}, axis=1, join="inner").dropna()
    if len(joined) < 15:
        return {"status": "UNVERIFIED", "reason": "LESS_THAN_15_COMMON_SESSIONS",
                "overlap_sessions": len(joined)}
    # Returns, not absolute levels: upstream dividend/split adjustment conventions can differ.
    ret = joined.pct_change(fill_method=None).dropna()
    if ret.empty:
        return {"status": "UNVERIFIED", "reason": "NO_RETURN_PAIRS", "overlap_sessions": len(joined)}
    abs_drift = (ret.primary - ret.alternate).abs()
    median = float(abs_drift.median())
    p95 = float(abs_drift.quantile(.95))
    return {
        "status": "ALIGNED" if median <= threshold_median and p95 <= threshold_p95 else "DISAGREEMENT",
        "overlap_sessions": len(joined), "return_pairs": len(ret),
        "mean_abs_return_gap": float(abs_drift.mean()),
        "median_abs_return_gap": median, "p95_abs_return_gap": p95,
        "daily_return_correlation": (float(ret.primary.corr(ret.alternate))
                                     if len(ret) >= 3 and np.isfinite(ret.primary.corr(ret.alternate))
                                     else None),
        "last_session": str(joined.index[-1].date()),
    }


def run(market, out, end_exclusive, *, secondary_fetcher=None):
    report = {
        "status": "SECONDARY_DIAGNOSTIC",
        "secondary_provider": "FinanceDataReader",
        "provider_independence_verified": False,
        "research_only": True,
        "external_failures_block_primary": False,
        "source_note": "FDR may use Yahoo as upstream: this is NOT exchange-independent certification.",
        "symbols": {},
    }
    if secondary_fetcher is None:
        import FinanceDataReader as fdr
        secondary_fetcher = fdr.DataReader
    stop = pd.Timestamp(end_exclusive)
    start = (stop - pd.Timedelta(days=100)).strftime("%Y-%m-%d")
    end = stop.strftime("%Y-%m-%d")
    for symbol in PROBES:
        try:
            primary = load_bars(market_file(market, symbol))["close"].tail(80)
            secondary = secondary_fetcher(symbol, start, end)
            if secondary is None or secondary.empty or "Close" not in secondary:
                raise ValueError("secondary returned no Close price column")
            result = compare_return_series(primary, secondary["Close"])
        except Exception as ex:
            result = {"status": "UNAVAILABLE", "reason": type(ex).__name__,
                      "detail": str(ex)[:250]}
        report["symbols"][symbol] = result
    report["aligned"] = sum(x["status"] == "ALIGNED" for x in report["symbols"].values())
    report["disagreements"] = sum(x["status"] == "DISAGREEMENT" for x in report["symbols"].values())
    report["unverified"] = len(PROBES) - report["aligned"] - report["disagreements"]
    report["status"] = (
        "DISAGREEMENT_DETECTED" if report["disagreements"] else
        "PROVIDER_ORIGIN_UNVERIFIED"
    )
    write_json(out, report)
    print(json.dumps({"DAILY20_SECONDARY": {"status": report["status"],
                                           "aligned": report["aligned"],
                                           "disagreements": report["disagreements"],
                                           "unverified": report["unverified"]}}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--end-date", required=True)
    args = parser.parse_args()
    run(args.market, args.out, args.end_date)


if __name__ == "__main__":
    main()
