"""Reconcile missing market rows and candidate availability, metadata only."""
from __future__ import annotations
import argparse
import csv
from datetime import date
import json
from pathlib import Path

from data_catalog import build_catalog


def require(ok, code):
    if not ok:
        raise ValueError("GAP_LEDGER_" + code)


def day(value):
    require(isinstance(value, str) and date.fromisoformat(value).isoformat() == value,
            "DATE_INVALID")
    return value


def build_ledger(overview, summary, events, plan):
    catalog = build_catalog(plan)
    asof = day(overview["asof_date"])
    ref = catalog["reference_archive"]["session"]
    require(overview.get("integrity_failures") == [] and
            overview.get("source_claimed_asof") == catalog["source_archive"]["session"],
            "SOURCE_SESSION_OR_INTEGRITY")
    market = [r for r in summary if r["layer"] == "MARKET"]
    queue = {r["indicator"]: r for r in plan["market_queue"]}
    require(len(market) == len(queue) == overview["market_assets"] and
            {r["indicator"] for r in market} == set(queue), "UNIVERSE")
    gaps = {key: set() for key in queue}
    for event in events:
        if event["layer"] != "MARKET" or event["status"] != "GAP":
            continue
        key, dt = event["indicator"], day(event["date"])
        require(key in gaps and dt not in gaps[key] and dt <= asof, "GAP_IDENTITY")
        gaps[key].add(dt)
    rows = []
    for entry in sorted(market, key=lambda r: r["indicator"]):
        key = entry["indicator"]
        candidate = queue[key]
        first, last = day(entry["first_date"]), day(entry["last_date"])
        require(first <= last and last == candidate["source_last"] and
                entry["asof_date"] == asof and entry["schedule"] == candidate["frequency"],
                "ASSET_SOURCE_OR_CALENDAR")
        dates = gaps[key]
        require(all(first <= dt for dt in dates) and
                float(entry["missing_expected_records"]) == len(dates), "ASSET_GAP_COUNT")
        historical = sum(dt <= last for dt in dates)
        tail = len(dates) - historical
        beyond_ref = sum(dt > max(last, ref) for dt in dates)
        covered = tail - beyond_ref
        # Plans enumerate candidate counts, not individual candidate dates.
        # Never attach a candidate to an exact date from counts alone.
        consistent = ref <= asof and covered == candidate["expected_tail_rows"]
        same_basis = mismatched_basis = source_refetch = 0
        if consistent:
            n = candidate["candidate_tail_rows"]
            if candidate["adjustment_flag_matches"] is True:
                same_basis = n
            elif candidate["adjustment_flag_matches"] is False:
                mismatched_basis = n
            else:
                require(n == 0, "UNEXPECTED_CANDIDATE")
            source_refetch = candidate["candidate_missing_expected_rows"]
            unresolved = beyond_ref
        else:
            unresolved = tail
        require(tail == same_basis + mismatched_basis + source_refetch + unresolved,
                "TAIL_ACCOUNTING")
        rows.append({
            "indicator": key, "frequency": entry["schedule"], "last_observed": last,
            "audit_asof": asof, "reference_asof": ref,
            "historical_gaps": historical, "tail_gaps": tail,
            "same_basis_unapproved_candidates": same_basis,
            "basis_mismatch_candidates": mismatched_basis,
            "source_refetch_rows": source_refetch,
            "unreconciled_tail_rows": unresolved, "plan_reconciled": consistent,
            "approved_rows": 0,
        })
    fields = ("historical_gaps", "tail_gaps", "same_basis_unapproved_candidates",
              "basis_mismatch_candidates", "source_refetch_rows", "unreconciled_tail_rows",
              "approved_rows")
    totals = {key: sum(r[key] for r in rows) for key in fields}
    require(totals["historical_gaps"] + totals["tail_gaps"] ==
            overview["market_expected_row_gaps"], "TOTAL_GAP_COUNT")
    return {"version": "kalman-market-gap-ledger-v1", "research_only": True,
            "production_writes": False, "strategy_promoted": False,
            "status": "GAP_LEDGER_METADATA_ONLY_HOLD",
            "source_archive": catalog["source_archive"],
            "reference_archive": catalog["reference_archive"],
            "audit_asof": asof, "totals": totals, "assets": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    def read_json(name):
        return json.loads((out / name).read_text(encoding="utf-8"))
    def read_csv(name):
        with (out / name).open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    result = build_ledger(read_json("audit_overview.json"), read_csv("indicator_summary.csv"),
                          read_csv("missing_events.csv"), read_json("backfill_plan.json"))
    (out / "market_gap_ledger.json").write_text(json.dumps(result, indent=2) + "\n",
                                               encoding="utf-8")
    with (out / "market_gap_ledger.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(result["assets"][0]))
        writer.writeheader()
        writer.writerows(result["assets"])
    print("KALMAN_MARKET_GAP_LEDGER_HOLD", json.dumps(result["totals"], sort_keys=True))


if __name__ == "__main__":
    main()
