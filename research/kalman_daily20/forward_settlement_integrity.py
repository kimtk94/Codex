#!/usr/bin/env python3
"""Read-only audit of Daily20 4-XNYS-session Bull/Bear settled outcomes.

No trading, price replacement, retroactive signal creation or source certification.
The earliest legitimate settlement is only after the FOURTH subsequent XNYS
session's close. Record immutable original realized entries/values even when a
vendor later revises its adjusted historical OHLCV; classify that revision HOLD.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from hashlib import sha256
import io
import json
import math
from pathlib import Path

import pandas as pd

from daily20 import load_bars, load_spec, market_file, write_json
from forward_shadow import (
    COST_BPS, HOLD_SESSIONS, check_events, nyse_dates, journal_bytes,
)
from bear_forward import validate_bear_events

VERSION = "daily20-4xnys-settlement-evidence-v1"
FAMILIES = ("BULL_LOGISTIC", "BEAR_LOGISTIC", "BEAR_RULE")
COLUMNS = (
    "signal_date", "symbol", "family", "candidate_at_signal_time",
    "entry_date", "exit_date", "state", "original_signal_hash",
    "original_settlement_hash", "recorded_at_utc", "cost_20bp_net_return",
    "price_revision_detected", "price_revision_issues",
)


def require(test, code):
    if not test:
        raise RuntimeError("SETTLEMENT_" + code)


def js_digest(data):
    return sha256(data).hexdigest()


def read_events(path):
    body = Path(path).read_bytes()
    return [json.loads(s) for s in body.splitlines() if s.strip()], js_digest(body)


def price_frame(market, symbol, cache):
    if symbol not in cache:
        cache[symbol] = load_bars(market_file(market, symbol))
    return cache[symbol]


def verify_settled_value(event, original, market, expected_dates, cache, calendar):
    """Arithmetic is checked against the original record AND current vendor.

    A changed vendor close is flagged; old frozen settlement values are never
    replaced. An input revision is not itself proof that a past fill was wrong.
    """
    expected = [pd.Timestamp(x.date()).normalize() for x in expected_dates]
    entry_date, exit_date = str(expected_dates[1].date()), str(expected_dates[4].date())
    require(event.get("entry_date") == entry_date and
            event.get("exit_date") == exit_date, "FOUR_SESSION_DATES_REWRITTEN")
    stamp = pd.Timestamp(event.get("recorded_at_utc"))
    require(stamp.tzinfo is not None and
            stamp >= calendar.session_close(expected_dates[4]) +
            pd.Timedelta(minutes=45), "SETTLEMENT_BEFORE_EXIT_CLOSE_BUFFER")
    require(event.get("signal_hash") == original["hash"] and
            event.get("candidate_at_signal_time") is original["candidate"] and
            event.get("model_positive_probability_frozen") ==
            original["probability"] and
            event.get("observation_only_no_execution") is True,
            "FROZEN_ORIGINAL_EVENT_LINK_CHANGED")
    for key in ("entry_open", "exit_close", "gross_return",
                "next_open_gap_return", "worst_four_session_low_vs_entry"):
        require(type(event.get(key)) in (int, float) and
                math.isfinite(event[key]), "OUTCOME_NUMERIC_INVALID:" + key)
    start, end = float(event["entry_open"]), float(event["exit_close"])
    require(start > 0 and end > 0, "OUTCOME_MARKS_INVALID")
    gross = end / start - 1
    require(math.isclose(event["gross_return"], gross,
                         rel_tol=0, abs_tol=1e-9),
            "GROSS_RETURN_ARITHMETIC_MISMATCH")
    nets = event.get("net_return_by_cost_bp")
    require(isinstance(nets, dict) and set(nets) ==
            {str(cost) for cost in COST_BPS},
            "COST_GRID_MISSING")
    for cost in COST_BPS:
        value = nets[str(cost)]
        require(type(value) in (int, float) and math.isfinite(value)
                and math.isclose(value, gross - cost / 10_000,
                                 rel_tol=0, abs_tol=1e-9),
                "ROUNDTRIP_COST_MISMATCH")
    frame = price_frame(market, original["symbol"], cache)
    require(set(expected).issubset(frame.index), "EXIT_WINDOW_MARKET_GAP")
    observed_open = float(frame.at[expected[1], "open"])
    observed_close = float(frame.at[expected[4], "close"])
    previous_close = float(frame.at[expected[0], "close"])
    worst_low = float(frame.loc[expected[1]:expected[4], "low"].min())
    require(all(math.isfinite(x) and x > 0 for x in (
        observed_open, observed_close, previous_close, worst_low)),
        "CURRENT_MARKET_WINDOW_INVALID")
    issues = []
    for key, calculated in (
        ("entry_open", observed_open),
        ("exit_close", observed_close),
        ("gross_return", observed_close / observed_open - 1),
        ("next_open_gap_return", observed_open / previous_close - 1),
        ("worst_four_session_low_vs_entry",
         worst_low / observed_open - 1),
    ):
        tolerance = 1e-7 if key in ("entry_open", "exit_close") else 1e-9
        if not math.isclose(event[key], calculated, rel_tol=0, abs_tol=tolerance):
            issues.append(key)
    return issues


def audit(spec, market, asof, bull_events, bear_events, *,
          report_bull=None, report_bear=None, recorded_source_sha=None):
    require(HOLD_SESSIONS == 4 and tuple(COST_BPS) == (20, 40, 80),
            "SCORING_RULES_CHANGED")
    core = set(spec["core"])
    require(len(core) == 20 and len(spec["context"]) == 6,
            "UNIVERSE_INCOMPLETE")
    bull, settled_bull = check_events(bull_events, core)
    bear, settled_bear = validate_bear_events(bear_events, core)
    for family, signals in (
        ("BULL_LOGISTIC", bull),
        ("BEAR_LOGISTIC", {k: v for k, v in bear.items() if k[2] == "BEAR_LOGISTIC"}),
        ("BEAR_RULE", {k: v for k, v in bear.items() if k[2] == "BEAR_RULE"}),
    ):
        counts = Counter(k[0] for k in signals)
        require(all(v == 20 for v in counts.values()),
                "PARTIAL_SESSION:" + family)
    require(set(k[0] for k in bull) == set(k[0] for k in bear),
            "BULL_BEAR_COHORT_DATE_MISMATCH")
    require(len(bear) == 2 * len(bull), "BEAR_COHORT_INCOMPLETE")
    for (date, symbol, family), event in bear.items():
        require(event.get("baseline_signal_hash") ==
                bull[(date, symbol)]["hash"],
                "BEAR_BULL_ORIGINAL_ANCHOR_MISMATCH")
    if report_bull is not None or report_bear is not None:
        require(isinstance(report_bull, dict) and
                isinstance(report_bear, dict) and
                report_bull.get("last_completed_session") == asof and
                report_bear.get("last_completed_session") == asof and
                report_bull.get("signal_events") == len(bull) and
                report_bear.get("signal_events") == len(bear) and
                report_bull.get("settled_events") == len(settled_bull) and
                report_bear.get("settled_events") == len(settled_bear) and
                report_bull.get("research_only") is True and
                report_bear.get("research_only") is True and
                report_bull.get("approved_live") is False and
                report_bear.get("approved_live") is False,
                "FORWARD_REPORT_VS_JOURNAL_MISMATCH")
    expected = {
        (event["signal_date"], event["symbol"], "BULL_LOGISTIC"): event
        for event in bull_events if event["kind"] == "SETTLED"
    }
    expected.update({
        (event["signal_date"], event["symbol"], event["family"]): event
        for event in bear_events if event["kind"] == "SETTLED"
    })
    require(len(expected) == len(settled_bull) + len(settled_bear),
            "SETTLED_INDEX_NOT_UNIQUE")
    import exchange_calendars as xc
    calendar = xc.get_calendar("XNYS")
    cache, rows = {}, []
    counts = Counter()
    for date, symbol in sorted(bull):
        for family in FAMILIES:
            identity = (date, symbol, family)
            original = (bull[(date, symbol)] if family == "BULL_LOGISTIC"
                        else bear[identity])
            _, window = nyse_dates(date, calendar=calendar)
            entry_date, exit_date = str(window[1].date()), str(window[4].date())
            settled = expected.get(identity)
            due = exit_date <= asof
            require(not (due and settled is None),
                    "MATURED_4TH_SESSION_UNSETTLED:" + ":".join(identity))
            require(not (not due and settled is not None),
                    "PREMATURE_4TH_SESSION_SETTLEMENT")
            require(date <= asof, "SIGNAL_FROM_FUTURE")
            issues = []
            if settled is not None:
                issues = verify_settled_value(settled, original, market, window,
                                               cache, calendar)
                state = ("SETTLED_VENDOR_HISTORY_REVISED_HOLD"
                         if issues else "SETTLED_ARITHMETIC_VERIFIED_RESEARCH_ONLY")
                counts["settled"] += 1
                counts["vendor_price_revisions"] += int(bool(issues))
            else:
                state = "PENDING_UNMATURED_4_XNYS_SESSIONS"
                counts["pending"] += 1
            rows.append({
                "signal_date": date, "symbol": symbol, "family": family,
                "candidate_at_signal_time": original["candidate"],
                "entry_date": entry_date, "exit_date": exit_date,
                "state": state, "original_signal_hash": original["hash"],
                "original_settlement_hash": settled["hash"] if settled else None,
                "recorded_at_utc": settled.get("recorded_at_utc") if settled else None,
                "cost_20bp_net_return": (
                    settled["net_return_by_cost_bp"]["20"] if settled else None),
                "price_revision_detected": bool(issues),
                "price_revision_issues": issues,
            })
    require(len(rows) == len(bull) + len(bear), "AUDIT_ROW_COUNT_INCOMPLETE")
    require(counts["settled"] == len(settled_bull) + len(settled_bear),
            "SETTLED_JOURNAL_COUNT_MISMATCH")
    status = ("SETTLED_VENDOR_REVISION_RESEARCH_HOLD"
              if counts["vendor_price_revisions"] else
              "SETTLEMENT_SCHEDULE_AND_ARITHMETIC_RESEARCH_HOLD")
    return {
        "version": VERSION, "session": asof, "status": status,
        "research_only": True, "production_writes": False,
        "live_execution": False, "strategy_promoted": False,
        "official_regular_close_certified": False,
        "source_finality_verified_assets": 0,
        "settlement_is_observation_not_executed_trade": True,
        "actual_forward_outcomes_approved_for_attribution": False,
        "round_trip_cost_grid_bps": list(COST_BPS),
        "holding_period_subsequent_xnys_sessions": 4,
        "first_future_session_entry": "next_session_open",
        "fourth_future_session_exit": "fourth_subsequent_close",
        "signal_count": len(rows),
        "bull_signals": len(bull), "bear_signals": len(bear),
        "pending_unmatured": counts["pending"],
        "settled_arithmetic_verified": counts["settled"] -
                                       counts["vendor_price_revisions"],
        "settled_vendor_price_revisions": counts["vendor_price_revisions"],
        "settled_events": counts["settled"],
        "candidate_settlements": sum(
            bool(row["candidate_at_signal_time"])
            for row in rows if row["original_settlement_hash"] is not None
        ),
        "first_unsettled_exit_date": min(
            (row["exit_date"] for row in rows
             if row["original_settlement_hash"] is None), default=None),
        "original_journals_unchanged": True,
        "scored_input_maturity_not_conflated_with_alpha": True,
        "source_digests": recorded_source_sha,
        "observations": rows,
    }


def csv_blob(rows):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            key: json.dumps(row[key]) if key == "price_revision_issues" else
            "" if row[key] is None else row[key]
            for key in COLUMNS
        })
    return buf.getvalue().encode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="research/kalman_daily20/universe.json")
    for name in ("market", "qc", "bull-journal", "bear-journal",
                 "bull-report", "bear-report", "out"):
        ap.add_argument("--" + name, required=True)
    args = ap.parse_args()
    qc = json.loads(Path(args.qc).read_text())
    require(qc.get("status") == "READY" and qc.get("required") == 26 and
            qc.get("ready") == 26 and
            isinstance(qc.get("expected_session"), str),
            "INCOMPLETE_26_ASOF_MARKET")
    bull, bull_sha = read_events(args.bull_journal)
    bear, bear_sha = read_events(args.bear_journal)
    br = json.loads(Path(args.bull_report).read_text())
    rr = json.loads(Path(args.bear_report).read_text())
    output = audit(load_spec(args.config), args.market, qc["expected_session"],
                   bull, bear, report_bull=br, report_bear=rr,
                   recorded_source_sha={
                       "bull_journal_sha256": bull_sha,
                       "bear_journal_sha256": bear_sha,
                       "qc_sha256": js_digest(Path(args.qc).read_bytes()),
                   })
    target = Path(args.out)
    target.mkdir(parents=True, exist_ok=True)
    table = csv_blob(output["observations"])
    (target / "settlement_queue.csv").write_bytes(table)
    output["settlement_queue_csv_sha256"] = js_digest(table)
    write_json(target / "report.json", output)
    print(json.dumps({"DAILY20_SETTLEMENT_INTEGRITY": {
        "session": output["session"], "signals": output["signal_count"],
        "settled": output["settled_events"], "pending": output["pending_unmatured"],
        "revisions": output["settled_vendor_price_revisions"],
        "first_unsettled_exit_date": output["first_unsettled_exit_date"],
        "status": output["status"], "source_certified": 0,
    }}))


if __name__ == "__main__":
    main()
