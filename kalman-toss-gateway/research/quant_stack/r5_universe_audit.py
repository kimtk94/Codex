from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


SCHEMA_VERSION = "kalman-r5-universe-audit-v1"
PIT_COLUMNS = {
    "effective_from", "effective_to", "listed_at", "delisted_at",
    "membership_start", "membership_end", "universe_as_of",
}


def audit(path: Path) -> dict:
    df = pd.read_parquet(path)
    if "symbol" not in df.columns or "timestamp" not in df.columns:
        raise ValueError("rankings must contain symbol and timestamp")
    z = df[["symbol", "timestamp"]].copy()
    z["symbol"] = z["symbol"].astype(str).str.upper().str.strip()
    z["timestamp"] = pd.to_datetime(z["timestamp"], utc=True, errors="coerce")
    z = z.dropna(subset=["timestamp"]).loc[lambda x: x["symbol"].ne("")]

    month_sets = (
        z.assign(month=z["timestamp"].dt.to_period("M").astype(str))
        .groupby("month")["symbol"]
        .agg(lambda s: frozenset(s))
    )
    distinct_memberships = len(set(month_sets.tolist()))
    first_set = month_sets.iloc[0] if len(month_sets) else frozenset()
    last_set = month_sets.iloc[-1] if len(month_sets) else frozenset()
    pit_cols_present = sorted(PIT_COLUMNS.intersection(df.columns))

    constant = bool(len(month_sets) and distinct_memberships == 1)
    risk = "HIGH" if constant and not pit_cols_present else "REVIEW"
    reasons = []
    if constant:
        reasons.append("monthly universe membership is identical across the full backtest window")
    if not pit_cols_present:
        reasons.append("no point-in-time membership/listing/delisting columns are present")
    if first_set == last_set and len(first_set):
        reasons.append("first-period and last-period symbol sets are identical")

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "source": str(path),
        "start": z["timestamp"].min().isoformat(),
        "end": z["timestamp"].max().isoformat(),
        "unique_symbols": int(z["symbol"].nunique()),
        "months": int(len(month_sets)),
        "distinct_monthly_membership_sets": int(distinct_memberships),
        "constant_membership": constant,
        "point_in_time_columns_present": pit_cols_present,
        "survivorship_risk": risk,
        "risk_reasons": reasons,
        "first_period_symbols": sorted(first_set),
        "last_period_symbols": sorted(last_set),
        "interpretation": (
            "This audit does not prove survivorship bias by itself; it proves that the supplied backtest artifact "
            "does not encode changing point-in-time membership. Historical performance should therefore be labeled "
            "static-universe until a dated membership source is supplied."
        ),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rankings", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = audit(args.rankings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
