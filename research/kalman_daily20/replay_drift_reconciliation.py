#!/usr/bin/env python3
"""Reconcile frozen Bull/Bear replays with the independent stability gate.

Historical 2026-11-20 source revisions are already investigated in issue #884.
This auditor never back-fills the original 21-feature snapshot and cannot
assert which upstream market-feed mechanism caused a given probability drift.
It reports the same-day per-symbol observations and verifies that material
legacy Bull differences are present in the stability gate's HOLD incidents.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import io
import json
import math
from pathlib import Path

from daily20 import load_spec, write_json

VERSION = "daily20-replay-reconciliation-v1"
EXPECTED = {
    "bull": "daily20-forward-shadow-v1",
    "bear": "daily20-bear-forward-v1",
    "stability": "daily20-prospective-stability-v1",
    "finality": "daily20-source-finality-v1",
}
FAMILIES = ("BULL_LOGISTIC", "BEAR_LOGISTIC", "BEAR_RULE")
EPSILON_PP = 1e-10
FIELDS = (
    "session", "symbol", "family", "frozen_probability", "recomputed_probability",
    "delta_percentage_points", "candidate_changed", "shadow_only_changed",
    "changed_fields", "material_replay", "stability_incident_present",
    "legacy_no_original_features", "first_event_hash", "cause_certified",
)


def ensure(condition, code):
    if not condition:
        raise ValueError(code)


def safe_probability(obj):
    if obj is None:
        return None
    ensure(type(obj) in (float, int), "REPLAY_PROBABILITY_TYPE")
    value = float(obj)
    ensure(math.isfinite(value) and 0 <= value <= 1, "REPLAY_PROBABILITY_RANGE")
    return value


def digest(blob):
    return sha256(blob).hexdigest()


def source_report(path, version):
    raw = Path(path).read_bytes()
    report = json.loads(raw)
    ensure(report.get("version") == version, "REPLAY_INPUT_VERSION_MISMATCH")
    return report, digest(raw)


def one_diff(row, session, valid_symbols, family, *, bear):
    ensure(isinstance(row, dict), "REPLAY_INVALID_DIFFERENCE_ROW")
    symbol = row.get("symbol")
    ensure(symbol in valid_symbols, "REPLAY_DIFFERENCE_UNKNOWN_SYMBOL")
    if bear:
        ensure(row.get("family") == family, "REPLAY_BEAR_WRONG_FAMILY")
        before = row.get("frozen_probability")
        after = row.get("recomputed_probability")
        old_flag = row.get("frozen_candidate")
        new_flag = row.get("recomputed_candidate")
        old_shadow = new_shadow = None
        changed = row.get("changed_fields")
        ensure(isinstance(changed, list) and
               all(isinstance(v, str) for v in changed),
               "REPLAY_BEAR_CHANGED_FIELDS_INVALID")
    else:
        before = row.get("frozen_probability")
        after = row.get("recomputed_probability")
        old_flag = row.get("frozen_candidate")
        new_flag = row.get("recomputed_candidate")
        old_shadow = row.get("frozen_shadow_only")
        new_shadow = row.get("recomputed_shadow_only")
        ensure(type(old_shadow) is bool and type(new_shadow) is bool,
               "REPLAY_BULL_SHADOW_FLAG_INVALID")
        changed = [
            key for key, old, new in (
                ("probability", before, after),
                ("candidate", old_flag, new_flag),
                ("shadow_only", old_shadow, new_shadow),
            ) if old != new
        ]
    ensure(type(old_flag) is bool and type(new_flag) is bool,
           "REPLAY_CANDIDATE_FLAG_INVALID")
    a, b = safe_probability(before), safe_probability(after)
    delta = (b - a) * 100 if a is not None and b is not None else None
    event_hash = row.get("frozen_event_hash")
    ensure(isinstance(event_hash, str) and len(event_hash) == 64
           and all(c in "0123456789abcdef" for c in event_hash.lower()),
           "REPLAY_EVENT_HASH_INVALID")
    return {
        "session": session, "symbol": symbol, "family": family,
        "frozen_probability": a, "recomputed_probability": b,
        "delta_percentage_points": delta,
        "candidate_changed": old_flag != new_flag,
        "shadow_only_changed": old_shadow != new_shadow if not bear else False,
        "probability_missing_changed": (a is None) != (b is None),
        "changed_fields": changed,
        "first_event_hash": event_hash,
        "cause_certified": False,
    }


def reconcile(spec, bull, bear, stability, finality, hashes):
    core = list(spec["core"])
    ensure(len(core) == 20 and len(set(core)) == 20,
           "REPLAY_CORE_NOT_20")
    ensure(len(spec["context"]) == 6 and
           len(set(core + list(spec["context"]))) == 26,
           "REPLAY_ASSETS_NOT_26")
    session = bull.get("last_completed_session")
    ensure(isinstance(session, str) and len(session) == 10
           and session == bear.get("last_completed_session")
           == stability.get("session") == finality.get("session"),
           "REPLAY_SESSION_MISMATCH")
    ensure(bull.get("version") == EXPECTED["bull"] and
           bear.get("version") == EXPECTED["bear"] and
           stability.get("version") == EXPECTED["stability"] and
           finality.get("version") == EXPECTED["finality"],
           "REPLAY_VERSION_MISMATCH")
    ensure(bull.get("research_only") is True
           and bull.get("approved_live") is False
           and bear.get("research_only") is True
           and bear.get("approved_live") is False
           and bear.get("no_broker_order") is True
           and stability.get("research_only") is True
           and stability.get("production_writes") is False
           and stability.get("strategy_promoted") is False
           and finality.get("research_only") is True
           and finality.get("research_hold") is True
           and finality.get("verified") == 0
           and finality.get("required") == 26,
           "REPLAY_TRADABILITY_OR_FINALITY_CLAIM")
    threshold = stability.get("drift_threshold_percentage_points_exclusive")
    ensure(type(threshold) in (int, float) and
           abs(threshold - 1.0) < 1e-12,
           "REPLAY_THRESHOLD_NOT_ONE_PERCENT_POINT")
    ensure(bull.get("signal_events", 0) >= 20 and
           bull["signal_events"] % 20 == 0 and
           bear.get("signal_events", 0) >= 40 and
           bear["signal_events"] % 40 == 0,
           "REPLAY_PARTIAL_SEALED_UNIVERSE")
    ensure(bull.get("new_signal_events") in (0, 20) and
           bear.get("new_signal_events") in (0, 40),
           "REPLAY_PARTIAL_NEW_SEAL")
    ensure(bull["new_signal_events"] == stability.get("new_sealed_bull_signals")
           and bear["new_signal_events"] == stability.get("new_sealed_bear_signals"),
           "REPLAY_STABILITY_ADMISSION_MISMATCH")
    legacy = not stability.get("current_session_has_original_snapshot")
    ensure(type(stability.get("current_session_has_original_snapshot")) is bool,
           "REPLAY_SNAPSHOT_STATUS_INVALID")
    if legacy:
        ensure(bull["new_signal_events"] == 0
               and bear["new_signal_events"] == 0
               and stability.get("frozen_snapshot_sha256") is None,
               "REPLAY_LEGACY_FALSE_FIRST_SEAL")
    rows = []
    for family, container, count_key, data_key in (
        ("BULL_LOGISTIC", bull, "frozen_replay_drift_count",
         "frozen_replay_differences"),
        ("BEAR_LOGISTIC", bear, "frozen_replay_drift",
         "frozen_replay_differences"),
    ):
        records = container.get(data_key)
        ensure(isinstance(records, list) and
               len(records) == container.get(count_key),
               "REPLAY_DIFFERENCE_COUNT_INVALID")
        for raw in records:
            derived_family = raw.get("family") if family == "BEAR_LOGISTIC" else family
            ensure(derived_family in FAMILIES and
                   (family == "BULL_LOGISTIC" or
                    derived_family in ("BEAR_LOGISTIC", "BEAR_RULE")),
                   "REPLAY_FAMILY_INVALID")
            rows.append(one_diff(raw, session, core, derived_family,
                                 bear=family != "BULL_LOGISTIC"))
    lookup = {}
    for row in rows:
        key = row["symbol"], row["family"]
        ensure(key not in lookup, "REPLAY_DUPLICATED_EVENT")
        lookup[key] = row
    ensure(sum(r["family"] == "BULL_LOGISTIC" for r in rows) <= 20
           and len(rows) <= 60, "REPLAY_DIFFERENCES_OVERFLOW")
    incidents = stability.get("incidents")
    ensure(isinstance(incidents, list) and
           len(incidents) == stability.get("incidents_count"),
           "REPLAY_STABILITY_INCIDENTS_INVALID")
    inc_map = {}
    for inc in incidents:
        ensure(isinstance(inc, dict) and
               inc.get("symbol") in core and
               inc.get("family") in FAMILIES,
               "REPLAY_UNKNOWN_STABILITY_INCIDENT")
        key = inc["symbol"], inc["family"]
        ensure(key not in inc_map, "REPLAY_DUPLICATED_STABILITY_INCIDENT")
        ensure(type(inc.get("research_hold")) is bool,
               "REPLAY_INCIDENT_HOLD_TYPE")
        inc_map[key] = inc
        if legacy:
            ensure(inc.get("legacy_event_only_no_original_feature_snapshot") is True
                   and inc["research_hold"] is True,
                   "REPLAY_LEGACY_INCIDENT_FALSIFIED")
    results = []
    for row in rows:
        material = (
            row["candidate_changed"] or row["probability_missing_changed"]
            or (row["delta_percentage_points"] is not None and
                abs(row["delta_percentage_points"]) > threshold + EPSILON_PP)
        )
        inc = inc_map.get((row["symbol"], row["family"]))
        row["material_replay"] = material
        row["stability_incident_present"] = inc is not None
        row["legacy_no_original_features"] = legacy
        if legacy and row["family"] == "BULL_LOGISTIC":
            ensure(material == (inc is not None),
                   "REPLAY_LEGACY_BULL_HOLD_RECONCILIATION_FAILED")
            if inc is not None:
                ensure(inc["research_hold"]
                       and inc.get("candidate_flip") == row["candidate_changed"]
                       and (inc.get("probability_delta_pp") is None) ==
                       (row["delta_percentage_points"] is None),
                       "REPLAY_BULL_INCIDENT_VALUE_CONFLICT")
                if inc.get("probability_delta_pp") is not None:
                    ensure(abs(inc["probability_delta_pp"] -
                               row["delta_percentage_points"]) < 0.0001,
                           "REPLAY_BULL_DELTA_INCONSISTENT")
        results.append(row)
    # Non-material legacy rows need not appear in the stability incident list.
    # Bear family records can differ in feature/eligibility fields without a
    # model probability change, so the counts are not interchangeable.
    missing_bull_inc = [k for k in inc_map if k[1] == "BULL_LOGISTIC"
                        and k not in lookup]
    if legacy:
        ensure(not missing_bull_inc, "REPLAY_UNACCOUNTED_LEGACY_BULL_INCIDENT")
    if not legacy and bull.get("new_signal_events") == 20:
        ensure(bull.get("frozen_replay_drift_count") == 0,
               "REPLAY_FIRST_SEAL_HAS_FROZEN_DRIFT")
    full_rows = sorted(results, key=lambda x: (
        -int(x["material_replay"]), -abs(x["delta_percentage_points"] or 0),
        x["symbol"], x["family"]))
    material_bull = sum(r["material_replay"] for r in full_rows
                        if r["family"] == "BULL_LOGISTIC")
    return {
        "version": VERSION, "session": session,
        "research_only": True, "production_writes": False,
        "live_execution": False, "strategy_promoted": False,
        "status": "LEGACY_FROZEN_REPLAY_TRIAGED_RESEARCH_HOLD" if legacy else
                  "SNAPSHOT_ERA_REPLAY_TRIAGED_RESEARCH_HOLD",
        "original_21_feature_snapshot_available": not legacy,
        "legacy_without_original_21_feature_snapshot": legacy,
        "source_artifact_hashes": hashes,
        "bull_drift_count": sum(r["family"] == "BULL_LOGISTIC" for r in full_rows),
        "bull_material_count": material_bull,
        "bear_drift_count": sum(r["family"] != "BULL_LOGISTIC" for r in full_rows),
        "stability_incident_count": len(incidents),
        "stability_material_count": sum(bool(i["research_hold"]) for i in incidents),
        "legacy_bull_holds_reconciled": legacy,
        "original_journals_modified": False,
        "independent_source_finality_verified": 0,
        "causal_upstream_mechanism_certified": False,
        "known_historical_context": (
            "Issue #884, PR #905/#906: initial Nov 20 adjusted daily bar was "
            "revised; same-session feature changes explain most early score "
            "drift, with several first prices matching published after-hours "
            "quotes. No original 21-feature seal or source mechanism proof."
        ) if session == "2026-11-20" else None,
        "observations": full_rows,
    }


def csv_bytes(rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for entry in rows:
        writer.writerow({
            key: (json.dumps(entry[key], sort_keys=True)
                  if key == "changed_fields"
                  else "" if entry[key] is None else entry[key])
            for key in FIELDS
        })
    return buffer.getvalue().encode()


def main():
    parser = argparse.ArgumentParser()
    for key in ("bull", "bear", "stability", "finality", "out_dir"):
        parser.add_argument("--" + key.replace("_", "-"), required=True)
    parser.add_argument("--config", default="research/kalman_daily20/universe.json")
    args = parser.parse_args()
    paths = {"bull": args.bull, "bear": args.bear,
             "stability": args.stability, "finality": args.finality}
    reports, hashes = {}, {}
    for key, path in paths.items():
        reports[key], hashes[key + "_sha256"] = source_report(path, EXPECTED[key])
    output = Path(args.out_dir)
    output.mkdir(parents=True, exist_ok=True)
    result = reconcile(load_spec(args.config), **reports, hashes=hashes)
    data = csv_bytes(result["observations"])
    (output / "replay_differences.csv").write_bytes(data)
    result["replay_differences_csv_sha256"] = digest(data)
    write_json(output / "report.json", result)
    print(json.dumps({"DAILY20_REPLAY_RECONCILIATION": {
        "session": result["session"], "bull_changed": result["bull_drift_count"],
        "bull_material": result["bull_material_count"],
        "bear_changed": result["bear_drift_count"],
        "stability_incidents": result["stability_incident_count"],
        "legacy_no_original_feature_snapshot":
            result["legacy_without_original_21_feature_snapshot"],
        "status": result["status"], "certified": 0
    }}))


if __name__ == "__main__":
    main()
