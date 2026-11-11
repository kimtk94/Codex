#!/usr/bin/env python3
"""PIT-validated COIN V_unweighted signal-ledger replay; NO LIVE ORDER PATH.

The candidate ledger is mandatory. Aggregated archive results must never be
used to guess signal dates, and all outputs contain *only* aggregates.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

from coin_structure import ARMS, HORIZONS, geometry, simulate, metrics, build_sessions

FIELDS = ("signal_id", "signal_date", "entry_date", "symbol", "model",
          "available_after", "source_run_id")
EXPECTED = {2025: 80, 2026: 46}
FEED = "ALPACA_SIP_15MIN_ADJUSTMENT_ALL"


def load_ledger(path):
    data = path.read_bytes()
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not set(FIELDS).issubset(reader.fieldnames):
            raise ValueError("MISSING_PIT_LEDGER_FIELDS")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("DUPLICATE_LEDGER_HEADERS")
        records = list(reader)
    if not records:
        raise ValueError("EMPTY_PIT_LEDGER")
    ids = set()
    entries = set()
    for r in records:
        if any(not r[x].strip() for x in FIELDS):
            raise ValueError("EMPTY_PIT_FIELD")
        if r["symbol"] != "COIN" or r["model"] != "V_unweighted":
            raise ValueError("WRONG_SYMBOL_OR_MODEL")
        if r["available_after"] != "RTH_CLOSE":
            raise ValueError("SIGNAL_AVAILABILITY_UNVERIFIED")
        try:
            date.fromisoformat(r["signal_date"])
            date.fromisoformat(r["entry_date"])
        except ValueError:
            raise ValueError("INVALID_DATE") from None
        if r["signal_date"] >= r["entry_date"]:
            raise ValueError("SIGNAL_AFTER_ENTRY_LEAKAGE")
        if r["signal_id"] in ids or r["entry_date"] in entries:
            raise ValueError("DUPLICATE_SIGNAL_OR_ENTRY")
        ids.add(r["signal_id"])
        entries.add(r["entry_date"])
    return records, hashlib.sha256(data).hexdigest()


def validate_entries(rows, sessions, *, expected=EXPECTED):
    by_date = {s["date"]: i for i, s in enumerate(sessions)}
    counts = Counter()
    candidates = []
    for r in rows:
        signal_idx = by_date.get(r["signal_date"])
        entry_idx = by_date.get(r["entry_date"])
        if signal_idx is None or entry_idx is None:
            raise ValueError("PIT_DATE_NOT_IN_COMPLETE_SIP")
        if entry_idx != signal_idx + 1:
            raise ValueError("NOT_IMMEDIATELY_NEXT_NYSE_SESSION")
        if signal_idx < 20:
            raise ValueError("INSUFFICIENT_COMPLETED_LOOKBACK")
        year = int(r["entry_date"][:4])
        if year not in expected:
            raise ValueError("UNEXPECTED_YEAR")
        counts[year] += 1
        candidates.append((entry_idx, r))
    if dict(counts) != dict(expected):
        raise ValueError("COHORT_CARDINALITY_MISMATCH: " + str(dict(counts)))
    for year in expected:
        year_runs = {r["source_run_id"] for _, r in candidates
                     if int(r["entry_date"][:4]) == year}
        if len(year_runs) != 1:
            raise ValueError("MULTIPLE_UNVERIFIED_SOURCE_RUNS_IN_YEAR")
    return sorted(candidates)


def _atr14_prior(sessions, i):
    t = []
    for j in range(i - 14, i):
        x, prior = sessions[j], sessions[j-1]["close"]
        t.append(max(x["high"]-x["low"], abs(x["high"]-prior), abs(x["low"]-prior)))
    return sum(t) / 14


def replay(sessions, source_quality, ledger, ledger_sha, *, expected=EXPECTED, source_sha=None):
    if source_quality["incomplete_sessions"] != 0:
        raise ValueError("INCOMPLETE_SIP_SOURCE")
    entries = validate_entries(ledger, sessions, expected=expected)
    baselines = {}
    rows = []
    for year in sorted(expected):
        cohort = [i for i, r in entries if int(r["entry_date"][:4]) == year]
        baseline_pass = 0
        atr_ratios = []
        for i in cohort:
            entry = sessions[i]["bars"][1]["o"]
            atrfrac = _atr14_prior(sessions, i) / entry
            atr_ratios.append(atrfrac)
            stop = atrfrac * 1.25
            target = atrfrac * 3.0
            if stop <= .03 and target <= .08 and (
                target-.003)/(stop+.003) >= 2:
                baseline_pass += 1
        atr_ratios.sort()
        baselines[year] = {
            "signals": len(cohort),
            "original_atr125_stop300_gate_pass": baseline_pass,
            "median_atr14_over_0945_entry": round(atr_ratios[len(atr_ratios)//2], 7),
            "parity_with_original_zero_pass": baseline_pass == 0
        }
        # Fail closed: archival COIN 2025/2026 original RR2 admits zero.
        if year in EXPECTED and baseline_pass:
            raise ValueError("ORIGINAL_BASELINE_PARITY_DRIFT")
        for arm in ARMS:
            feasible = []
            rejection = Counter()
            for i in cohort:
                entry = sessions[i]["bars"][1]["o"]
                g = geometry(entry,
                             sessions[i]["bars"][0]["l"],
                             sessions[i-1]["low"],
                             max(s["high"] for s in sessions[i-20:i]),
                             arm)
                if g["pass"]:
                    feasible.append((i, g))
                else:
                    rejection[g["reason"]] += 1
            if len(feasible)+sum(rejection.values()) != len(cohort):
                raise ValueError("GEOMETRY_COHORT_NOT_CONSERVED")
            for hold in HORIZONS:
                used = []
                blocked = tail = 0
                last_exit = -1
                for i, g in feasible:
                    if i + hold > len(sessions):
                        tail += 1
                        continue
                    if i <= last_exit:
                        blocked += 1
                        continue
                    x = simulate(sessions, i, hold,
                                 g["stop_pct"], g["target_pct"])
                    used.append(x)
                    last_exit = x["exit_index"]
                rows.append({
                    "year": year, "arm": arm, "hold_sessions": hold,
                    "original_signals": len(cohort),
                    "structural_pass": len(feasible),
                    "first_rejection_counts": dict(rejection),
                    "overlap_blocked": blocked,
                    "right_censored": tail,
                    **metrics(used, sessions),
                })
    return {
        "schema": "coin-rr2-v-unweighted-pit-signal-replay-v1",
        "status": "MATCHED_LEDGER_RESEARCH_ONLY_NOT_UNSEEN_OOS",
        "live": "HOLD",
        "no_broker_or_live_change": True,
        "signals_verified": dict(Counter(int(r["entry_date"][:4]) for _, r in entries)),
        "ledger_sha256": ledger_sha,
        "sip_source_sha256": source_sha,
        "year_source_run_id_sha256": {
            str(year): hashlib.sha256(next(
                r["source_run_id"] for _, r in entries
                if int(r["entry_date"][:4]) == year).encode()).hexdigest()
            for year in sorted(expected)
        },
        "market_source": FEED,
        "signal_rule": "RTH_CLOSE_TO_NEXT_NYSE_SESSION_0945",
        "baseline_parity": baselines,
        "not_fresh_oos": True,
        "do_not_publish_signal_dates_or_bars": True,
        "quality": source_quality,
        "results": rows,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ledger", required=True, type=Path,
                   help="Private validated PIT signal CSV; NOT an aggregate summary")
    p.add_argument("--bars", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--start", default="2024-01-01")
    p.add_argument("--end", default="2026-10-30")
    a = p.parse_args()
    ledger, h = load_ledger(a.ledger)
    barbytes = a.bars.read_bytes()
    bars = json.loads(barbytes)
    sessions, q = build_sessions(bars, start=a.start, end=a.end)
    d = replay(sessions, q, ledger, h,
               source_sha=hashlib.sha256(barbytes).hexdigest())
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": d["status"],
                      "verified": d["signals_verified"],
                      "rows": len(d["results"]), "live": "HOLD"}))


if __name__ == "__main__":
    main()
