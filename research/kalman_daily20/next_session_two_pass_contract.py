#!/usr/bin/env python3
"""Fail-closed first-seal vs replay evidence, without placing or altering orders.

This is a *proof of the handoff*. Validate existing, authenticated Drive archive
BEFORE writers run; then verify the exact original journal byte prefix, cohort
counts and frozen 26/420/40/60 snapshot after the current research run.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from daily20 import load_spec, write_json
from forward_shadow import (
    JOURNAL as BULL_JOURNAL, ROOT_HASH, check_events, check_signal_admission,
    validate_prior_results_archive,
)
from bear_forward import validate_bear_events
from prospective_seal_attestation import FIRST_ELIGIBLE, attest_snapshot

VERSION = "daily20-first-seal-two-pass-contract-v1"
BEAR_JOURNAL = "research/bear_forward/journal.jsonl"
SNAP_PREFIX = "research/stability/snapshots/"
FIRST_SCHEDULE = "40 2 * * 2-6"
REPLAY_SCHEDULE = "40 4 * * 2-6"
VALID_SCHEDULE_SLOTS = ("", FIRST_SCHEDULE, REPLAY_SCHEDULE)
VALID_EVENT_ORIGINS = ("", "push", "schedule", "workflow_dispatch")


def require(condition, message):
    if not condition:
        raise RuntimeError("TWO_PASS_" + message)


def digest(body):
    return sha256(body).hexdigest()


def read_events(body):
    return [json.loads(line) for line in body.splitlines() if line.strip()]


def validate_prior(blob, core):
    # Checks every signed manifest member, Bull event hash chains, journal dates
    # and the complete existing universe.
    manifest, _ = validate_prior_results_archive(blob, core)
    with ZipFile(BytesIO(blob)) as z:
        names = set(z.namelist())
        require(BULL_JOURNAL in names and BEAR_JOURNAL in names,
                "HISTORIC_JOURNAL_MISSING")
        bull_raw, bear_raw = z.read(BULL_JOURNAL), z.read(BEAR_JOURNAL)
        bull_signals, bull_settled = check_events(
            read_events(bull_raw), set(core))
        bear_signals, bear_settled = validate_bear_events(
            read_events(bear_raw), set(core))
        frozen = {name: digest(z.read(name)) for name in names
                  if name.startswith(SNAP_PREFIX) and name.endswith(".json")}
        old_asof = manifest["data_expected_last_closed_xnys"]
        return {
            "prior_manifest_session": old_asof,
            "prior_actions_run_id": str(manifest["source_actions_run_id"]),
            "prior_bull_journal_sha256": digest(bull_raw),
            "prior_bear_journal_sha256": digest(bear_raw),
            "prior_bull_journal_bytes": len(bull_raw),
            "prior_bear_journal_bytes": len(bear_raw),
            "prior_bull_signal_events": len(bull_signals),
            "prior_bear_signal_events": len(bear_signals),
            "prior_bull_settled_events": len(bull_settled),
            "prior_bear_settled_events": len(bear_settled),
            "frozen_snapshot_sha256": frozen,
            "existing_bull_sessions": sorted({s for s, _ in bull_signals}),
            "existing_bear_sessions": sorted({s for s, _, _ in bear_signals}),
            "current_prior_bull_keys": bull_signals,
            "current_prior_bear_keys": bear_signals,
            "prior_raw": {BULL_JOURNAL: bull_raw, BEAR_JOURNAL: bear_raw},
        }


def decide(core, prior, session, *, clock, schedule_slot="", current_run_id=None,
           event_name=""):
    require(schedule_slot in VALID_SCHEDULE_SLOTS, "UNKNOWN_SCHEDULE_SLOT")
    require(event_name in VALID_EVENT_ORIGINS, "UNKNOWN_GITHUB_EVENT_ORIGIN")
    if event_name == "schedule":
        require(schedule_slot in (FIRST_SCHEDULE, REPLAY_SCHEDULE),
                "SCHEDULED_EVENT_WITHOUT_AN_EXACT_SLOT")
    elif event_name:
        require(schedule_slot == "", "NON_SCHEDULED_EVENT_FORGED_A_SLOT")
    require(len(core) == 20 and len(set(core)) == 20,
            "UNIVERSE_NOT_20_UNIQUE")
    require(isinstance(session, str) and
            session >= FIRST_ELIGIBLE or session == "2026-11-20",
            "UNSUPPORTED_SESSION")
    require(prior["prior_manifest_session"] <= session,
            "PRIOR_ARCHIVE_FROM_FUTURE")
    from daily20 import last_completed_nyse
    stamp = pd.Timestamp(clock)
    require(stamp.tzinfo is not None and session == str(last_completed_nyse(stamp)),
            "NOT_LATEST_FULLY_CLOSED_XNYS_SESSION")
    accepted, next_open = check_signal_admission(session, stamp)
    bull = [sym for (day, sym) in prior["current_prior_bull_keys"]
            if day == session]
    bear = [(sym, family)
            for day, sym, family in prior["current_prior_bear_keys"]
            if day == session]
    require(len(bull) in (0, 20) and len(bear) in (0, 40)
            and set(bull) in (set(), set(core))
            and (not bear or set(bear) ==
                 {(s, fam) for s in core
                  for fam in ("BEAR_LOGISTIC", "BEAR_RULE")}),
            "PRIOR_PARTIAL_COHORT")
    require((len(bull) == 0) == (len(bear) == 0),
            "PRIOR_BULL_BEAR_SEAL_DISAGREEMENT")
    captured = SNAP_PREFIX + session + ".json"
    prior_snapshot = prior["frozen_snapshot_sha256"].get(captured)
    if bull:
        mode = ("SAME_SESSION_REPLAY_EXPECTED"
                if prior_snapshot is not None else
                "LEGACY_REPLAY_NO_20261120_ORIGINAL_FEATURES_HOLD")
    elif accepted:
        mode = "FIRST_GENUINE_SEAL_EXPECTED"
    else:
        mode = "FIRST_SEAL_WINDOW_MISSED_HOLD"
    if mode == "FIRST_GENUINE_SEAL_EXPECTED":
        require(session >= FIRST_ELIGIBLE and prior_snapshot is None,
                "RETROSPECTIVE_FIRST_SEAL_NOT_ALLOWED")
        # Daily20 research also runs automatically on PR-related main pushes.
        # A push that happens after the NYSE close but before the scheduled
        # 02:40 UTC first pass must NOT steal the original 60 event hashes.
        # A *deliberate* manual dispatch retains the existing research-only
        # recovery behavior, but does not count as the scheduled first run
        # in the independent two-slot watchdog.
        require(event_name != "push",
                "MAIN_PUSH_MUST_NOT_PREEMPT_SCHEDULED_FIRST_SEAL")
    # A scheduled replay must NOT become a belated first seal if the earlier
    # GitHub scheduled job failed or never ran. This preflight executes before
    # either original forward writer; an abort means no files are published.
    # On a holiday the 02:40 UTC slot sees an already recorded XNYS session
    # and is allowed to audit it as a replay without manufacturing a new day.
    if schedule_slot == REPLAY_SCHEDULE and session >= FIRST_ELIGIBLE:
        require(mode == "SAME_SESSION_REPLAY_EXPECTED"
                and prior["prior_manifest_session"] == session,
                "SCHEDULED_REPLAY_WITHOUT_VERIFIED_FIRST_SEAL")
        if current_run_id is not None:
            require(str(prior["prior_actions_run_id"]) != str(current_run_id),
                    "REPLAY_MUST_USE_DISTINCT_ACTIONS_RUN")
    if (schedule_slot == FIRST_SCHEDULE and session >= FIRST_ELIGIBLE
            and prior["prior_manifest_session"] < session):
        require(mode == "FIRST_GENUINE_SEAL_EXPECTED",
                "FIRST_SCHEDULE_NEW_SESSION_SEAL_MISSING")
    expected_new_bull = 20 if mode == "FIRST_GENUINE_SEAL_EXPECTED" else 0
    expected_new_bear = 40 if expected_new_bull else 0
    return {
        "version": VERSION, "session": session,
        "prior_session": prior["prior_manifest_session"],
        "prior_actions_run_id": prior["prior_actions_run_id"],
        "mode": mode, "scheduled_slot": schedule_slot,
        "github_event_origin": event_name,
        "scheduled_replay_first_seal_verified": (schedule_slot == REPLAY_SCHEDULE
            and mode == "SAME_SESSION_REPLAY_EXPECTED"),
        "research_only": True,
        "production_writes": False, "live_execution": False,
        "strategy_promoted": False, "price_certified": False,
        "scheduled_admission_open": accepted,
        "next_open_utc": next_open,
        "expected_new_bull": expected_new_bull,
        "expected_new_bear": expected_new_bear,
        "prior_bull_signal_events": prior["prior_bull_signal_events"],
        "prior_bear_signal_events": prior["prior_bear_signal_events"],
        "prior_bull_journal_sha256": prior["prior_bull_journal_sha256"],
        "prior_bear_journal_sha256": prior["prior_bear_journal_sha256"],
        "prior_bull_journal_bytes": prior["prior_bull_journal_bytes"],
        "prior_bear_journal_bytes": prior["prior_bear_journal_bytes"],
        "prior_original_snapshot_sha256": prior_snapshot,
        "prior_snapshot_count": len(prior["frozen_snapshot_sha256"]),
        "no_historical_reseal": True,
    }


def postflight(plan, prior, core, bull_dir, bear_dir, stability_dir, *, run_id, schedule_slot=None):
    require(plan.get("version") == VERSION and
            plan.get("research_only") is True and
            plan.get("production_writes") is False and
            plan.get("strategy_promoted") is False,
            "INVALID_PREFLIGHT_GOVERNANCE")
    session = plan["session"]
    if schedule_slot is not None:
        require(schedule_slot in VALID_SCHEDULE_SLOTS
                and plan.get("scheduled_slot") == schedule_slot,
                "PREFLIGHT_POSTFLIGHT_SCHEDULE_ROLE_CHANGED")
    if plan.get("scheduled_slot") == REPLAY_SCHEDULE:
        require(plan.get("scheduled_replay_first_seal_verified") is True
                and plan.get("expected_new_bull") == 0
                and plan.get("expected_new_bear") == 0,
                "SCHEDULED_REPLAY_NOT_VERIFIED")
    bull_dir, bear_dir = Path(bull_dir), Path(bear_dir)
    stability_dir = Path(stability_dir)
    report_bull = json.loads((bull_dir / "report.json").read_text())
    report_bear = json.loads((bear_dir / "report.json").read_text())
    report_stability = json.loads((stability_dir / "report.json").read_text())
    require(report_bull["last_completed_session"] ==
            report_bear["last_completed_session"] ==
            report_stability["session"] == session,
            "POSTFLIGHT_WRONG_ASOF")
    require(report_bull["source_run_id"] == report_bear["source_run_id"] == str(run_id),
            "POSTFLIGHT_RUN_ID_WRONG")
    require(report_bull["new_signal_events"] == plan["expected_new_bull"]
            and report_bear["new_signal_events"] == plan["expected_new_bear"]
            and report_stability["new_sealed_bull_signals"] == plan["expected_new_bull"]
            and report_stability["new_sealed_bear_signals"] == plan["expected_new_bear"],
            "POSTFLIGHT_NEW_SIGNAL_COUNT_INCONSISTENT")
    require(report_stability["research_only"] is True
            and report_stability["strategy_promoted"] is False
            and report_stability["source_finality_verified_assets"] == 0
            and report_stability["research_hold"] is True,
            "POSTFLIGHT_FALSE_SCIENTIFIC_PROMOTION")
    observed = {}
    for name, path in ((BULL_JOURNAL, bull_dir / "journal.jsonl"),
                       (BEAR_JOURNAL, bear_dir / "journal.jsonl")):
        body = path.read_bytes()
        previous = prior["prior_raw"][name]
        require(body.startswith(previous), "PRIOR_JOURNAL_BYTES_NOT_PREFIX_" + name)
        observed[name] = body
    bs, _ = check_events(read_events(observed[BULL_JOURNAL]), set(core))
    brs, _ = validate_bear_events(read_events(observed[BEAR_JOURNAL]), set(core))
    require(len(bs) == prior["prior_bull_signal_events"] + plan["expected_new_bull"]
            and len(brs) == prior["prior_bear_signal_events"] + plan["expected_new_bear"]
            and len([key for key in bs if key[0] == session]) == 20
            and len([key for key in brs if key[0] == session]) == 40,
            "POSTFLIGHT_PARTIAL_OR_MUTATED_COHORT")
    if plan["expected_new_bull"]:
        require(all(bs[(session, symbol)]["source_actions_run_id"] == str(run_id)
                    for symbol in core) and
                all(brs[(session, symbol, fam)]["source_actions_run_id"] == str(run_id)
                    for symbol in core
                    for fam in ("BEAR_LOGISTIC", "BEAR_RULE")),
                "FIRST_SEAL_EVENTS_FROM_OTHER_ACTIONS_RUN")
    frozen = stability_dir / "snapshots" / (session + ".json")
    prior_hash = plan["prior_original_snapshot_sha256"]
    checked_60 = 0
    if plan["expected_new_bull"]:
        require(frozen.is_file() and
                digest(frozen.read_bytes()) == report_stability["frozen_snapshot_sha256"],
                "FIRST_SEAL_SNAPSHOT_MISSING_OR_CHANGED")
        snapshot = json.loads(frozen.read_bytes())
        signed_bull = {(session, symbol, "BULL_LOGISTIC"): bs[(session, symbol)]
                       for symbol in core}
        signed_bear = {
            (session, symbol, family): brs[(session, symbol, family)]
            for symbol in core for family in ("BEAR_LOGISTIC", "BEAR_RULE")
        }
        proof = attest_snapshot(snapshot, session, signed_bull, signed_bear)
        require(proof["original_signal_hash_count"] == 60
                and proof["core_feature_rows_verified"] == 20
                and proof["model_input_fingerprints_verified"] == 40
                and snapshot["source_actions_run_id"] == str(run_id),
                "FIRST_SEAL_26_420_40_60_EVIDENCE_INCOMPLETE")
        checked_60 = 60
    elif prior_hash is not None:
        require(frozen.is_file() and digest(frozen.read_bytes()) == prior_hash
                and report_stability["frozen_snapshot_sha256"] == prior_hash,
                "REPLAY_ORIGINAL_SNAPSHOT_BYTES_REWRITTEN")
        # The prior original has to remain immutable, but current recomputation
        # may differ. Such differences are flagged, NEVER rewritten.
        checked_60 = 60
    else:
        require(not frozen.exists(),
                "LEGACY_SNAPSHOT_RETROACTIVELY_FABRICATED")
    # Validate all *older* snapshots retain their exact source bytes too.
    for name, oldhash in prior["frozen_snapshot_sha256"].items():
        path = stability_dir / name.replace("research/stability/", "")
        require(path.is_file() and digest(path.read_bytes()) == oldhash,
                "PRIOR_OTHER_SESSION_SNAPSHOT_REPLACED")
    status = ("FIRST_SEAL_26_PRICE_420_FEATURE_40_MODEL_60_EVENT_ATTESTED_HOLD"
              if plan["expected_new_bull"] else
              "SAME_SESSION_REPLAY_DRIFT_RESEARCH_HOLD"
              if prior_hash and report_stability["incidents_count"] > 0 else
              "SAME_SESSION_REPLAY_INPUTS_UNCHANGED_SOURCE_HOLD"
              if prior_hash else
              "LEGACY_OR_MISSED_FIRST_SEAL_HOLD")
    return {
        "version": VERSION, "session": session,
        "research_only": True, "production_writes": False,
        "live_execution": False, "strategy_promoted": False,
        "status": status, "mode": plan["mode"],
        "current_actions_run_id": str(run_id),
        "prior_actions_run_id": plan["prior_actions_run_id"],
        "bull_new": report_bull["new_signal_events"],
        "bear_new": report_bear["new_signal_events"],
        "journal_prefix_byte_identical": True,
        "all_prior_snapshots_byte_identical": True,
        "original_snapshot_sha256": (
            digest(frozen.read_bytes()) if frozen.is_file() else None),
        "full_26_price_420_feature_40_model_60_event_attested": (
            checked_60 == 60 and
            plan["expected_new_bull"] == 20),
        "replay_numerical_incidents": report_stability["incidents_count"],
        "replay_inputs_changed": bool(
            prior_hash and report_stability["incidents_count"] > 0),
        "full_raw_market_close_certified": False,
        "original_signal_events_rewritten": False,
        "research_hold": True,
        "no_broker_orders": True,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", required=True, choices=("pre", "post"))
    p.add_argument("--prior-zip", required=True)
    p.add_argument("--config", default="research/kalman_daily20/universe.json")
    p.add_argument("--qc", required=True)
    p.add_argument("--schedule-slot", default="")
    p.add_argument("--event-name", default="")
    p.add_argument("--pre", required=True)
    p.add_argument("--bull-dir")
    p.add_argument("--bear-dir")
    p.add_argument("--stability-dir")
    p.add_argument("--out")
    a = p.parse_args()
    spec = load_spec(a.config)
    prior_blob = Path(a.prior_zip).read_bytes()
    prior = validate_prior(prior_blob, spec["core"])
    qc = json.loads(Path(a.qc).read_text())
    require(qc.get("status") == "READY" and
            qc.get("required") == qc.get("ready") == 26,
            "CURRENT_MARKET_QC_NOT_READY")
    session = qc.get("expected_session")
    if a.phase == "pre":
        report = decide(spec["core"], prior, session,
                        clock=datetime.now(timezone.utc),
                        schedule_slot=a.schedule_slot,
                        event_name=a.event_name,
                        current_run_id=os.environ.get("GITHUB_RUN_ID"))
        report["prior_results_zip_sha256"] = digest(prior_blob)
        write_json(a.pre, report)
        print("DAILY20_TWO_PASS_PREFLIGHT", session, report["mode"],
              "new", report["expected_new_bull"], report["expected_new_bear"])
    else:
        require(all((a.bull_dir, a.bear_dir, a.stability_dir, a.out)),
                "POSTFLIGHT_MISSING_INPUTS")
        pre = json.loads(Path(a.pre).read_text())
        require(pre.get("scheduled_slot") == a.schedule_slot,
                "PREFLIGHT_POSTFLIGHT_SCHEDULE_ROLE_CHANGED")
        require(pre.get("github_event_origin") == a.event_name,
                "PREFLIGHT_POSTFLIGHT_EVENT_ORIGIN_CHANGED")
        require(pre.get("prior_results_zip_sha256") == digest(prior_blob)
                and pre.get("session") == session,
                "PREFLIGHT_PRIOR_SOURCE_OR_SESSION_CHANGED")
        report = postflight(pre, prior, spec["core"], a.bull_dir,
                            a.bear_dir, a.stability_dir,
                            run_id=os.environ.get("GITHUB_RUN_ID", "local"),
                            schedule_slot=a.schedule_slot)
        write_json(a.out, report)
        print("DAILY20_TWO_PASS_POSTFLIGHT", session, report["status"],
              "new", report["bull_new"], report["bear_new"],
              "replay_incidents", report["replay_numerical_incidents"])


if __name__ == "__main__":
    main()
