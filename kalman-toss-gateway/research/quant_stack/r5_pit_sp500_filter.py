from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

SOURCE_URL = "https://raw.githubusercontent.com/chinobing/historical_sp500_constituents/main/sp_500_historical_components.csv"
NY = ZoneInfo("America/New_York")
# Identity aliases where the research price history uses today's ticker over
# older dates. Eligibility is accepted if either ticker was an index member.
ALIASES = {
    "BNY": {"BNY", "BK"},
}


def norm(x: str) -> str:
    return str(x).strip().upper().replace("-", ".")


def fetch(url: str, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def load_membership(path: Path) -> dict:
    hist = pd.read_csv(path)
    hist["date"] = pd.to_datetime(hist["date"], errors="coerce").dt.date
    hist = hist.dropna(subset=["date"]).sort_values("date")
    return {
        row.date: {norm(x) for x in str(row.tickers).split(",") if str(x).strip()}
        for row in hist.itertuples(index=False)
    }


def eligible(symbol: str, members: set[str]) -> bool:
    symbol = norm(symbol)
    aliases = ALIASES.get(symbol, {symbol})
    return bool(aliases.intersection(members))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rankings", type=Path, required=True)
    p.add_argument("--membership-cache", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--status", type=Path, required=True)
    p.add_argument("--refresh", action="store_true")
    args = p.parse_args()

    if args.refresh or not args.membership_cache.is_file():
        sha = fetch(SOURCE_URL, args.membership_cache)
    else:
        sha = hashlib.sha256(args.membership_cache.read_bytes()).hexdigest()

    membership = load_membership(args.membership_cache)
    membership_dates = sorted(membership)
    if not membership_dates:
        raise RuntimeError("historical membership is empty")

    rankings = pd.read_parquet(args.rankings)
    rankings["timestamp"] = pd.to_datetime(rankings["timestamp"], utc=True, errors="coerce")
    session_dates = rankings["timestamp"].dt.tz_convert(NY).dt.date

    # Source is daily. If a date is missing, use the latest available snapshot
    # at or before that trading date.
    date_series = pd.Series(membership_dates)
    unique_sessions = sorted(set(session_dates.dropna()))
    resolved = {}
    for d in unique_sessions:
        idx = date_series.searchsorted(d, side="right") - 1
        if idx < 0:
            resolved[d] = None
        else:
            resolved[d] = membership_dates[int(idx)]

    keep = []
    excluded_counts: dict[str, int] = {}
    first_exclusions = []
    for i, row in enumerate(rankings.itertuples(index=False)):
        d = session_dates.iloc[i]
        md = resolved.get(d)
        ok = False
        if md is not None:
            ok = eligible(row.symbol, membership[md])
        keep.append(ok)
        if not ok:
            sym = str(row.symbol)
            excluded_counts[sym] = excluded_counts.get(sym, 0) + 1
            if len(first_exclusions) < 100:
                first_exclusions.append({"date": str(d), "symbol": sym})

    mask = pd.Series(keep, index=rankings.index)
    out = rankings.loc[mask].copy()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.output, index=False)

    # Count unique eligible symbols by broad period for auditability.
    temp = out[["timestamp", "symbol"]].copy()
    temp["year"] = temp["timestamp"].dt.year
    eligible_by_year = {
        str(int(y)): int(g["symbol"].nunique())
        for y, g in temp.groupby("year")
    }
    status = {
        "schema_version": "r5-pit-sp500-conservative-v1",
        "status": "COMPLETE",
        "source_url": SOURCE_URL,
        "source_sha256": sha,
        "source_is_unofficial_research_reference": True,
        "input_rows": int(len(rankings)),
        "output_rows": int(len(out)),
        "excluded_rows": int((~mask).sum()),
        "input_symbols": int(rankings["symbol"].nunique()),
        "output_symbols": int(out["symbol"].nunique()),
        "eligible_symbols_by_year": eligible_by_year,
        "top_excluded_symbols": sorted(
            excluded_counts.items(), key=lambda kv: (-kv[1], kv[0])
        )[:25],
        "first_exclusions": first_exclusions,
        "limitations": [
            "Filters only the existing static 93-symbol score artifact.",
            "Does not add historical constituents that disappeared before the current universe was defined.",
            "Therefore this is PIT-conservative, not fully survivorship-bias-free.",
        ],
    }
    args.status.parent.mkdir(parents=True, exist_ok=True)
    args.status.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
