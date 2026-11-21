#!/usr/bin/env python3
"""Research-only RR>=2.0 ATR entry gate audit. No orders, no source market-data export.

Input CSV must be built from the frozen, point-in-time candidate signal cohort:
signal_id,symbol,signal_date,entry_price,atr
entry_price and atr must reflect only data legally known at the intended entry.
Results contain only aggregated rejection counts by symbol and year.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ARMS = {
    "baseline_1p25_3p00": (1.25, 3.00),
    "A_1p00_2p50": (1.00, 2.50),
    "B_0p75_2p25": (0.75, 2.25),
}
REQUIRED = {"signal_id", "symbol", "signal_date", "entry_price", "atr"}
REASONS = ("STOP_CAP_EXCEEDED", "TARGET_CAP_EXCEEDED", "NET_RR_BELOW_2")
CONFIG = {
    "min_net_rr": 2.0,
    "round_trip_cost_fraction": 0.003,
    "max_stop_fraction": 0.03,
    "max_target_fraction": 0.08,
    "over_cap_policy": "REJECT_NOT_CLIP",
}


def assess(atr_over_price: float, arm: tuple[float, float]) -> dict:
    """All flags independent: multiple simultaneous causes are preserved."""
    if not math.isfinite(atr_over_price) or atr_over_price <= 0:
        raise ValueError("ATR/entry must be finite and positive")
    stop = arm[0] * atr_over_price
    target = arm[1] * atr_over_price
    net_reward = target - CONFIG["round_trip_cost_fraction"]
    net_risk = stop + CONFIG["round_trip_cost_fraction"]
    net_rr = net_reward / net_risk
    flags = [
        reason for reason, blocked in (
            ("STOP_CAP_EXCEEDED", stop > CONFIG["max_stop_fraction"] + 1e-12),
            ("TARGET_CAP_EXCEEDED", target > CONFIG["max_target_fraction"] + 1e-12),
            ("NET_RR_BELOW_2", net_rr + 1e-12 < CONFIG["min_net_rr"]),
        ) if blocked
    ]
    return {
        "accepted": not flags,
        "reasons": flags,
        "primary_reason": flags[0] if flags else "PASS",
        "net_rr": net_rr,
        "stop_fraction": stop,
        "target_fraction": target,
    }


def audit(path: Path, expected: dict[tuple[str, int], int] | None = None) -> dict:
    rows = path.read_bytes()
    cohorts: dict[tuple[str, int], list[float]] = defaultdict(list)
    seen = set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError(f"missing columns {sorted(REQUIRED - set(reader.fieldnames or []))}")
        for row_num, row in enumerate(reader, start=2):
            try:
                signal_id = row["signal_id"].strip()
                symbol = row["symbol"].strip().upper()
                year = date.fromisoformat(row["signal_date"].strip()[:10]).year
                entry = float(row["entry_price"])
                atr = float(row["atr"])
                if not signal_id or not symbol or not all(map(math.isfinite, (entry, atr))) or min(entry, atr) <= 0:
                    raise ValueError("empty ID/symbol, nonfinite or nonpositive entry/ATR")
                key = (symbol, signal_id)
                if key in seen:
                    raise ValueError("duplicate signal ID within symbol")
                seen.add(key)
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f"invalid candidate row {row_num}: {exc}") from exc
            cohorts[(symbol, year)].append(atr / entry)
    if not cohorts:
        raise ValueError("empty candidate cohort is not a valid real-data test")
    actual_counts = {key: len(v) for key, v in cohorts.items()}
    if expected:
        for key, count in expected.items():
            if actual_counts.get(key, 0) != count:
                raise ValueError(
                    f"candidate cohort mismatch {key}: expected={count}, actual={actual_counts.get(key, 0)}"
                )
    report = {
        "status": "GATE_DIAGNOSTIC_ONLY",
        "is_realized_backtest": False,
        "live_modified": False,
        "config": CONFIG,
        "input_sha256": hashlib.sha256(rows).hexdigest(),
        "input_candidates": len(seen),
        "cohorts": [],
    }
    for (symbol, year), ratios in sorted(cohorts.items()):
        result = {"symbol": symbol, "year": year, "signals": len(ratios), "arms": {}}
        for arm_name, multipliers in ARMS.items():
            checks = [assess(x, multipliers) for x in ratios]
            reasons_any = Counter(flag for x in checks for flag in x["reasons"])
            reasons_primary = Counter(x["primary_reason"] for x in checks)
            accepted = sum(x["accepted"] for x in checks)
            rr_values = sorted(x["net_rr"] for x in checks)
            result["arms"][arm_name] = {
                "signals": len(checks),
                "accepted": accepted,
                "rejected": len(checks) - accepted,
                "acceptance_rate": round(accepted / len(checks), 6),
                "primary_reason_counts": dict(sorted(reasons_primary.items())),
                "independent_reason_counts": {
                    k: reasons_any.get(k, 0) for k in REASONS
                },
                "both_stop_and_target_caps": sum(
                    all(k in x["reasons"] for k in REASONS[:2]) for x in checks
                ),
                "median_unclipped_net_rr": round(rr_values[len(rr_values) // 2], 6),
            }
        report["cohorts"].append(result)
    return report


def parse_expected(values: list[str]) -> dict[tuple[str, int], int]:
    parsed = {}
    for x in values:
        try:
            ticker, year, number = x.rsplit(":", 2)
            key = (ticker.upper(), int(year))
            if not ticker or int(number) < 0 or key in parsed:
                raise ValueError("invalid or duplicate expectation")
            parsed[key] = int(number)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"bad --expect-cohort {x}; use SYMBOL:YEAR:COUNT") from exc
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("outputs/rr2_entry_audit/summary.json"))
    parser.add_argument("--expect-cohort", action="append", default=[])
    args = parser.parse_args()
    report = audit(args.candidates, parse_expected(args.expect_cohort))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "input_candidates": report["input_candidates"],
        "cohorts": [
            {"symbol": c["symbol"], "year": c["year"], "signals": c["signals"],
             "accepted": {name: v["accepted"] for name, v in c["arms"].items()}}
            for c in report["cohorts"]
        ],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
