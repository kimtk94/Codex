#!/usr/bin/env python3
"""Prospectively seal two independent Bear-Regime shadow strategies (NO LIVE).

A dedicated journal is separated from the existing Bull Logistic shadow ledger.
Every 20-name pair (BEAR_LOGISTIC + BEAR_RULE) is frozen after the US close,
before next-session open. 4-session delayed observations are appended, never
retroactively labelled as forward. Only newly captured sessions count.
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

from daily20 import load_spec, write_json
from forward_shadow import (
    COST_BPS, HOLD_SESSIONS, ROOT_HASH, SEED_MAX_SESSION, canonical_json,
    check_events as check_bull_events, check_signal_admission, event_hash,
    journal_bytes, new_observation, nyse_dates, sha256_bytes,
    validate_prior_results_archive,
)
from regime_challenger import (
    BEAR_VIX_MAX, BEAR_RSI_HIGH, BEAR_RSI_LOW, MIN_BEAR_TRAIN,
    ML_THRESHOLD, bear_gate, fit_bear_year, rule_gate,
)
from train import COLUMNS, context_frame, feature_frame

VERSION = "daily20-bear-forward-v1"
FAMILIES = ("BEAR_LOGISTIC", "BEAR_RULE")
JOURNAL = "research/bear_forward/journal.jsonl"
REPORT = "research/bear_forward/report.json"
FILES = ("journal.jsonl", "report.json", "snapshots.csv",
         "outcomes.csv", "latest_candidates.csv")
GENESIS_DATE = "2026-11-20"


def read_prior_bear(blob, core):
    """Re-use fully authenticated prior result ZIP verification, then bear seal."""
    manifest, bull = validate_prior_results_archive(blob, core)
    with ZipFile(BytesIO(blob)) as zf:
        names = set(zf.namelist())
        if JOURNAL not in names:
            if REPORT in names:
                raise RuntimeError("BEAR_PRIOR_REPORT_WITHOUT_JOURNAL")
            if str(manifest.get("data_expected_last_closed_xnys")) > GENESIS_DATE:
                raise RuntimeError("BEAR_JOURNAL_BOOTSTRAP_DATE_PASSED")
            return manifest, bull, []
        if not all("research/bear_forward/" + name in names for name in FILES):
            raise RuntimeError("BEAR_PRIOR_ARCHIVE_INCOMPLETE")
        content = zf.read(JOURNAL)
        previous = json.loads(zf.read(REPORT))
        if (previous.get("version") != VERSION
                or previous.get("research_only") is not True
                or previous.get("live_execution") is not False
                or previous.get("approved_live") is not False
                or previous.get("journal_sha256") != sha256_bytes(content)):
            raise RuntimeError("BEAR_PRIOR_REPORT_INVALID")
        journal = [json.loads(x) for x in content.decode().splitlines() if x.strip()]
        signals, settled = validate_bear_events(journal, core)
        if (len(signals) != previous.get("signal_events")
                or len(settled) != previous.get("settled_events")
                or (journal[-1]["hash"] if journal else ROOT_HASH) != previous.get("journal_hash_tip")):
            raise RuntimeError("BEAR_PRIOR_COUNTER_MISMATCH")
        return manifest, bull, journal


def add_event(journal, payload):
    event = {
        "seq": len(journal) + 1,
        "prev_hash": journal[-1]["hash"] if journal else ROOT_HASH,
        **payload,
    }
    if event["kind"] not in ("SIGNAL", "SETTLED") or event["family"] not in FAMILIES:
        raise RuntimeError("INVALID_BEAR_EVENT_KIND")
    event["hash"] = event_hash(event)
    journal.append(event)
    return event


def validate_bear_events(journal, core):
    """Reject modified chain, duplicates, invalid timing and disconnected events."""
    previous_hash = ROOT_HASH
    last_signal_date = ""
    signals, settlements = {}, set()
    for number, event in enumerate(journal, 1):
        if (event.get("seq") != number or event.get("prev_hash") != previous_hash
                or event.get("hash") != event_hash(event)
                or event.get("kind") not in ("SIGNAL", "SETTLED")
                or event.get("family") not in FAMILIES
                or event.get("symbol") not in core
                or event.get("research_only") is not True):
            raise RuntimeError("BEAR_JOURNAL_HASH_OR_IDENTITY_BROKEN")
        key = (event.get("signal_date"), event["symbol"], event["family"])
        if event["kind"] == "SIGNAL":
            if key in signals:
                raise RuntimeError("BEAR_DUPLICATE_FROZEN_SIGNAL")
            if str(event.get("signal_date", "")) < last_signal_date:
                raise RuntimeError("BEAR_SIGNAL_DATE_REGRESSION")
            last_signal_date = event["signal_date"]
            if type(event.get("candidate")) is not bool or type(event.get("eligible")) is not bool:
                raise RuntimeError("BEAR_INVALID_BOOLEAN")
            if event["candidate"] and not event["eligible"]:
                raise RuntimeError("BEAR_CANDIDATE_WITHOUT_GATE")
            prob = event.get("probability")
            if event["family"] == "BEAR_LOGISTIC":
                if prob is not None and (
                    isinstance(prob, bool) or not isinstance(prob, (float, int))
                    or not 0 <= prob <= 1):
                    raise RuntimeError("BEAR_INVALID_PROBABILITY")
                if event["candidate"] and prob is None:
                    raise RuntimeError("BEAR_CANDIDATE_NO_MODEL")
            elif prob is not None:
                raise RuntimeError("BEAR_RULE_MUST_HAVE_NULL_PROBABILITY")
            if event.get("model_version") != VERSION or event.get("shadow_only") not in (True, False):
                raise RuntimeError("BEAR_INVALID_SOURCE_VERSION")
            if not isinstance(event.get("feature_sha256"), str) or len(event["feature_sha256"]) != 64:
                raise RuntimeError("BEAR_FEATURE_HASH_MISSING")
            if not isinstance(event.get("baseline_signal_hash"), str) or len(event["baseline_signal_hash"]) != 64:
                raise RuntimeError("BEAR_BASELINE_SIGNAL_NOT_LINKED")
            signals[key] = event
        else:
            if key not in signals or key in settlements:
                raise RuntimeError("BEAR_UNLINKED_OR_DUPLICATE_SETTLEMENT")
            if event.get("signal_hash") != signals[key]["hash"]:
                raise RuntimeError("BEAR_SETTLEMENT_SIGNAL_HASH_MISMATCH")
            if not (event["signal_date"] < event["entry_date"] < event["exit_date"]):
                raise RuntimeError("BEAR_SETTLEMENT_DATE_SEQUENCE")
            if event.get("candidate_at_signal_time") != signals[key]["candidate"]:
                raise RuntimeError("BEAR_SETTLEMENT_CANDIDATE_MODIFIED")
            if event.get("observation_only_no_execution") is not True:
                raise RuntimeError("BEAR_FAKE_EXECUTION")
            settlements.add(key)
        previous_hash = event["hash"]
    return signals, settlements


def _safe_float(value):
    if value is None or pd.isna(value) or not np.isfinite(float(value)):
        return None
    return round(float(value), 12)


def score_bear_asof(spec, market, features, session):
    """Score only the last completed bar using fixed prior-year-purged training.

    Existing bear retrospective CSVs are explicitly NOT inputs to this function.
    """
    context = context_frame(market)
    rows = {}
    for symbol in spec["core"]:
        frame = feature_frame(symbol, market, features, context,
                              float(spec["round_trip_cost_bps"]))
        if frame.empty or str(frame.index[-1].date()) != session:
            raise RuntimeError("BEAR_ASOF_FEATURE_SESSION_MISMATCH:" + symbol)
        last = frame.iloc[[-1]]
        reg = bool(bear_gate(last).iloc[0])
        rule = bool(rule_gate(frame).iloc[-1])
        estimator, _, fold = fit_bear_year(frame, int(session[:4]))
        probability = None
        if estimator is not None:
            predicted = float(estimator.predict_proba(last[COLUMNS])[:, 1][0])
            if not np.isfinite(predicted) or not 0 <= predicted <= 1:
                raise RuntimeError("NONFINITE_BEAR_SCORE:" + symbol)
            probability = round(predicted, 12)
        values = {k: _safe_float(last.iloc[0][k]) for k in COLUMNS}
        digest = sha256_bytes(canonical_json(values).encode())
        for family in FAMILIES:
            candidate = bool(
                (reg and probability is not None and probability >= ML_THRESHOLD)
                if family == "BEAR_LOGISTIC" else rule
            )
            rows[(symbol, family)] = {
                "eligible": reg,
                "candidate": candidate,
                "probability": probability if family == "BEAR_LOGISTIC" else None,
                "shadow_only": symbol in spec["high_risk_shadow_only"],
                "feature_sha256": digest,
                "fold_status": fold["status"] if family == "BEAR_LOGISTIC"
                               else "FROZEN_RULE_NO_FIT",
                "bear_training_rows": int(fold["bear_training_rows"])
                                      if family == "BEAR_LOGISTIC" else None,
                "vix_prior": _safe_float(last.iloc[0]["vix_lag"]),
                "rsi14": _safe_float(last.iloc[0]["rsi14"]),
                "macd_hist": _safe_float(last.iloc[0]["macd_hist"]),
                "ret1": _safe_float(last.iloc[0]["ret1"]),
                "policy": {
                    "bear": f"prior_spy_below_200ma_and_prior_vix_le_{BEAR_VIX_MAX:g}",
                    "rule": f"rsi_{BEAR_RSI_LOW:g}_{BEAR_RSI_HIGH:g}_ret1_positive_macd_rising",
                    "probability_threshold": ML_THRESHOLD if family == "BEAR_LOGISTIC" else None,
                    "min_early_bear_training_rows": MIN_BEAR_TRAIN if family == "BEAR_LOGISTIC" else None,
                },
            }
    if len(rows) != 40:
        raise RuntimeError("INCOMPLETE_BEAR_FORECASTS")
    return rows


def asof_calendar_check(journal):
    import exchange_calendars as xc
    cal = xc.get_calendar("XNYS")
    for event in journal:
        recorded = pd.Timestamp(event["recorded_at_utc"])
        if recorded.tzinfo is None:
            raise RuntimeError("BEAR_RECORD_MISSING_UTC_OFFSET")
        if event["kind"] == "SIGNAL":
            accepted, _ = check_signal_admission(event["signal_date"], recorded)
            if not accepted:
                raise RuntimeError("BACKDATED_BEAR_SIGNAL_FORBIDDEN")
        else:
            exit_session = cal.date_to_session(event["exit_date"], direction="none")
            if recorded < cal.session_close(exit_session):
                raise RuntimeError("PREMATURE_BEAR_SETTLEMENT_FORBIDDEN")


def run(spec, prior_zip, market, features, qc_path, baseline_journal,
        out, *, now=None, run_id=None, source_sha=None, scorer=None):
    stamp = pd.Timestamp(datetime.now(timezone.utc) if now is None else now)
    if stamp.tzinfo is None:
        raise RuntimeError("BEAR_RUN_NEEDS_TZ_AWARE_TIMESTAMP")
    stamp = stamp.tz_convert("UTC")
    recorded_at = stamp.isoformat()
    qc = json.loads(Path(qc_path).read_text())
    if qc.get("status") != "READY" or qc.get("required") != 26 or qc.get("ready") != 26:
        raise RuntimeError("BEAR_FORWARD_REQUIRES_ALL_26_QC")
    from daily20 import last_completed_nyse
    session = str(last_completed_nyse(stamp))
    if str(qc.get("expected_session")) != session:
        raise RuntimeError("BEAR_BACKDATED_QC_SESSION")
    # The CLI passes a path; unit tests may supply exactly the same ZIP bytes.
    blob = prior_zip if isinstance(prior_zip, bytes) else Path(prior_zip).read_bytes()
    manifest, previous_bull, journal = read_prior_bear(blob, set(spec["core"]))
    if str(manifest.get("data_expected_last_closed_xnys")) > session:
        raise RuntimeError("BEAR_PRIOR_FROM_FUTURE")
    baseline_file = Path(baseline_journal)
    if not baseline_file.is_file():
        raise RuntimeError("BEAR_MISSING_CURRENT_BULL_JOURNAL")
    baseline = [json.loads(row) for row in baseline_file.read_text().splitlines() if row]
    bulls, _ = check_bull_events(baseline, set(spec["core"]))
    prev_bulls, _ = check_bull_events(previous_bull, set(spec["core"]))
    if set(prev_bulls) - set(bulls):
        raise RuntimeError("BEAR_BASELINE_HISTORY_DROPPED")
    for key, previous in prev_bulls.items():
        if previous["hash"] != bulls[key]["hash"]:
            raise RuntimeError("BEAR_BASELINE_HISTORY_REVISED")

    signals, settled = validate_bear_events(journal, set(spec["core"]))
    today = [key for key in signals if key[0] == session]
    admit, next_open = check_signal_admission(session, stamp)
    # Creating bear snapshots for the first time is allowed only during a
    # genuinely future (pre-next-open) window with same-session Bull evidence.
    has_current_baseline = all((session, s) in bulls for s in spec["core"])
    new_signals = 0
    # The already-sealed signal takes precedence over current adjusted-history
    # replay. Report any changed feature or score; NEVER mutate the frozen
    # original or use recomputed values for delayed outcome attribution.
    frozen_replay_differences = []
    if today:
        if len(today) != 40:
            raise RuntimeError("BEAR_PARTIAL_SESSION_CANNOT_BE_REPAIRED")
        if not has_current_baseline:
            raise RuntimeError("BEAR_MISSING_CONTEMPORANEOUS_BULL_EVIDENCE")
        if admit:
            candidate_rows = (scorer or score_bear_asof)(
                spec, market, features, session)
            for symbol in spec["core"]:
                for family in FAMILIES:
                    frozen = signals[(session, symbol, family)]
                    current = candidate_rows[(symbol, family)]
                    changed = [
                        key for key in ("eligible", "candidate", "probability",
                                        "shadow_only", "feature_sha256", "fold_status",
                                        "bear_training_rows", "vix_prior", "rsi14",
                                        "macd_hist", "ret1", "policy")
                        if frozen.get(key) != current.get(key)
                    ]
                    if changed:
                        frozen_replay_differences.append({
                            "symbol": symbol,
                            "family": family,
                            "changed_fields": changed,
                            "frozen_event_hash": frozen["hash"],
                            "frozen_candidate": frozen["candidate"],
                            "recomputed_candidate": current["candidate"],
                            "frozen_probability": frozen["probability"],
                            "recomputed_probability": current["probability"],
                            "classification": "REPLAY_DRIFT_FROZEN_EVENT_PRESERVED",
                        })
    elif admit and has_current_baseline:
        candidate_rows = (scorer or score_bear_asof)(
            spec, market, features, session)
        if set(candidate_rows) != {
            (symbol, family) for symbol in spec["core"] for family in FAMILIES
        }:
            raise RuntimeError("BEAR_INCOMPLETE_CURRENT_MODEL_SCORES")
        for symbol in spec["core"]:
            anchor = bulls[(session, symbol)]
            if anchor["recorded_at_utc"] > recorded_at:
                raise RuntimeError("BEAR_BASELINE_CAPTURED_IN_FUTURE")
            for family in FAMILIES:
                add_event(journal, {
                    "kind": "SIGNAL", "research_only": True,
                    "signal_date": session, "symbol": symbol, "family": family,
                    "baseline_signal_hash": anchor["hash"],
                    "model_version": VERSION,
                    "recorded_at_utc": recorded_at,
                    "source_actions_run_id": str(run_id or os.environ.get("GITHUB_RUN_ID", "local")),
                    "source_sha": str(source_sha or os.environ.get("GITHUB_SHA", "local")),
                    "horizon_us_sessions": HOLD_SESSIONS,
                    **candidate_rows[(symbol, family)],
                })
        new_signals = 40
    elif not journal:
        raise RuntimeError("BEAR_FORWARD_FIRST_SEAL_MISSED_PRE_NEXT_OPEN")
    signals, settled = validate_bear_events(journal, set(spec["core"]))
    newly_settled = 0
    for key, signal in list(signals.items()):
        if key in settled:
            continue
        observed = new_observation(signal, market, session, recorded_at)
        if observed is None:
            continue
        observed["family"] = signal["family"]
        add_event(journal, observed)
        newly_settled += 1

    signals, settled = validate_bear_events(journal, set(spec["core"]))
    # Each date is complete in two independent families, never a partial cohort.
    by_date = {}
    for date, symbol, family in signals:
        by_date.setdefault(date, set()).add((symbol, family))
    if any(len(keys) != 40 for keys in by_date.values()):
        raise RuntimeError("BEAR_PARTIAL_FROZEN_HISTORY")
    asof_calendar_check(journal)
    output = Path(out)
    output.mkdir(parents=True, exist_ok=True)
    content = journal_bytes(journal)
    (output / "journal.jsonl").write_bytes(content)
    snapshots = pd.DataFrame(e for e in journal if e["kind"] == "SIGNAL")
    outcomes = pd.DataFrame(e for e in journal if e["kind"] == "SETTLED")
    snapshots.to_csv(output / "snapshots.csv", index=False)
    if outcomes.empty:
        outcomes = pd.DataFrame(columns=("signal_date", "symbol", "family",
                                         "exit_date", "gross_return"))
    outcomes.to_csv(output / "outcomes.csv", index=False)
    latest = snapshots.loc[snapshots["signal_date"] == session]
    if latest.empty:
        latest = pd.DataFrame(columns=snapshots.columns)
    latest.to_csv(output / "latest_candidates.csv", index=False)
    family_counts = {}
    for family in FAMILIES:
        frozen_family = [s for s in signals.values() if s["family"] == family]
        matured = [e for e in journal if e["kind"] == "SETTLED"
                   and e["family"] == family and e["candidate_at_signal_time"]]
        family_counts[family] = {
            "signals": len(frozen_family),
            "candidates": sum(bool(s["candidate"]) for s in frozen_family),
            "matured_candidate_observations": len(matured),
            "avg_net_return_20bp": (
                float(np.mean([x["net_return_by_cost_bp"]["20"] for x in matured]))
                if matured else None
            ),
            "win_rate_20bp": (
                float(np.mean([x["net_return_by_cost_bp"]["20"] > 0 for x in matured]))
                if matured else None
            ),
        }
    report = {
        "version": VERSION, "status": "RESEARCH_ONLY", "research_only": True,
        "live_execution": False, "approved_live": False,
        "source_run_id": str(run_id or os.environ.get("GITHUB_RUN_ID", "local")),
        "source_sha": str(source_sha or os.environ.get("GITHUB_SHA", "local")),
        "created_at_utc": recorded_at,
        "last_completed_session": session,
        "next_session_open_utc": next_open,
        "new_signal_events": new_signals,
        "frozen_replay_drift": len(frozen_replay_differences),
        "frozen_replay_differences": frozen_replay_differences,
        "new_settled_events": newly_settled,
        "signal_events": len(signals),
        "settled_events": len(settled),
        "pending_events": len(signals) - len(settled),
        "frozen_sessions": len(by_date),
        "first_admitted_session": sorted(by_date)[0],
        "latest_admitted_session": sorted(by_date)[-1],
        "family": family_counts,
        "journal_sha256": sha256_bytes(content),
        "journal_hash_tip": journal[-1]["hash"],
        "historical_oos_promoted": False,
        "backdated_signal_reconstruction": False,
        "benchmark_model_not_modified": True,
        "model_versions_stay_separate": True,
        "no_broker_order": True,
        "only_observation_not_portfolio_equity": True,
        "warnings": [
            "The 2024–2026 bear model results are historical discovery, not prospective performance",
            "A model probability is frozen only if the trained prior-year model is available",
            "Bear-only eligibility uses prior-session SPY and VIX; RSI and MACD use signal close",
            "No backfill after following XNYS open; missed dates remain missing",
            "Settlement only after fourth subsequent XNYS close, without actual broker fills",
            "No live promotion or cross-strategy model selection from observed outcomes",
        ],
    }
    write_json(output / "report.json", report)
    print(json.dumps({"DAILY20_BEAR_FORWARD": {
        "status": "SEALED", "last_session": session,
        "new_signals": new_signals,
        "frozen_replay_drift": len(frozen_replay_differences),
        "signal_events": len(signals),
        "settled": len(settled), "pending": len(signals) - len(settled),
        "new_settlements": newly_settled,
        "family": family_counts,
        "journal_tip": journal[-1]["hash"][:16],
    }}))
    return report


def run_pr_asof_smoke(spec, market, features, qc_path, out):
    """Regression smoke only: PR previews are NEVER admitted forward signals."""
    qc = json.loads(Path(qc_path).read_text())
    if qc.get("status") != "READY" or qc.get("ready") != 26:
        raise RuntimeError("BEAR_PR_SMOKE_REQUIRES_MARKET_QC")
    session = str(qc["expected_session"])
    scored = score_bear_asof(spec, market, features, session)
    rows = list(scored.items())
    if len(rows) != 40 or any(not isinstance(row["candidate"], bool)
                              for (_, row) in rows):
        raise RuntimeError("BEAR_PR_SMOKE_INCOMPLETE")
    diagnostics = {
        "status": "PR_RETROSPECTIVE_SCORER_CHECK_NOT_FORWARD_EVIDENCE",
        "research_only": True, "forward_signal_events": 0,
        "asof_session": session, "scored_rows": len(rows),
        "candidate_counts": {
            fam: sum(v["candidate"] for (sym, family), v in rows if family == fam)
            for fam in FAMILIES
        },
        "eligible_bear_symbols": sum(
            scored[(symbol, "BEAR_RULE")]["eligible"] for symbol in spec["core"]
        ),
        "bear_logistic_available": sum(
            scored[(symbol, "BEAR_LOGISTIC")]["probability"] is not None
            for symbol in spec["core"]
        ),
        "not_prospective_evidence": True, "no_broker_order": True,
    }
    write_json(Path(out) / "pr_asof_smoke.json", diagnostics)
    print(json.dumps({"DAILY20_BEAR_PR_SCORER": diagnostics}))
    return diagnostics


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="research/kalman_daily20/universe.json")
    p.add_argument("--prior-zip")
    p.add_argument("--market", required=True)
    p.add_argument("--features", required=True)
    p.add_argument("--qc", required=True)
    p.add_argument("--pr-asof-smoke", action="store_true")
    p.add_argument("--baseline-journal")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    if args.pr_asof_smoke:
        run_pr_asof_smoke(load_spec(args.config), args.market, args.features,
                          args.qc, args.out)
        return
    if not args.prior_zip or not args.baseline_journal:
        raise RuntimeError("BEAR_FORWARD_REQUIRES_PRIOR_DRIVE_AND_FROZEN_BASELINE")
    run(load_spec(args.config), args.prior_zip, args.market, args.features,
        args.qc, args.baseline_journal, args.out)


if __name__ == "__main__":
    main()
