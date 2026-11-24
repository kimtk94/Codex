#!/usr/bin/env python3
"""Immutable, research-only evidence for an explicitly retrospective data refresh.

Never creates forward signal events and never writes to the canonical Drive ZIPs.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import exchange_calendars as xc
import pandas as pd

from daily20 import audit_one, last_completed_nyse, load_bars, market_file, feature_file, write_json

VERSION = "kalman-retrospective-data-backfill-v1"


def check_target(session: str, *, asof=None) -> date:
    try:
        day = date.fromisoformat(session)
    except (TypeError, ValueError) as exc:
        raise ValueError("TARGET_SESSION_NOT_ISO_DATE") from exc
    if str(day) != session:
        raise ValueError("TARGET_SESSION_NOT_ISO_DATE")
    cal = xc.get_calendar("XNYS")
    if not cal.is_session(pd.Timestamp(day)):
        raise ValueError("TARGET_NOT_XNYS_SESSION")
    if day > (asof or last_completed_nyse()):
        raise ValueError("TARGET_NOT_FULLY_COMPLETED")
    return day


REQUEST_VERSION = "kalman-historical-backfill-request-v1"


def check_backfill_request(path, *, asof=None):
    """Accept only an explicit one-time, research-only request tied to its filename."""
    p = Path(path)
    request = json.loads(p.read_text())
    if (request.get("version") != REQUEST_VERSION
            or request.get("classification") != "RETROSPECTIVE_BACKFILL_NOT_PROSPECTIVE"
            or request.get("research_only") is not True
            or request.get("production_writes") is not False
            or request.get("forward_events_created") != 0
            or request.get("live_execution") is not False):
        raise ValueError("INVALID_RETROSPECTIVE_GITOPS_REQUEST")
    session = request.get("session")
    if session != p.stem:
        raise ValueError("BACKFILL_REQUEST_FILENAME_SESSION_MISMATCH")
    return check_target(session, asof=asof)


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_backfill(universe: dict, market, features, session: str, *,
                    asof=None, prior_archive=None, refresh_report=None):
    target = check_target(session, asof=asof)
    assets = universe["assets"]
    if not universe.get("research_only") is True or len(assets) != 26:
        raise ValueError("BACKFILL_UNEXPECTED_UNIVERSE")
    symbols = [asset["provider_symbol"] for asset in assets]
    if len(set(symbols)) != 26:
        raise ValueError("BACKFILL_DUPLICATE_SYMBOLS")
    rows, errors = [], []
    for asset in assets:
        sym = asset["provider_symbol"]
        raw = market_file(market, sym)
        feat = feature_file(features, sym)
        item = {"symbol": sym, "raw_sha256": None, "features_sha256": None,
                "raw_last": None, "features_last": None, "status": "BLOCKED"}
        try:
            if not raw.is_file() or not feat.is_file():
                raise ValueError("MISSING_RAW_OR_FEATURE_FILE")
            bars = load_bars(raw)
            f = pd.read_parquet(feat)
            if bars.empty or f.empty or "timestamp" not in f:
                raise ValueError("EMPTY_OR_INVALID_HISTORY")
            fd = pd.to_datetime(f["timestamp"], utc=True, errors="raise").dt.date
            if fd.duplicated().any() or fd.isna().any():
                raise ValueError("DUPLICATE_FEATURE_DATES")
            if len(f) != len(bars) or set(fd) != set(bars.index.date):
                raise ValueError("PRICE_FEATURE_DATES_MISMATCH")
            bar_last = bars.index[-1].date()
            feat_last = fd.max()
            item["raw_last"], item["features_last"] = str(bar_last), str(feat_last)
            if bar_last != target or feat_last != target:
                raise ValueError("TARGET_SESSION_NOT_LAST_IN_BOTH")
            selected = bars.iloc[-1]
            if not all(pd.notna(selected[k]) for k in ("open", "high", "low", "close", "volume")):
                raise ValueError("TARGET_MISSING_OHLCV")
            if not (selected["high"] >= max(selected["open"], selected["close"])
                    and selected["low"] <= min(selected["open"], selected["close"])
                    and selected["low"] > 0):
                raise ValueError("TARGET_INVALID_OHLC")
            qc = audit_one(sym, market, features, target)
            item["quality_control"] = qc
            if qc["status"] != "READY":
                raise ValueError("STANDARD_DAILY20_QC_BLOCKED: " + ",".join(qc["errors"]))
            if not pd.to_numeric(f.loc[fd.eq(target), "talib_v2_rsi14"], errors="coerce").notna().all():
                raise ValueError("TARGET_RSI_MISSING")
            item["raw_sha256"] = sha256_file(raw)
            item["features_sha256"] = sha256_file(feat)
            item["status"] = "DATA_BACKFILLED_RESEARCH_ONLY"
        except (ValueError, KeyError, OSError, TypeError) as exc:
            item["error"] = str(exc)
            errors.append({"symbol": sym, "error": str(exc)})
        rows.append(item)
    refresh = None
    if refresh_report is not None:
        refresh = json.loads(Path(refresh_report).read_text())
        if refresh.get("status") != "READY" and refresh.get("mode") != "FULL_HISTORY":
            raise ValueError("REFRESH_REPORT_NOT_READY")
    return {
        "version": VERSION, "session": session,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "github_actions_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_commit_sha": os.environ.get("GITHUB_SHA"),
        "prior_drive_data_zip_sha256": sha256_file(prior_archive) if prior_archive else None,
        "refresh_mode_report": refresh,
        "research_only": True, "production_writes": False,
        "prospective_first_seal": False, "forward_events_created": 0,
        "classification": "RETROSPECTIVE_BACKFILL_NOT_PROSPECTIVE",
        "price_finality_independently_certified": False,
        "issuer_adjustment_factors_certified": False,
        "strategy_promoted": False, "live_execution": False,
        "status": "DATA_BACKFILL_VERIFIED" if not errors else "DATA_BACKFILL_HOLD",
        "assets_expected": 26, "assets_verified": 26 - len(errors),
        "errors": errors, "assets": rows,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--session", required=True)
    p.add_argument("--universe", required=True)
    p.add_argument("--market", required=True)
    p.add_argument("--features", required=True)
    p.add_argument("--prior-archive", required=True, help="Checksum-verified input Drive ZIP")
    p.add_argument("--refresh-report", required=True, help="Incremental/full refresh status JSON")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    report = verify_backfill(json.loads(Path(args.universe).read_text()),
                             args.market, args.features, args.session,
                             prior_archive=args.prior_archive, refresh_report=args.refresh_report)
    write_json(args.out, report)
    print(json.dumps({"status": report["status"],
                      "assets_verified": report["assets_verified"],
                      "classification": report["classification"]}))
    if report["status"] != "DATA_BACKFILL_VERIFIED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
