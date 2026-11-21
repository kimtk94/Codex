#!/usr/bin/env python3
"""Append-only, hash-linked, post-close Daily20 shadow prediction evidence.

Only admit signals before the following XNYS open. A realized outcome is added
in a separate event after the fourth subsequent XNYS close. Never convert
retrospective 2024-26 backtests into prospective predictions.

A hash chain is *tamper-evident*, NOT tamper-proof. The owner can replace a
Drive file; independent Drive revisions/Actions runs are audit anchors.
No live broker, no account balances, no investment advice.
"""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from zipfile import ZipFile

import numpy as np
import pandas as pd

from daily20 import load_bars, load_spec, market_file, write_json

VERSION = "daily20-forward-shadow-v1"
SEED_MAX_SESSION = "2026-11-20"
ROOT_HASH = "0" * 64
HOLD_SESSIONS = 4
COST_BPS = (20, 40, 80)
JOURNAL = "research/forward_shadow/journal.jsonl"
REPORT = "research/forward_shadow/report.json"
VALID_KINDS = {"SIGNAL", "SETTLED"}
OUTPUT_FILES = ("journal.jsonl", "report.json", "snapshots.csv", "outcomes.csv")


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def event_hash(event):
    return sha256_bytes(canonical_json({k: v for k, v in event.items()
                                       if k != "hash"}).encode())


def chain_append(journal, payload):
    event = {
        "seq": len(journal) + 1,
        "prev_hash": journal[-1]["hash"] if journal else ROOT_HASH,
        **payload,
    }
    if event["kind"] not in VALID_KINDS:
        raise RuntimeError("FORBIDDEN_FORWARD_EVENT_KIND")
    event["hash"] = event_hash(event)
    journal.append(event)
    return event


def check_events(journal, core):
    if not isinstance(journal, list):
        raise RuntimeError("JOURNAL_NOT_A_LIST")
    parent = ROOT_HASH
    signal_index, settled_index = {}, set()
    last_signal_date = ""
    for number, event in enumerate(journal, 1):
        if not isinstance(event, dict) or event.get("seq") != number:
            raise RuntimeError("JOURNAL_SEQUENCE_BROKEN")
        if event.get("prev_hash") != parent or event.get("hash") != event_hash(event):
            raise RuntimeError("JOURNAL_HASH_CHAIN_BROKEN")
        if event.get("kind") not in VALID_KINDS or event.get("symbol") not in core:
            raise RuntimeError("JOURNAL_INVALID_EVENT_IDENTITY")
        key = (event.get("signal_date"), event["symbol"])
        date = str(event.get("signal_date"))
        if event["kind"] == "SIGNAL":
            # An already-frozen later signal can precede a settlement of an
            # older signal in the append-only event stream.
            if date < last_signal_date:
                raise RuntimeError("JOURNAL_SIGNAL_DATE_REGRESSED")
            last_signal_date = date
            if key in signal_index:
                raise RuntimeError("JOURNAL_DUPLICATE_FROZEN_SIGNAL")
            if not 0 <= event.get("probability", -1) <= 1:
                raise RuntimeError("JOURNAL_INVALID_PROBABILITY")
            if type(event.get("candidate")) is not bool:
                raise RuntimeError("JOURNAL_INVALID_CANDIDATE")
            if event.get("research_only") is not True:
                raise RuntimeError("JOURNAL_LIVE_SIGNAL_FORBIDDEN")
            signal_index[key] = event
        else:
            if key not in signal_index or key in settled_index:
                raise RuntimeError("JOURNAL_INVALID_SETTLEMENT_LINK")
            s = signal_index[key]
            if event.get("signal_hash") != s["hash"]:
                raise RuntimeError("JOURNAL_SETTLEMENT_SIGNAL_HASH_MISMATCH")
            if not (event["signal_date"] < event["entry_date"] < event["exit_date"]):
                raise RuntimeError("JOURNAL_INVALID_SETTLEMENT_DATES")
            if event.get("research_only") is not True:
                raise RuntimeError("JOURNAL_LIVE_SETTLEMENT_FORBIDDEN")
            settled_index.add(key)
        parent = event["hash"]
    return signal_index, settled_index


def validate_prior_results_archive(blob, core):
    """Verify exact signed-manifest hashes of *all* archived output members."""
    if not blob:
        raise RuntimeError("MISSING_PREVIOUS_DRIVE_RESULTS")
    with ZipFile(BytesIO(blob)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(
            name.startswith("/") or ".." in Path(name).parts or "\\" in name
            for name in names
        ):
            raise RuntimeError("UNSAFE_PRIOR_RESEARCH_ARCHIVE")
        if "drive_manifest.json" not in names:
            raise RuntimeError("RESULTS_MANIFEST_MISSING")
        manifest = json.loads(archive.read("drive_manifest.json"))
        if (manifest.get("format") != "kalman-daily20-drive-v1"
                or manifest.get("research_only") is not True
                or manifest.get("production_writes") is not False
                or manifest.get("oos_score_count") != 20):
            raise RuntimeError("INVALID_PRIOR_RESEARCH_MANIFEST")
        hashes = manifest.get("payload_hashes_sha256", {})
        if set(hashes) != set(names) - {"drive_manifest.json"}:
            raise RuntimeError("INCOMPLETE_PRIOR_RESEARCH_HASHES")
        if not all(sha256_bytes(archive.read(name)) == digest
                   for name, digest in hashes.items()):
            raise RuntimeError("PRIOR_RESEARCH_HASH_MISMATCH")
        needed = {"qc.json", "research/summary.json",
                  "research/latest_research_scores.csv"}
        if not needed.issubset(names):
            raise RuntimeError("MISSING_PRIOR_RESULTS_EVIDENCE")
        if JOURNAL in names:
            if REPORT not in names:
                raise RuntimeError("PRIOR_FORWARD_REPORT_MISSING")
            payload = archive.read(JOURNAL).decode("utf-8")
            journal = [json.loads(line) for line in payload.splitlines() if line.strip()]
            old_report = json.loads(archive.read(REPORT))
            if old_report.get("version") != VERSION or old_report.get("research_only") is not True:
                raise RuntimeError("PRIOR_FORWARD_VERSION_MISMATCH")
            if old_report.get("journal_sha256") != sha256_bytes(archive.read(JOURNAL)):
                raise RuntimeError("PRIOR_FORWARD_JOURNAL_HASH_MISMATCH")
        else:
            if REPORT in names or manifest.get("data_expected_last_closed_xnys", "") > SEED_MAX_SESSION:
                raise RuntimeError("MISSING_FORWARD_HISTORY_AFTER_INITIALIZATION")
            journal = []
    check_events(journal, core)
    return manifest, journal


def nyse_dates(signal_date, *, calendar=None):
    import exchange_calendars as xc
    calendar = calendar or xc.get_calendar("XNYS")
    date = pd.Timestamp(signal_date)
    sessions = calendar.sessions_in_range(
        (date - pd.Timedelta(days=1)).date(),
        (date + pd.Timedelta(days=28)).date(),
    )
    day = pd.Timestamp(date, tz="UTC") if date.tzinfo is None else date.tz_convert("UTC")
    if day not in sessions:
        raise RuntimeError("SIGNAL_NOT_XNYS_SESSION")
    idx = sessions.get_loc(day)
    if idx + HOLD_SESSIONS >= len(sessions):
        raise RuntimeError("MISSING_FUTURE_XNYS_CALENDAR")
    return calendar, sessions[idx:idx + HOLD_SESSIONS + 1]


def check_signal_admission(signal_date, now):
    calendar, future = nyse_dates(signal_date)
    stamp = pd.Timestamp(now).tz_convert("UTC")
    latest_close = calendar.session_close(future[0])
    next_open = calendar.session_open(future[1])
    if stamp < latest_close + pd.Timedelta(minutes=45):
        raise RuntimeError("SIGNAL_SESSION_NOT_FOLLOWED_BY_45M_BUFFER")
    return bool(stamp < next_open), str(next_open)


def read_score_rows(path, spec, expected_session):
    scores = pd.read_csv(path)
    required = {"symbol", "signal_after_close", "logistic_prob_positive_net",
                "research_candidate", "not_order", "shadow_only"}
    if not required.issubset(scores.columns) or len(scores) != 20:
        raise RuntimeError("INCOMPLETE_FUTURE_SIGNAL_SCORES")
    if set(scores["symbol"]) != set(spec["core"]) or scores["symbol"].duplicated().any():
        raise RuntimeError("INVALID_FUTURE_SCORE_UNIVERSE")
    if set(scores["signal_after_close"].astype(str)) != {expected_session}:
        raise RuntimeError("FUTURE_SCORE_SESSION_MISMATCH")
    rows = {}
    for item in scores.to_dict("records"):
        symbol = item["symbol"]
        prob = float(item["logistic_prob_positive_net"])
        if not np.isfinite(prob) or not 0 <= prob <= 1:
            raise RuntimeError("INVALID_FUTURE_PROBABILITY")
        def read_bool(value):
            if isinstance(value, (bool, np.bool_)):
                return bool(value)
            if str(value).strip().lower() in ("true", "false"):
                return str(value).strip().lower() == "true"
            raise RuntimeError("INVALID_BOOLEAN_FUTURE_SCORE")
        if read_bool(item["not_order"]) is not True:
            raise RuntimeError("LIVE_SIGNAL_SNAPSHOT_FORBIDDEN")
        shadow = read_bool(item["shadow_only"])
        if shadow != (symbol in spec["high_risk_shadow_only"]):
            raise RuntimeError("SHADOW_RISK_CLASSIFICATION_MISMATCH")
        rows[symbol] = {
            "probability": round(prob, 12),
            "candidate": read_bool(item["research_candidate"]),
            "shadow_only": shadow,
        }
    return rows


def new_observation(signal, market, latest_session, recorded_at):
    """Only fully closed fourth subsequent session permits a settlement."""
    _, future = nyse_dates(signal["signal_date"])
    entry_date = str(future[1].date())
    exit_date = str(future[4].date())
    if exit_date > latest_session:
        return None
    frame = load_bars(market_file(market, signal["symbol"]))
    required_dates = [pd.Timestamp(day.date()).normalize() for day in future]
    if not frame.index.isin(required_dates).any() or not set(required_dates).issubset(frame.index):
        raise RuntimeError("FUTURE_OBSERVATION_PRICE_GAP:" + signal["symbol"])
    entry = float(frame.at[required_dates[1], "open"])
    exit_close = float(frame.at[required_dates[4], "close"])
    prev_close = float(frame.at[required_dates[0], "close"])
    interval = frame.loc[required_dates[1]:required_dates[4]]
    intrahold_min_low = float(pd.to_numeric(interval["low"]).min())
    if not all(np.isfinite(x) and x > 0
               for x in (entry, exit_close, prev_close, intrahold_min_low)):
        raise RuntimeError("INVALID_FUTURE_OBSERVATION_PRICE")
    gross = exit_close / entry - 1
    net = {str(bp): round(gross - bp / 10_000, 12) for bp in COST_BPS}
    return {
        "kind": "SETTLED", "research_only": True,
        "signal_date": signal["signal_date"], "symbol": signal["symbol"],
        "signal_hash": signal["hash"], "entry_date": entry_date,
        "exit_date": exit_date, "recorded_at_utc": recorded_at,
        "entry_open": round(entry, 9), "exit_close": round(exit_close, 9),
        "gross_return": round(gross, 12),
        "net_return_by_cost_bp": net,
        "next_open_gap_return": round(entry / prev_close - 1, 12),
        "worst_four_session_low_vs_entry": round(intrahold_min_low / entry - 1, 12),
        "observation_only_no_execution": True,
        "candidate_at_signal_time": signal["candidate"],
        "model_positive_probability_frozen": signal["probability"],
    }


def journal_bytes(journal):
    return ("".join(canonical_json(item) + "\n" for item in journal)).encode("utf-8")


def run(spec, prior_blob, market, scores_path, qc_path, out, *, now=None,
        source_sha=None, run_id=None):
    now = (datetime.now(timezone.utc) if now is None else pd.Timestamp(now).to_pydatetime())
    stamp = pd.Timestamp(now)
    if stamp.tzinfo is None:
        raise RuntimeError("CURRENT_TIME_MUST_BE_TIMEZONE_AWARE")
    stamp = stamp.tz_convert("UTC")
    recorded_at = stamp.isoformat()
    qc = json.loads(Path(qc_path).read_text())
    latest = str(qc.get("expected_session"))
    if qc.get("status") != "READY" or qc.get("ready") != 26:
        raise RuntimeError("FORWARD_ONLY_REQUIRES_QC_26")
    # The input session itself must be the most recent *fully closed* NYSE
    # session, not a retrospective run with a hand-chosen end date.
    from daily20 import last_completed_nyse
    if latest != str(last_completed_nyse(stamp)):
        raise RuntimeError("BACKDATED_FORWARD_SESSION_BLOCKED")
    prior_manifest, journal = validate_prior_results_archive(prior_blob, spec["core"])
    old_session = str(prior_manifest.get("data_expected_last_closed_xnys"))
    if old_session > latest:
        raise RuntimeError("PREVIOUS_SESSION_NEWER_THAN_CURRENT")
    signals, settled = check_events(journal, set(spec["core"]))
    new_score = read_score_rows(scores_path, spec, latest)
    recorded_today = [k for k in signals if k[0] == latest]
    admitted, next_open = check_signal_admission(latest, stamp)
    if recorded_today:
        if len(recorded_today) != 20:
            raise RuntimeError("PARTIAL_FROZEN_SESSION_CANNOT_BE_REPAIRED")
        for symbol in spec["core"]:
            frozen = signals[(latest, symbol)]
            values = new_score[symbol]
            if (abs(frozen["probability"] - values["probability"]) > 1e-9
                    or frozen["candidate"] != values["candidate"]
                    or frozen["shadow_only"] != values["shadow_only"]):
                # Historical scores are not silently revised on a CI rerun.
                # This should be resolved as an explicit model-version fork.
                raise RuntimeError("FROZEN_FORWARD_SIGNAL_REVISED:" + symbol)
    elif admitted:
        for symbol in spec["core"]:
            chain_append(journal, {
                "kind": "SIGNAL", "research_only": True,
                "signal_date": latest, "symbol": symbol,
                "recorded_at_utc": recorded_at,
                "source_actions_run_id": str(run_id or os.environ.get("GITHUB_RUN_ID", "local")),
                "source_sha": str(source_sha or os.environ.get("GITHUB_SHA", "local")),
                "model_version": spec["version"],
                "horizon_us_sessions": HOLD_SESSIONS,
                **new_score[symbol],
            })
    elif not journal:
        raise RuntimeError("NO_SEED_BEFORE_NEXT_OPEN_FAIL_CLOSED")
    current_signals, current_settled = check_events(journal, set(spec["core"]))
    newly_settled = 0
    # Never reorder journal history: settlements appended in signal-date order,
    # while new signals, if any, have the latest date.
    outstanding = [(k, v) for k, v in current_signals.items() if k not in current_settled]
    for key, signal in outstanding:
        outcome = new_observation(signal, market, latest, recorded_at)
        if outcome is None:
            continue
        chain_append(journal, outcome)
        newly_settled += 1
    signals, settled = check_events(journal, set(spec["core"]))
    for item in journal:
        if item["kind"] == "SIGNAL":
            # A stored signal must have been made before the following open;
            # prevents retrospective "prospective" backfills by configuration.
            accepted, _ = check_signal_admission(
                item["signal_date"], pd.Timestamp(item["recorded_at_utc"]))
            if not accepted:
                raise RuntimeError("JOURNAL_HAS_BACKDATED_SIGNAL")
        else:
            import exchange_calendars as xc
            cal = xc.get_calendar("XNYS")
            exit_s = pd.Timestamp(item["exit_date"], tz="UTC")
            if pd.Timestamp(item["recorded_at_utc"]) < cal.session_close(exit_s):
                raise RuntimeError("JOURNAL_HAS_PREMATURE_SETTLEMENT")
    output = Path(out)
    output.mkdir(parents=True, exist_ok=True)
    snapshots = pd.DataFrame(
        [e for e in journal if e["kind"] == "SIGNAL"]
    )
    outcomes = pd.DataFrame(
        [e for e in journal if e["kind"] == "SETTLED"]
    )
    snapshots.to_csv(output / "snapshots.csv", index=False)
    if outcomes.empty:
        outcomes = pd.DataFrame(columns=[
            "seq", "signal_date", "symbol", "entry_date", "exit_date",
            "gross_return", "candidate_at_signal_time",
        ])
    outcomes.to_csv(output / "outcomes.csv", index=False)
    body = journal_bytes(journal)
    (output / "journal.jsonl").write_bytes(body)
    pending = len(signals) - len(settled)
    admitted_sessions = sorted({date for date, _ in signals})
    candidate_outcomes = [
        e for e in journal if e["kind"] == "SETTLED" and e["candidate_at_signal_time"]
    ]
    report = {
        "version": VERSION, "status": "RESEARCH_ONLY",
        "research_only": True, "live_execution": False, "approved_live": False,
        "last_completed_session": latest, "prior_drive_session": old_session,
        "previous_run_id": prior_manifest.get("source_actions_run_id"),
        "source_run_id": str(run_id or os.environ.get("GITHUB_RUN_ID", "local")),
        "created_at_utc": recorded_at,
        "next_session_open_utc": next_open, "signal_admission_open": admitted,
        "new_signal_events": 20 if admitted and not recorded_today else 0,
        "newly_settled_events": newly_settled,
        "signal_events": len(signals), "settled_events": len(settled),
        "pending_events": pending,
        "first_admitted_session": admitted_sessions[0],
        "latest_admitted_session": admitted_sessions[-1],
        "admitted_sessions": len(admitted_sessions),
        "matured_candidate_observations": len(candidate_outcomes),
        "candidate_average_net_return_20bp": (
            float(np.mean([e["net_return_by_cost_bp"]["20"] for e in candidate_outcomes]))
            if candidate_outcomes else None
        ),
        "candidate_win_rate_20bp": (
            float(np.mean([e["net_return_by_cost_bp"]["20"] > 0 for e in candidate_outcomes]))
            if candidate_outcomes else None
        ),
        "historical_oos_2024_26_promoted": False,
        "retrospective_backfill": False,
        "only_observation_not_portfolio_equity": True,
        "journal_hash_tip": journal[-1]["hash"],
        "journal_sha256": sha256_bytes(body),
        "warnings": [
            "Prospective signal evidence only after a verified complete NYSE close",
            "Existing annual logistic fitted model is frozen by run/model version metadata",
            "No retroactive signal admission; a late run after next open cannot backfill",
            "Outcome tracked after fourth subsequent completed NYSE close only",
            "No real orders; return uses adjusted Yahoo next-open/fourth-close candles",
            "All 20 daily scores are tracked; rejected candidates are observations, not trades",
            "Hash chain is tamper-evident, but Drive file overwrite and historical source revision remain possible",
            "2024–2026 retrospective OOS results do not count as forward validation",
        ],
    }
    write_json(output / "report.json", report)
    print(json.dumps({"DAILY20_FORWARD_SHADOW": {
        "status": report["status"], "signals": report["signal_events"],
        "new_signals": report["new_signal_events"],
        "settled": report["settled_events"], "pending": pending,
        "admitted_session": report["latest_admitted_session"],
        "journal_tip": report["journal_hash_tip"][:16],
    }}))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="research/kalman_daily20/universe.json")
    p.add_argument("--prior-zip")
    p.add_argument("--market")
    p.add_argument("--scores")
    p.add_argument("--qc")
    p.add_argument("--out", required=True)
    p.add_argument("--pr-contract", action="store_true")
    args = p.parse_args()
    if args.pr_contract:
        write_json(Path(args.out) / "pr_contract.json", {
            "status": "PR_ONLY_NO_FORWARD_EVIDENCE", "research_only": True,
            "why": "PR replay is not a verified prior-close prospective signal"
        })
        return
    required = (args.prior_zip, args.market, args.scores, args.qc)
    if not all(required):
        raise RuntimeError("FORWARD_RECORD_REQUIRES_PRIOR_VERIFIED_DRIVE_ZIP")
    run(load_spec(args.config), Path(args.prior_zip).read_bytes(), args.market,
        args.scores, args.qc, args.out)


if __name__ == "__main__":
    main()
