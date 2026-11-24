#!/usr/bin/env python3
"""PR-only first-seal contract rehearsal with REAL archived OHLCV/features.

Twenty Bull and forty Bear/Rule EVENT HASHES are made in memory solely for
this rehearsal. They are synthetic and MUST NEVER be published as prospective
journal evidence or as a real first-seal snapshot. Model fitting and as-of
feature computation use the real current CI source data.
"""
from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

from daily20 import load_spec, write_json
from forward_shadow import chain_append, journal_bytes, read_score_rows
from bear_forward import add_event
from prospective_seal_attestation import (
    _event_index, attest_snapshot, fingerprint,
)
from stability_gate import make_current_snapshot
from stability_replay_fixture import fake_anchor

VERSION = "daily20-real-input-synthetic-seal-rehearsal-v1"
FAMILIES = ("BULL_LOGISTIC", "BEAR_LOGISTIC", "BEAR_RULE")


def _lookup_stub(spec, session):
    bull = {
        (session, symbol): {
            "hash": fake_anchor(symbol, "BULL_LOGISTIC", session)
        } for symbol in spec["core"]
    }
    bear = {
        (session, symbol, family): {
            "hash": fake_anchor(symbol, family, session)
        }
        for symbol in spec["core"] for family in FAMILIES[1:]
    }
    return bull, bear


def make_test_journals(spec, original, session):
    """Use the repository's REAL event_hash/chain_append implementations."""
    bulls, bears = [], []
    source_run = original["source_actions_run_id"]
    source_sha = original["source_sha"]
    for symbol in spec["core"]:
        row = original["models"][symbol]
        b = row["scored"]["BULL_LOGISTIC"]
        anchor = chain_append(bulls, {
            "kind": "SIGNAL", "research_only": True, "signal_date": session,
            "symbol": symbol,
            "source_actions_run_id": source_run,
            "source_sha": source_sha,
            "recorded_at_utc": "2026-11-21T01:30:00+00:00",
            "probability": b["probability"], "candidate": b["candidate"],
            "shadow_only": symbol in spec["high_risk_shadow_only"],
            "synthetic_test_event_never_tradable": True,
        })
        for family in FAMILIES[1:]:
            scored = row["scored"][family]
            add_event(bears, {
                "kind": "SIGNAL", "research_only": True, "signal_date": session,
                "symbol": symbol, "family": family,
                "source_actions_run_id": source_run,
                "source_sha": source_sha,
                "recorded_at_utc": "2026-11-21T01:30:00+00:00",
                "baseline_signal_hash": anchor["hash"],
                "probability": scored["probability"],
                "candidate": scored["candidate"],
                "feature_sha256": row["feature_sha256"],
                "synthetic_test_event_never_tradable": True,
            })
    if len(bulls) != 20 or len(bears) != 40:
        raise RuntimeError("REHEARSAL_PARTIAL_TEST_EVENT_SET")
    return bulls, bears


def rehearse(spec, market_root, features_root, scores_path, session):
    if len(spec["core"]) != 20 or len(spec["context"]) != 6:
        raise RuntimeError("REHEARSAL_UNIVERSE_INCOMPLETE")
    scores = read_score_rows(scores_path, spec, session)
    fake_bull, fake_bear = _lookup_stub(spec, session)
    # This first computation is only to calculate actual (not invented) first
    # day's 26 price bars and the 20 independently fitted model score rows.
    observed = make_current_snapshot(
        spec, market_root, features_root, scores, session, fake_bull, fake_bear,
    )
    bull_events, bear_events = make_test_journals(spec, observed, session)
    temporary = BytesIO()
    with ZipFile(temporary, "w") as z:
        z.writestr("research/forward_shadow/journal.jsonl", journal_bytes(bull_events))
        z.writestr("research/bear_forward/journal.jsonl", journal_bytes(bear_events))
    # Parse and authenticate the full hash chain, not just 60 event hashes.
    with ZipFile(BytesIO(temporary.getvalue())) as z:
        bull = _event_index(z, z.namelist(),
                            "research/forward_shadow/journal.jsonl", "BULL")
        bear = _event_index(z, z.namelist(),
                            "research/bear_forward/journal.jsonl", "BEAR")
    snapshot = make_current_snapshot(
        spec, market_root, features_root, scores, session,
        {(d, s): event for (d, s, _), event in bull.items()},
        bear,
    )
    snapshot["source_finality_at_capture"] = {
        "status": "SOURCE_FINALITY_HOLD", "required": 26,
        "verified": 0, "research_hold": True, "provisional": True,
        "evidence_sha256": fingerprint({
            "source": "SYNTHETIC_REHEARSAL_ONLY_NO_OFFICIAL_CLOSE_PROOF",
            "session": session,
        }),
    }
    # Reject a result that changed its underlying actual daily OHLCV, technical
    # feature values or model predictions during event-fingerprint binding.
    for field in ("price_26", "price_26_sha256", "software",
                  "training_cutoff_exclusive"):
        if observed[field] != snapshot[field]:
            raise RuntimeError("REHEARSAL_RECOMPUTED_INPUT_NOT_STABLE:" + field)
    for symbol in spec["core"]:
        left, right = observed["models"][symbol], snapshot["models"][symbol]
        for field in ("ohlcv", "feature_columns", "feature_values",
                      "feature_sha256", "models", "scored"):
            if left[field] != right[field]:
                raise RuntimeError(
                    "REHEARSAL_RECOMPUTED_MODEL_NOT_STABLE:"
                    + symbol + ":" + field
                )
    proof = attest_snapshot(snapshot, session, bull, bear)
    if (proof["original_signal_hash_count"] != 60 or
        proof["core_feature_rows_verified"] != 20 or
        proof["model_input_fingerprints_verified"] != 40 or
        proof["price_26_sha256"] != observed["price_26_sha256"]):
        raise RuntimeError("REHEARSAL_INCOMPLETE_REAL_INPUT_PROOF")
    return {
        "version": VERSION,
        "status": "REAL_INPUT_SYNTHETIC_EVENT_CONTRACT_PASS",
        "session": session,
        "research_only": True,
        "historical_real_price_and_feature_values": True,
        "synthetic_event_hashes_only": True,
        "synthetic_events_written_to_drive": False,
        "prospective_first_seal_claimed": False,
        "official_close_certified": False,
        "live_execution": False,
        "production_writes": False,
        "strategy_promoted": False,
        "price_assets_verified": len(observed["price_26"]),
        "core_real_feature_vectors_verified": 20,
        "feature_values_verified": 20 * len(next(iter(
            observed["models"].values()))["feature_values"]),
        "real_model_fit_provenance_verified": 40,
        "synthetic_event_anchor_count": proof["original_signal_hash_count"],
        "models_and_features_stable_on_two_recomputations": True,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="research/kalman_daily20/universe.json")
    p.add_argument("--data-root", required=True)
    p.add_argument("--scores", required=True)
    p.add_argument("--qc", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    qc = json.loads(Path(args.qc).read_text())
    session = str(qc.get("expected_session"))
    if (qc.get("ready") != 26 or qc.get("required") != 26
            or qc.get("status") != "READY"
            or not isinstance(qc.get("expected_session"), str)):
        raise RuntimeError("REHEARSAL_CURRENT_DATA_QC_NOT_READY")
    root = Path(args.data_root)
    result = rehearse(
        load_spec(args.config), root / "market", root / "features",
        args.scores, session,
    )
    write_json(args.out, result)
    print(json.dumps({"DAILY20_REAL_INPUT_SEAL_REHEARSAL": result}))


if __name__ == "__main__":
    main()
