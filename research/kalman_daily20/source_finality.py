#!/usr/bin/env python3
"""Prospective Daily20 EOD source-finality evidence (research-only, fail closed).

Runs BEFORE initial forward-seal steps. It never overwrites the quote or
asserts a public site, FDR, Yahoo, or Alpaca IEX quote is an exchange-
certified regular-session closing print. In the absence of independently
certified close/adjustment proof, every instrument remains provisional.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path

import pandas as pd

from daily20 import load_spec, market_file, write_json
from refresh_incremental import read_verified_cache

VERSION = "daily20-source-finality-v1"
REFERENCE_VERSION = "daily20-quote-reference-v1"
REGULAR = "REGULAR_CLOSE"
AFTER_HOURS = "AFTER_HOURS"
UNKNOWN = "UNKNOWN"
QUOTE_TYPES = (REGULAR, AFTER_HOURS, UNKNOWN)
MAX_RAW_PRICE_DIFFERENCE_USD = 0.005
MATERIAL_REPLAY_RELATIVE = 0.001
OHLCV = ("open", "high", "low", "close", "volume")


def sha(blob):
    return sha256(blob).hexdigest()


def checked_reference(path, session, symbols):
    """Optional user/third-party reference, not a trusted feed or certification."""
    if not path:
        return {}
    payload = json.loads(Path(path).read_text())
    if payload.get("schema") != REFERENCE_VERSION or payload.get("session") != session:
        raise RuntimeError("FINALITY_REFERENCE_SCHEMA_OR_SESSION_MISMATCH")
    if payload.get("research_only") is not True:
        raise RuntimeError("FINALITY_REFERENCE_RESEARCH_ONLY_REQUIRED")
    rows = payload.get("quotes", [])
    if not isinstance(rows, list) or len(rows) > len(symbols):
        raise RuntimeError("FINALITY_REFERENCE_INVALID_COUNT")
    by_symbol = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("FINALITY_REFERENCE_NOT_OBJECT")
        symbol = row.get("symbol")
        if symbol in by_symbol or symbol not in symbols:
            raise RuntimeError("FINALITY_REFERENCE_DUPLICATE_OR_UNKNOWN_SYMBOL")
        typ = row.get("quote_type")
        if typ not in QUOTE_TYPES:
            raise RuntimeError("FINALITY_REFERENCE_UNDEFINED_QUOTE_TYPE")
        provider = row.get("provider")
        feed = row.get("feed")
        fetched = row.get("fetched_at_utc")
        time = row.get("observed_at_utc")
        adjustment = row.get("adjustment")
        # Full provenance is required even to label a quote a comparison reference.
        if (not isinstance(provider, str) or not provider.strip()
                or not isinstance(feed, str) or not feed.strip()
                or adjustment not in ("RAW", "YAHOO_AUTO_ADJUSTED", "UNKNOWN")
                or not isinstance(fetched, str) or not isinstance(time, str)
                or not fetched.endswith("Z") or not time.endswith("Z")):
            raise RuntimeError("FINALITY_REFERENCE_PROVENANCE_INCOMPLETE")
        try:
            observed = pd.Timestamp(time)
            retrieved = pd.Timestamp(fetched)
        except Exception as e:
            raise RuntimeError("FINALITY_REFERENCE_INVALID_TIME") from e
        if observed.tzinfo is None or retrieved.tzinfo is None:
            raise RuntimeError("FINALITY_REFERENCE_TIME_ZONE_ABSENT")
        # Avoid silently merging a different day, pre-market, or post-market bar.
        if observed.tz_convert("America/New_York").date().isoformat() != session:
            raise RuntimeError("FINALITY_REFERENCE_OBSERVATION_SESSION_MISMATCH")
        if retrieved < observed:
            raise RuntimeError("FINALITY_REFERENCE_FUTURE_OBSERVATION")
        value = row.get("price")
        if typ == UNKNOWN:
            if value is not None:
                raise RuntimeError("FINALITY_UNKNOWN_QUOTE_WITH_PRICE")
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise RuntimeError("FINALITY_REFERENCE_NONPOSITIVE_OR_UNSAFE_PRICE")
        # A self-declared independence or certification claim is not trusted.
        # No reference object can set status=VERIFIED.
        by_symbol[symbol] = dict(row)
    return by_symbol


def classify_quote(primary_close, is_adjusted, reference):
    if reference is None:
        return "NO_INDEPENDENT_REGULAR_CLOSE_REFERENCE"
    typ = reference["quote_type"]
    if typ == UNKNOWN:
        return "UNKNOWN_REFERENCE_QUOTE_TYPE"
    value = reference["price"]
    # A Yahoo-adjusted close cannot be directly compared to independent raw
    # closing prints without an independently validated corporate-action factor.
    if is_adjusted and reference["adjustment"] != "YAHOO_AUTO_ADJUSTED":
        return "ADJUSTMENT_CONVENTION_NOT_COMPARABLE"
    if not is_adjusted and reference["adjustment"] != "RAW":
        return "ADJUSTMENT_CONVENTION_NOT_COMPARABLE"
    identical = abs(primary_close - value) <= MAX_RAW_PRICE_DIFFERENCE_USD
    if typ == AFTER_HOURS:
        return ("AFTER_HOURS_QUOTE_MATCH_RESEARCH_HOLD"
                if identical else "AFTER_HOURS_QUOTE_DIFFERENT_RESEARCH_HOLD")
    return ("PUBLISHED_REGULAR_REFERENCE_MATCH_NOT_CERTIFIED"
            if identical else "PUBLISHED_REGULAR_REFERENCE_CONFLICT_HOLD")


def _last_bar(path, expected):
    p = Path(path)
    if not p.is_file():
        raise RuntimeError("FINALITY_MISSING_PARQUET:" + str(p))
    raw = pd.read_parquet(p)
    if "timestamp" not in raw or any(c not in raw for c in OHLCV) or "is_adjusted" not in raw:
        raise RuntimeError("FINALITY_BAR_SCHEMA_INVALID:" + str(p))
    idx = pd.to_datetime(raw["timestamp"], utc=True, errors="raise")
    if idx.isna().any() or idx.duplicated().any():
        raise RuntimeError("FINALITY_DUPLICATED_TIMESTAMP")
    date = idx.dt.date.astype(str)
    subset = raw.loc[date == expected]
    if len(subset) != 1 or expected != date.iloc[-1]:
        raise RuntimeError("FINALITY_EXPECTED_DATE_NOT_LATEST:" + str(p))
    if raw["is_adjusted"].nunique() != 1:
        raise RuntimeError("FINALITY_MIXED_ADJUSTMENT")
    v = subset.iloc[0]
    vals = {c: float(v[c]) for c in OHLCV}
    if any(not math.isfinite(v) for v in vals.values()) or vals["close"] <= 0 or vals["volume"] < 0:
        raise RuntimeError("FINALITY_INVALID_MARKET_DATA")
    return {"ohlcv":vals,"is_adjusted":bool(v["is_adjusted"]),
            "original_bar_timestamp":str(idx[date == expected].iloc[0]),
            "file_sha256":sha(p.read_bytes()),"rows":len(raw)}


def _replay_prior(prior_zip, spec, session, current):
    if not prior_zip:
        return {"status":"NO_PRIOR_ARCHIVE_PROVIDED","same_session":False,
                "material_replay_symbols":[]}
    universe = json.loads((Path(__file__).resolve().parents[0]/"universe.json").read_text())
    # Never treat an unverified cached ZIP as a prior original quote.
    expected_keys = {"yf_" + x.lower().replace("^","") for x in spec["core"]+spec["context"]}
    manifest,prior = read_verified_cache(Path(prior_zip).read_bytes(),expected_keys)
    prev_session = str(manifest.get("data_expected_last_closed_xnys"))
    if prev_session != session:
        return {"status":"PRIOR_SESSION_DIFFERENT","prior_session":prev_session,
                "same_session":False,"material_replay_symbols":[]}
    changed = []
    details = {}
    for symbol in spec["core"]+spec["context"]:
        prev = prior["yf_"+symbol.lower().replace("^","")]
        stamps = pd.to_datetime(prev["timestamp"],utc=True).dt.date.astype(str)
        old = prev.loc[stamps == session]
        if len(old) != 1:
            raise RuntimeError("FINALITY_PRIOR_SAME_SESSION_MISSING_ASSET:" + symbol)
        old_row = old.iloc[0]
        now = current[symbol]["ohlcv"]
        vals = {}
        for c in OHLCV:
            before = float(old_row[c])
            delta = now[c] - before
            vals[c] = {"old":before,"new":now[c],"delta":delta}
        rel = abs(vals["close"]["delta"] / float(old_row["close"]))
        material = rel > MATERIAL_REPLAY_RELATIVE
        details[symbol] = {
            "relative_close_change":rel,
            "close_material_gt10bps":material,
            "volume_changed": vals["volume"]["delta"] != 0,
        }
        if material:
            changed.append(symbol)
    return {"status":"SAME_SESSION_COMPARISON","same_session":True,
            "prior_session":prev_session,"material_replay_symbols":changed,
            "per_symbol":details}


def run(spec, qc_path, market, out, *, reference=None, prior_zip=None, fetched_at=None):
    qc=json.loads(Path(qc_path).read_text())
    session=str(qc.get("expected_session"))
    core=list(spec["core"])
    names=core+list(spec["context"])
    if len(names) != 26 or len(set(names)) != 26:
        raise RuntimeError("FINALITY_NOT_26_DISTINCT_ASSETS")
    if qc.get("status") != "READY" or qc.get("ready") != 26:
        raise RuntimeError("FINALITY_PRIOR_OHLCV_QC_NOT_READY")
    quotes=checked_reference(reference,session,set(names))
    market = Path(market)
    captured = {}
    for symbol in names:
        captured[symbol]=_last_bar(market_file(market,symbol),session)
    replay=_replay_prior(prior_zip,spec,session,captured)
    lines=[]
    for symbol in names:
        current=captured[symbol]
        ref=quotes.get(symbol)
        status=classify_quote(current["ohlcv"]["close"],current["is_adjusted"],ref)
        lines.append({
            "symbol":symbol, "group":"CORE_20" if symbol in core else "CONTEXT_6",
            "session":session,
            "yahoo_close":current["ohlcv"]["close"],
            "yahoo_is_adjusted":current["is_adjusted"],
            "source_bar_utc":current["original_bar_timestamp"],
            "source_parquet_sha256":current["file_sha256"],
            "source_parquet_rows":current["rows"],
            "reference_type":ref["quote_type"] if ref else UNKNOWN,
            "reference_provider":ref.get("provider") if ref else None,
            "reference_feed":ref.get("feed") if ref else None,
            "reference_observed_at_utc":ref.get("observed_at_utc") if ref else None,
            "reference_fetched_at_utc":ref.get("fetched_at_utc") if ref else None,
            "reference_price":ref.get("price") if ref else None,
            "reference_adjustment":ref.get("adjustment") if ref else None,
            "reference_certified":False,
            "result":status,
            "finality_verified":False,
            "provisional_research_only":True,
        })
    status="REPLAY_DRIFT_RESEARCH_HOLD" if replay["material_replay_symbols"] else "SOURCE_FINALITY_HOLD"
    report={
        "version":VERSION,
        "session":session,
        "status":status,
        "research_only":True,
        "live_execution":False,
        "production_writes":False,
        "strategy_promoted":False,
        "external_regular_close_independent_certified":False,
        "research_hold":True,
        "new_signals_must_be_provisional":True,
        "verified":0,
        "required":26,
        "examined":len(lines),
        "reference_coverage":len(quotes),
        "time_collected_utc":fetched_at or datetime.now(timezone.utc).isoformat(),
        "source_run_id":__import__("os").environ.get("GITHUB_RUN_ID","local"),
        "source_commit_sha":__import__("os").environ.get("GITHUB_SHA","local"),
        "replay":replay,
        "symbols":lines,
        "disclosure":"No authenticated independent exchange-certified close feed connected. Valid structural data is not proof of 16:00 ET price finality.",
    }
    if report["examined"] != 26 or any(item["finality_verified"] for item in lines):
        raise RuntimeError("FINALITY_UNSUPPORTED_GO_STATE")
    write_json(out, report)
    print(json.dumps({"DAILY20_SOURCE_FINALITY":{
        "session":session,"status":status,"verified":0,"required":26,
        "reference_count":len(quotes),
        "material_same_session_replay":len(replay["material_replay_symbols"]),
    }}))
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",default="research/kalman_daily20/universe.json")
    p.add_argument("--market",required=True)
    p.add_argument("--qc",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--reference",default=None)
    p.add_argument("--prior-zip",default=None)
    a=p.parse_args()
    run(load_spec(a.config),a.qc,a.market,a.out,
        reference=a.reference,prior_zip=a.prior_zip)


if __name__=="__main__":
    main()
