#!/usr/bin/env python3
"""Daily20 isolated research orchestrator: universe, QC, annual OOS baseline."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DEFAULT_SPEC = Path("research/kalman_daily20/universe.json")
DEFAULT_CANONICAL = Path("kalman-toss-gateway/config/market-data-v2-universe.json")
ETFS = {"SPY", "QQQ", "QLD", "IWM", "SMH", "HYG", "LQD", "TLT", "GLD"}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")


def load_spec(path=DEFAULT_SPEC):
    spec = json.loads(Path(path).read_text())
    core, context = spec["core"], spec["context"]
    if len(core) != 20 or len(context) != 6 or len(set(core + context)) != 26:
        raise ValueError("expected precisely 20 distinct core + 6 distinct context symbols")
    if not set(spec["high_risk_shadow_only"]).issubset(core):
        raise ValueError("shadow-only risk names must be in core universe")
    if spec.get("live_execution") is not False:
        raise ValueError("LIVE forbidden in Daily20 research")
    return spec


def slug(symbol):
    return re.sub("[^a-z0-9]+", "_", symbol.lower()).strip("_")


def market_file(root, symbol):
    return Path(root) / "raw" / "yfinance" / ("yf_" + slug(symbol) + ".parquet")


def feature_file(root, symbol):
    return Path(root) / "talib" / (slug("VIX" if symbol == "^VIX" else symbol) + ".parquet")


def build_universe(spec, canonical):
    source = {str(r.get("provider_symbol", "")).upper(): r for r in canonical["assets"]
              if r.get("provider") == "yfinance"}
    assets = []
    for symbol in spec["core"] + spec["context"]:
        original = source.get(symbol, {})
        is_index = symbol.startswith("^")
        assets.append({
            "key": "yf_" + slug(symbol),
            "group": "DAILY20_CORE" if symbol in spec["core"] else "DAILY20_CONTEXT",
            "provider": "yfinance",
            "symbol": original.get("symbol", "VIX" if is_index else symbol),
            "provider_symbol": symbol,
            "market": "US", "currency": "USD",
            "kind": original.get("kind", "index" if is_index else "etf" if symbol in ETFS else "equity"),
            "required": True, "adjusted": not is_index,
        })
    if len(set(x["key"] for x in assets)) != 26:
        raise ValueError("non-unique generated data keys")
    return {"version": spec["version"], "research_only": True, "assets": assets, "comparisons": []}


def last_completed_nyse(now=None):
    import exchange_calendars as xc
    import pandas as pd
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    cutoff = now - pd.Timedelta(minutes=45)
    cal = xc.get_calendar("XNYS")
    sessions = cal.sessions_in_range((cutoff - pd.Timedelta(days=16)).date(), cutoff.date())
    closed = [s for s in sessions if cal.session_close(s) <= cutoff]
    if not closed:
        raise ValueError("no fully closed NYSE session")
    return closed[-1].date()


def load_bars(path):
    import pandas as pd
    df = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        raise ValueError("canonical OHLCV missing: " + repr(sorted(required - set(df.columns))))
    df["date"] = pd.to_datetime(df["timestamp"], utc=True, errors="raise").dt.tz_localize(None).dt.normalize()
    df = df.sort_values("date")
    if df["date"].isna().any() or df["date"].duplicated().any():
        raise ValueError("duplicate or invalid daily timestamps")
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.set_index("date")


def audit_one(symbol, market, features, expected):
    import pandas as pd
    p, q = market_file(market, symbol), feature_file(features, symbol)
    row = {"symbol": symbol, "status": "BLOCKED", "errors": []}
    errs = row["errors"]
    if not (p.exists() and q.exists()):
        errs.append("MISSING_PRICE_OR_FEATURE")
        return row
    try:
        df = load_bars(p)
        ft = pd.read_parquet(q)
        ft_dates = pd.to_datetime(ft["timestamp"], utc=True).dt.date
        row.update(rows=int(len(df)), first=str(df.index.min().date()),
                   last=str(df.index.max().date()))
        if len(df) < 252:
            errs.append("LESS_THAN_252_BARS")
        if df.index.max().date() != expected or ft_dates.max() != expected:
            errs.append("NOT_LATEST_COMPLETED_NYSE_SESSION")
        ohlc = df[["open", "high", "low", "close"]]
        if symbol == "^VIX":
            # Yahoo VIX keeps some all-null placeholder observations. Preserve
            # those dates as missing context, never fill them into model inputs.
            incomplete = ohlc.isna().any(axis=1)
            all_null = ohlc.isna().all(axis=1)
            if ((incomplete & ~all_null).any() or all_null.mean() > 0.04
                    or bool(all_null.iloc[-1]) or int(all_null.tail(30).sum()) > 2):
                errs.append("INVALID_VIX_CONTEXT_GAPS")
            elif all_null.any():
                row["missing_context_sessions"] = int(all_null.sum())
                row["warnings"] = ["VIX_ALL_NULL_PLACEHOLDERS_PRESERVED_AS_MISSING"]
        elif ohlc.isna().any().any():
            errs.append("INVALID_OHLC")
        if (ohlc.dropna() <= 0).any().any():
            errs.append("NONPOSITIVE_OHLC")
        if (df["high"] + 1e-7 < df[["open", "low", "close"]].max(axis=1)).any():
            errs.append("INVALID_HIGH")
        if (df["low"] - 1e-7 > df[["open", "high", "close"]].min(axis=1)).any():
            errs.append("INVALID_LOW")
        if (df["volume"].dropna() < 0).any():
            errs.append("NEGATIVE_VOLUME")
        if "talib_v2_rsi14" not in ft.columns or ft["talib_v2_rsi14"].notna().sum() < 100:
            errs.append("FEATURE_RSI_UNAVAILABLE")
        if len(ft) != len(df):
            errs.append("PRICE_FEATURE_LENGTH_MISMATCH")
    except Exception as exc:
        errs.append(type(exc).__name__ + ": " + str(exc)[:150])
    row["status"] = "READY" if not errs else "BLOCKED"
    return row


def audit_all(manifest, market, features, out, now=None):
    cfg = json.loads(Path(manifest).read_text())
    if len(cfg.get("assets", [])) != 26:
        raise ValueError("not a 26-asset Daily20 universe")
    expected = last_completed_nyse(now)
    results = [audit_one(v["provider_symbol"], market, features, expected)
               for v in cfg["assets"]]
    status = "READY" if all(r["status"] == "READY" for r in results) else "BLOCKED"
    result = {"status": status, "expected_session": str(expected),
              "required": 26, "ready": sum(r["status"] == "READY" for r in results),
              "research_only": True, "symbols": results}
    write_json(out, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="mode", required=True)
    u = subs.add_parser("universe")
    u.add_argument("--config", default=str(DEFAULT_SPEC))
    u.add_argument("--canonical", default=str(DEFAULT_CANONICAL))
    u.add_argument("--out", required=True)
    a = subs.add_parser("audit")
    a.add_argument("--manifest", required=True)
    a.add_argument("--market", required=True)
    a.add_argument("--features", required=True)
    a.add_argument("--out", required=True)
    t = subs.add_parser("train")
    t.add_argument("--config", default=str(DEFAULT_SPEC))
    t.add_argument("--market", required=True)
    t.add_argument("--features", required=True)
    t.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.mode == "universe":
        result = build_universe(load_spec(args.config), json.loads(Path(args.canonical).read_text()))
        write_json(args.out, result)
        print("UNIVERSE_READY", len(result["assets"]))
    elif args.mode == "audit":
        result = audit_all(args.manifest, args.market, args.features, args.out)
        print("DAILY20_AUDIT", result["status"], result["ready"], "/26")
        if result["status"] != "READY":
            raise SystemExit(2)
    else:
        from train import research
        report = research(load_spec(args.config), args.market, args.features, args.out)
        print("DAILY20_OOS", report["total_oos_trades"], "trades",
              report["latest_score_count"], "research-only scores")


if __name__ == "__main__":
    main()
