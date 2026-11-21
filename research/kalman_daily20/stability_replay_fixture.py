#!/usr/bin/env python3
"""Read-only CI fixture: compare two archived same-session Daily20 market snapshots.

This is a retrospective replay, NOT a prospective forecast. Synthetic event
hashes below are test anchors, never represented as real sealed journal events.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from daily20 import load_spec, write_json
from forward_shadow import read_score_rows
from stability_gate import classify, make_current_snapshot

VERSION = "daily20-stability-real-data-replay-fixture-v1"


def fake_anchor(symbol, family, session):
    return hashlib.sha256(
        ("NOT_A_REAL_SIGNAL:" + session + ":" + symbol + ":" + family).encode()
    ).hexdigest()


def source_paths(root):
    root = Path(root)
    if not (root / "market/raw/yfinance").is_dir():
        raise RuntimeError("MISSING_REAL_ARCHIVED_MARKET:" + str(root))
    if not (root / "features/talib").is_dir():
        raise RuntimeError("MISSING_REAL_ARCHIVED_FEATURES:" + str(root))
    return root / "market", root / "features"


def fabricate_test_only_event_anchors(spec, session):
    bull, bear = {}, {}
    for symbol in spec["core"]:
        bull[(session, symbol)] = {
            "hash": fake_anchor(symbol, "BULL_LOGISTIC", session)
        }
        for family in ("BEAR_LOGISTIC", "BEAR_RULE"):
            bear[(session, symbol, family)] = {
                "hash": fake_anchor(symbol, family, session)
            }
    return bull, bear


def run(spec, left_data, right_data, left_research, right_research,
        session, out):
    # Research snapshots are real, but their event anchors are explicitly fake
    # test fixtures, so they must never be imported into the forward journal.
    bull, bear = fabricate_test_only_event_anchors(spec, session)
    first_market, first_ta = source_paths(left_data)
    second_market, second_ta = source_paths(right_data)
    scores_left = read_score_rows(
        Path(left_research) / "research/latest_research_scores.csv",
        spec, session,
    )
    scores_right = read_score_rows(
        Path(right_research) / "research/latest_research_scores.csv",
        spec, session,
    )
    first = make_current_snapshot(spec, first_market, first_ta, scores_left,
                                  session, bull, bear)
    second = make_current_snapshot(spec, second_market, second_ta, scores_right,
                                   session, bull, bear)
    incidents, hold = classify(first, second)
    if first["model_count"] != 40 or second["model_count"] != 40:
        raise RuntimeError("REAL_FIXTURE_INCOMPLETE_MODEL_COUNT")
    if not hold:
        raise RuntimeError("REAL_FIXTURE_MATERIAL_DRIFT_NOT_DETECTED")
    if not any(x["symbol"] == "SPY" and x["family"] == "BULL_LOGISTIC"
               and x["research_hold"] for x in incidents):
        raise RuntimeError("REAL_FIXTURE_SPY_BULL_MATERIAL_DRIFT_MISSING")
    if first["models"]["SPY"]["feature_sha256"] == second["models"]["SPY"]["feature_sha256"]:
        raise RuntimeError("REAL_FIXTURE_REVISED_SPY_FEATURE_NOT_DETECTED")
    if any(first["models"][s]["frozen_signal_hashes"] !=
           second["models"][s]["frozen_signal_hashes"] for s in spec["core"]):
        raise RuntimeError("REAL_FIXTURE_EVENT_ANCHORS_CHANGED")
    # Equal values are not equal source SHA; feature and training hashes reflect
    # the actual numeric input, not bytewise Parquet serialization.
    report = {
        "version": VERSION,
        "fixture_asof_session": session,
        "historical_research_replay_only": True,
        "event_anchors_are_synthetic_fixtures": True,
        "source_is_two_immutable_actions_archives": True,
        "live_execution": False,
        "strategy_promoted": False,
        "research_hold": hold,
        "status": "REPLAY_DRIFT_RESEARCH_HOLD",
        "actual_model_count_per_archive": 40,
        "actual_feature_count_per_model": 21,
        "incident_count": len(incidents),
        "material_incident_count": sum(x["research_hold"] for x in incidents),
        "top_incidents": sorted(
            incidents,
            key=lambda x: abs(x["probability_delta_pp"])
            if x["probability_delta_pp"] is not None else -1,
            reverse=True,
        )[:20],
    }
    write_json(Path(out) / "replay_fixture_report.json", report)
    print(json.dumps({"DAILY20_STABILITY_ARCHIVE_FIXTURE": report}))
    return report


def main():
    ap = argparse.ArgumentParser()
    for key in ("left-data", "right-data", "left-research", "right-research",
                "session", "out"):
        ap.add_argument("--" + key, required=True)
    ap.add_argument("--config", default="research/kalman_daily20/universe.json")
    a = ap.parse_args()
    run(load_spec(a.config), a.left_data, a.right_data, a.left_research,
        a.right_research, a.session, a.out)


if __name__ == "__main__":
    main()
