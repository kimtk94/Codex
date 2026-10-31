#!/usr/bin/env python3
"""Research-only audit of archived aggregated RR>=2.0 SIP evidence (no raw candles)."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import zipfile
from pathlib import Path

ARMS = ("BASE_STOP125_TP300", "MODERATE_STOP100_TP250", "TIGHT_STOP075_TP225")
MODELS = ("P_unweighted", "V_unweighted")
HORIZONS = ("1", "2", "4")
YEARS = ("2025", "2026")


def audit_archive(path: Path) -> dict:
    archive_bytes = path.read_bytes()
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:
            raise ValueError("ARCHIVE_CRC")
        if not {"regime_rr2_feasibility.json", "source_qa.json"}.issubset(z.namelist()):
            raise ValueError("MISSING_AGGREGATE_EVIDENCE")
        report_bytes = z.read("regime_rr2_feasibility.json")
        d = json.loads(report_bytes)
        qa = json.loads(z.read("source_qa.json"))
    if d.get("schema") != "kalman-regime-netRR2-geometry-feasibility-v1":
        raise ValueError("WRONG_SCHEMA")
    if (d.get("status") != "RESEARCH_ONLY_NO_TRADE_PROMOTION"
            or d.get("decision") != "HOLD"
            or d.get("no_live_or_broker_change") is not True
            or d.get("2025_2026_not_fresh_out_of_sample") is not True):
        raise ValueError("UNSAFE_RESEARCH_GATE")
    if d.get("hard_minimum_net_RR") != 2.0 or d.get("roundtrip_cost_fraction") != .003:
        raise ValueError("RR_OR_COST_DRIFT")
    if qa.get("source", {}).get("feed") != "sip" or qa.get("source", {}).get("timeframe") != "15Min":
        raise ValueError("BAD_SOURCE_FEED")
    quality = d["data_qa"]
    if quality.get("partial_or_missing_symbol_sessions") != 0 or quality.get("complete_symbol_sessions") != 3555:
        raise ValueError("INCOMPLETE_SOURCE")
    for arm, (sl, tp) in zip(ARMS, ((1.25, 3.), (1., 2.5), (.75, 2.25))):
        a = d["research_policies"][arm]
        if (a["stop_atr_mult"], a["target_atr_mult"]) != (sl, tp):
            raise ValueError("ARM_CHANGED")
    rows = []
    for symbol, years in sorted(d["by_symbol"].items()):
        for year in YEARS:
            for model in MODELS:
                candidates_by_arm = set()
                for arm in ARMS:
                    entry = years[year][model][arm]
                    opportunity = entry["opportunity_feasibility"]
                    signal_n = opportunity["original_signal_count"]
                    passed = opportunity["passed_pre_entry_geometry"]
                    first_failure = opportunity["rejection_causes"]
                    if (sum(first_failure.values()) != signal_n
                            or first_failure.get("PASS", 0) != passed
                            or opportunity.get("causes_are_hierarchical_first_failure") is not True):
                        raise ValueError("FIRST_FAILURE_OR_COUNT_INVALID")
                    candidates_by_arm.add(signal_n)
                    for horizon in HORIZONS:
                        stats = entry["by_horizon"][horizon]["MIN_NET_RR_GATE"]
                        n = stats["trades"]
                        expect = stats["realized_expectancy_R"]
                        exits = stats["exit_reason_counts"]
                        if (n < 0 or n > passed or stats["signal_count"] != signal_n
                                or sum(exits.values()) != n):
                            raise ValueError("EXIT_OR_COHORT_MISMATCH")
                        if (n == 0 and expect is not None) or (
                            n > 0 and (not isinstance(expect, (int, float)) or not math.isfinite(expect))
                        ):
                            raise ValueError("INVALID_REALIZED_EXPECTANCY")
                        rows.append({
                            "symbol": symbol, "year": int(year), "model": model,
                            "arm": arm, "hold_sessions": int(horizon),
                            "signals": signal_n, "geometry_pass": passed, "trades": n,
                            "first_reject_stop": first_failure.get("STOP_TOO_WIDE", 0),
                            "first_reject_target": first_failure.get("TARGET_TOO_FAR", 0),
                            "first_reject_rr": first_failure.get("NET_RR_BELOW_MINIMUM", 0),
                            "gap_stop_exits": exits.get("STOP_GAP", 0),
                            "stop_exits": exits.get("STOP", 0),
                            "target_exits": exits.get("TARGET", 0) + exits.get("TARGET_LIMIT", 0),
                            "time_exits": exits.get("TIME_CLOSE", 0),
                            "realized_expectancy_R": expect,
                            "net_mean_trade_pct": stats["average_net_trade_pct"],
                            "mdd_pct": stats["mdd_eod_pct"],
                            "cumulative_return_pct": stats["cum_return_pct"],
                        })
                if len(candidates_by_arm) != 1:
                    raise ValueError("NONIDENTICAL_ARM_SIGNAL_COHORT")

    def get(s, y, m, arm, h=1):
        return next(x for x in rows if (x["symbol"], x["year"], x["model"], x["arm"], x["hold_sessions"]) == (s, y, m, arm, h))

    for year, n in ((2025, 80), (2026, 46)):
        for arm in ARMS:
            row = get("COIN", year, "V_unweighted", arm)
            if (row["signals"], row["geometry_pass"], row["first_reject_stop"]) != (n, 0, n):
                raise ValueError("COIN_REFERENCE_MISMATCH")
    for year, n in ((2025, 23), (2026, 27)):
        if get("IWM", year, "V_unweighted", ARMS[0])["trades"] != n:
            raise ValueError("IWM_REFERENCE_MISMATCH")
    stability = []
    for symbol in d["by_symbol"]:
        for model in MODELS:
            for arm in ARMS:
                for horizon in (1, 2, 4):
                    pair = [get(symbol, int(y), model, arm, horizon) for y in YEARS]
                    stability.append({
                        "symbol": symbol, "model": model, "arm": arm,
                        "hold_sessions": horizon,
                        "both_2025_2026_positive": all(
                            x["trades"] > 0 and x["realized_expectancy_R"] > 0 for x in pair),
                        "decision": "HOLD_REUSED_NOT_FRESH_OOS",
                    })
    return {
        "schema": "kalman-rr2-archive-independent-audit-v1",
        "status": "VERIFIED_RESEARCH_LIVE_HOLD",
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "source_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "source_qa_status": qa["status"],
        "independent_reject_causes_available": False,
        "no_live_change": True,
        "rows": rows,
        "stability": stability,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument("--out", default="outputs/rr2_entry_audit/archive_summary.json", type=Path)
    a = p.parse_args()
    result = audit_archive(a.archive)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2) + "\n")
    with a.out.with_suffix(".csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=result["rows"][0].keys())
        writer.writeheader()
        writer.writerows(result["rows"])
    print(json.dumps({
        "status": result["status"],
        "rows": len(result["rows"]),
        "positive_2025_2026_sleeves": sum(
            x["both_2025_2026_positive"] for x in result["stability"]),
        "live": "HOLD",
    }))


if __name__ == "__main__":
    main()
