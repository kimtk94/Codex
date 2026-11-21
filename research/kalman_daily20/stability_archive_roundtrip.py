#!/usr/bin/env python3
"""No-credentials, actual-data Daily20 freeze -> signed ZIP -> replay HOLD proof.

The forecast journals and prior archive are synthetic TEST fixtures derived
from immutable archived real market/technical/model-score outputs. NEVER feed
these test events back to a prospective Drive archive or live trading.
"""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from bear_forward import VERSION as BEAR_VERSION, add_event
from daily20 import load_spec, write_json
from forward_shadow import chain_append, journal_bytes, read_score_rows
from publish_drive import build_zip
from stability_gate import (
    _historical_snapshots, make_current_snapshot, run as run_stability,
)
from stability_replay_fixture import source_paths, fake_anchor
from test_forward_shadow import make_prior_zip

VERSION = "daily20-signed-zip-stability-roundtrip-fixture-v1"
SESSION = "2026-11-20"


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def output_journals(spec, first_market, first_ta, first_scores, root):
    # Initial synthetic identifiers allow computing real model results; they
    # are placeholders only, never emitted into an actual trading journal.
    fake_bull = {(SESSION, s): {
        "hash": fake_anchor(s, "BULL_LOGISTIC", SESSION)}
        for s in spec["core"]}
    fake_bear = {(SESSION, s, f): {
        "hash": fake_anchor(s, f, SESSION)}
        for s in spec["core"] for f in ("BEAR_LOGISTIC", "BEAR_RULE")}
    current = make_current_snapshot(
        spec, first_market, first_ta, first_scores, SESSION, fake_bull, fake_bear,
    )
    bulls, bears = [], []
    for s in spec["core"]:
        b = current["models"][s]["scored"]["BULL_LOGISTIC"]
        event = chain_append(bulls, {
            "kind": "SIGNAL", "research_only": True,
            "signal_date": SESSION, "symbol": s,
            "recorded_at_utc": "2026-11-21T01:30:00Z",
            "probability": b["probability"], "candidate": b["candidate"],
        })
        for f in ("BEAR_LOGISTIC", "BEAR_RULE"):
            r = current["models"][s]["scored"][f]
            add_event(bears, {
                "kind": "SIGNAL", "research_only": True,
                "signal_date": SESSION, "symbol": s, "family": f,
                "baseline_signal_hash": event["hash"],
                "model_version": BEAR_VERSION,
                "recorded_at_utc": "2026-11-21T01:30:00Z",
                "candidate": r["candidate"],
                "eligible": True,  # fixture only; not a real eligibility seal
                "probability": r["probability"],
                "shadow_only": s in spec["high_risk_shadow_only"],
                "feature_sha256": current["models"][s]["feature_sha256"],
            })
    (root / "bull.jsonl").write_bytes(journal_bytes(bulls))
    (root / "bear.jsonl").write_bytes(journal_bytes(bears))
    return bulls, bears


def prepared_reports(root, new_bull, new_bear):
    (root / "bull_report.json").write_text(json.dumps({
        "last_completed_session": SESSION, "new_signal_events": new_bull,
    }))
    (root / "bear_report.json").write_text(json.dumps({
        "last_completed_session": SESSION, "new_signal_events": new_bear,
    }))


def make_fixture_signed_results_zip(original_bull, snapshot_dir, out_zip):
    # The same publisher ZIP writer and same prior-manifest reader are used
    # in production, but this directory contains only TEST events and files.
    seed = make_prior_zip(journal=original_bull)
    tmp = out_zip.parent / "fixture_payload"
    tmp.mkdir(parents=True, exist_ok=True)
    with ZipFile(BytesIO(seed)) as z:
        manifest = json.loads(z.read("drive_manifest.json"))
        for name in z.namelist():
            if name == "drive_manifest.json":
                continue
            p = tmp / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(z.read(name))
    for p in (snapshot_dir / "snapshots").glob("*.json"):
        q = tmp / "research/stability/snapshots" / p.name
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_bytes(p.read_bytes())
    (tmp / "research/stability/report.json").write_bytes(
        (snapshot_dir / "report.json").read_bytes()
    )
    return build_zip(tmp, out_zip,
        {k: v for k, v in manifest.items()
         if k != "payload_hashes_sha256"})


def validate_tamper_rejection(zip_bytes, spec):
    with ZipFile(BytesIO(zip_bytes)) as z:
        names = z.namelist()
        source = {name: z.read(name) for name in names}
    key = "research/stability/snapshots/" + SESSION + ".json"
    original = source[key]
    source[key] = original.replace(b'"research_only":true',
                                   b'"research_only":false', 1)
    if source[key] == original:
        raise RuntimeError("SIGNED_FIXTURE_TAMPER_SIMULATION_NO_CHANGE")
    altered = BytesIO()
    with ZipFile(altered, "w") as z:
        for name in names:
            z.writestr(name, source[name])
    try:
        _historical_snapshots(altered.getvalue(), spec)
    except RuntimeError as error:
        if "PRIOR_RESEARCH_HASH_MISMATCH" not in str(error):
            raise
        return True
    raise RuntimeError("UNSIGNED_SNAPSHOT_TAMPER_ACCEPTED")


def run(spec, left_data, right_data, left_research, right_research, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    lm, lf = source_paths(left_data)
    rm, rf = source_paths(right_data)
    score1 = Path(left_research) / "research/latest_research_scores.csv"
    score2 = Path(right_research) / "research/latest_research_scores.csv"
    scores = read_score_rows(score1, spec, SESSION)
    with TemporaryDirectory() as temp:
        p = Path(temp)
        bulls, bears = output_journals(spec, lm, lf, scores, p)
        if len(bulls) != 20 or len(bears) != 40:
            raise RuntimeError("INCOMPLETE_SYNTHETIC_EVENT_TEST_FIXTURE")

        first_prior = p / "prior_empty.zip"
        first_prior.write_bytes(make_prior_zip())
        prepared_reports(p, 20, 40)
        first = run_stability(
            spec, first_prior, lm, lf, score1,
            p / "bull.jsonl", p / "bear.jsonl",
            p / "bull_report.json", p / "bear_report.json", p / "first",
        )
        if first["status"] != "SEALED_NEW_SESSION" or first["research_hold"]:
            raise RuntimeError("FIRST_REAL_DATA_FIXTURE_SEAL_FAILED")
        original = (p / "first/snapshots" / (SESSION + ".json")).read_bytes()
        frozen = json.loads(original)
        if len(frozen["price_26"]) != 26 or len(frozen["models"]) != 20:
            raise RuntimeError("FIRST_REAL_DATA_FEATURE_COUNT_WRONG")
        signed_zip = make_fixture_signed_results_zip(
            bulls, p / "first", p / "frozen_results_fixture.zip",
        )
        if _historical_snapshots(signed_zip.read_bytes(), spec)[SESSION] != original:
            raise RuntimeError("SIGNED_ZIP_FIRST_READBACK_BYTES_DIFFER")
        validate_tamper_rejection(signed_zip.read_bytes(), spec)

        prepared_reports(p, 0, 0)
        second = run_stability(
            spec, signed_zip, rm, rf, score2,
            p / "bull.jsonl", p / "bear.jsonl",
            p / "bull_report.json", p / "bear_report.json", p / "replay",
        )
        replayed = (p / "replay/snapshots" / (SESSION + ".json")).read_bytes()
        if replayed != original:
            raise RuntimeError("REPLAY_MUTATED_FROZEN_SNAPSHOT")
        if second["status"] != "REPLAY_DRIFT_RESEARCH_HOLD" or not second["research_hold"]:
            raise RuntimeError("REPLAY_DID_NOT_HOLD_MATERIAL_REAL_DATA_DRIFT")
        if not any(e["symbol"] == "SPY" and e["family"] == "BULL_LOGISTIC"
                   and e["research_hold"] for e in second["incidents"]):
            raise RuntimeError("MISSING_SPY_BULL_HOLD_AFTER_SIGNED_ZIP_REPLAY")

        # Copy the same old snapshot and repackage, as the real Daily20
        # publisher would, but only into a short-lived GH Actions artifact.
        second_zip = make_fixture_signed_results_zip(
            bulls, p / "replay", p / "replayed_results_fixture.zip",
        )
        restored = _historical_snapshots(second_zip.read_bytes(), spec)[SESSION]
        if restored != original:
            raise RuntimeError("SECOND_SIGNED_ZIP_MODIFIED_ORIGINAL_SNAPSHOT")
        report = {
            "version": VERSION, "status": "SIGNED_ZIP_ROUNDTRIP_PASS",
            "source_session": SESSION,
            "real_ohlcv_and_features": True,
            "synthetic_events_only": True,
            "actual_drive_credentials_used": False,
            "production_drive_writes": False,
            "live_execution": False,
            "strategy_promoted": False,
            "frozen_26_ohlcv": len(frozen["price_26"]),
            "frozen_core_assets": len(frozen["models"]),
            "frozen_21_features_per_asset": frozen["feature_count"],
            "frozen_models": frozen["model_count"],
            "bear_rule_assets": frozen["rule_count"],
            "initial_snapshot_sha256": sha(original),
            "first_zip_restore_sha256": sha(_historical_snapshots(
                signed_zip.read_bytes(), spec)[SESSION]),
            "second_zip_restore_sha256": sha(restored),
            "tamper_rejected": True,
            "replay_status": second["status"],
            "replay_hold_count": sum(e["research_hold"] for e in second["incidents"]),
            "replay_incidents": len(second["incidents"]),
        }
    write_json(out / "signed_zip_roundtrip.json", report)
    print(json.dumps({"DAILY20_SIGNED_ZIP_FIXTURE": report}))
    return report


def main():
    ap = argparse.ArgumentParser()
    for key in ("left-data", "right-data", "left-research", "right-research", "out"):
        ap.add_argument("--" + key, required=True)
    ap.add_argument("--config", default="research/kalman_daily20/universe.json")
    a = ap.parse_args()
    run(load_spec(a.config), a.left_data, a.right_data,
        a.left_research, a.right_research, a.out)


if __name__ == "__main__":
    main()
