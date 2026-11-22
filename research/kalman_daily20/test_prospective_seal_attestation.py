"""Synthetic, offline 26x21/40 model/60 immutable-event first-seal contracts."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import unittest
from zipfile import ZipFile

from prospective_seal_attestation import (
    CORE, CONTEXT, COLS, FIRST_ELIGIBLE, attest_snapshot, canonical,
    fingerprint, verify_archive_prospective_seals,
)
from stability_drive_readback import verify_results_blob

SESSION = "2026-11-23"


def hash_event(event):
    return fingerprint({k: v for k, v in event.items() if k != "hash"})


def fake_prospective():
    bull_events, bear_events = [], []
    for symbol in CORE:
        prior = "0" * 64 if not bull_events else bull_events[-1]["hash"]
        b = {
            "seq": len(bull_events) + 1, "prev_hash": prior,
            "kind": "SIGNAL", "signal_date": SESSION, "symbol": symbol,
            "research_only": True, "probability": 0.62, "candidate": True,
            "source_actions_run_id": "fixture-action", "source_sha": "a" * 40,
        }
        b["hash"] = hash_event(b)
        bull_events.append(b)
        for family in ("BEAR_LOGISTIC", "BEAR_RULE"):
            previous = "0" * 64 if not bear_events else bear_events[-1]["hash"]
            e = {
                "seq": len(bear_events) + 1, "prev_hash": previous,
                "kind": "SIGNAL", "signal_date": SESSION,
                "symbol": symbol, "family": family,
                "research_only": True, "probability":
                    0.24 if family == "BEAR_LOGISTIC" else None,
                "candidate": False,
                "baseline_signal_hash": b["hash"],
                "source_actions_run_id": "fixture-action", "source_sha": "a" * 40,
            }
            e["hash"] = hash_event(e)
            bear_events.append(e)
    bull = {(SESSION, e["symbol"], "BULL_LOGISTIC"): e for e in bull_events}
    bear = {(SESSION, e["symbol"], e["family"]): e for e in bear_events}
    price = {}
    for symbol in CORE + CONTEXT:
        price[symbol] = {
            "open": 100., "high": 102., "low": 99., "close": 101.,
            "volume": 1000000.,
        }
    models = {}
    for i, symbol in enumerate(CORE):
        features = [0.1 + 0.002 * i + j * .01 for j in range(21)]
        models[symbol] = {
            "ohlcv": price[symbol],
            "feature_columns": list(COLS),
            "feature_values": features,
            "feature_sha256": fingerprint(features),
            "models": {
                "BULL_LOGISTIC": {
                    "prediction": .62, "fold_status": "VALID",
                    "training_rows": 640, "training_hash": "a" * 64,
                    "fitted_model_hash": "b" * 64,
                },
                "BEAR_LOGISTIC": {
                    "prediction": .24, "fold_status": "VALID",
                    "training_rows": 240, "training_hash": "c" * 64,
                    "fitted_model_hash": "d" * 64,
                },
            },
            "scored": {
                "BULL_LOGISTIC": {"probability": .62, "candidate": True},
                "BEAR_LOGISTIC": {"probability": .24, "candidate": False},
                "BEAR_RULE": {"probability": None, "candidate": False},
            },
            "frozen_signal_hashes": {
                family: (bull if family == "BULL_LOGISTIC" else bear)[
                    (SESSION, symbol, family)]["hash"]
                for family in ("BULL_LOGISTIC", "BEAR_LOGISTIC", "BEAR_RULE")
            },
        }
    snapshot = {
        "schema": "daily20-prospective-stability-v1",
        "session": SESSION, "research_only": True, "production_writes": False,
        "source_actions_run_id": "fixture-action",
        "source_sha": "a" * 40,
        "price_26": price, "price_26_sha256": fingerprint(price),
        "software": {"python": "3.11", "numpy": "2.3", "pandas": "2.3",
                     "scikit_learn": "1.7"},
        "models": models, "model_count": 40, "rule_count": 20,
        "feature_count": 21, "training_cutoff_exclusive": "2026-01-01",
        "source_finality_at_capture": {
            "status": "SOURCE_FINALITY_HOLD",
            "verified": 0, "required": 26, "research_hold": True,
            "evidence_sha256": "f" * 64, "provisional": True,
        },
    }
    return snapshot, bull, bear, bull_events, bear_events


def archive(snapshot, bull_events, bear_events, *, include_report=True):
    source = {
        "research/stability/snapshots/" + SESSION + ".json":
            (canonical(snapshot) + "\n").encode(),
        "research/forward_shadow/journal.jsonl":
            b"".join((canonical(e) + "\n").encode() for e in bull_events),
        "research/bear_forward/journal.jsonl":
            b"".join((canonical(e) + "\n").encode() for e in bear_events),
    }
    if include_report:
        source["research/stability/report.json"] = json.dumps({
            "version": "daily20-prospective-stability-v1",
            "session": SESSION, "research_only": True,
            "production_writes": False,
            "promotional_attribution_allowed": False,
            "strategy_promoted": False, "research_hold": True,
            "status": "SOURCE_FINALITY_HOLD",
            "frozen_sessions_preserved": 1,
            "current_session_has_original_snapshot": True,
            "new_sealed_bull_signals": 20,
            "frozen_snapshot_sha256": sha256(
                source["research/stability/snapshots/" + SESSION + ".json"]
            ).hexdigest(),
        }).encode()
    manifest = {
        "format": "kalman-daily20-drive-v1",
        "research_only": True, "production_writes": False,
        "oos_score_count": 20,
        "data_expected_last_closed_xnys": SESSION,
        "stability_status": "SOURCE_FINALITY_HOLD",
        "stability_research_hold": True,
        "payload_hashes_sha256": {key: sha256(value).hexdigest()
                                  for key, value in source.items()},
    }
    buf = BytesIO()
    with ZipFile(buf, "w") as z:
        for key, value in source.items():
            z.writestr(key, value)
        z.writestr("drive_manifest.json", json.dumps(manifest))
    return buf.getvalue()


class FirstProspectiveSealTests(unittest.TestCase):
    def setUp(self):
        self.doc, self.bull, self.bear, self.bull_events, self.bear_events = fake_prospective()

    def check(self):
        return attest_snapshot(self.doc, SESSION, self.bull, self.bear)

    def test_complete_26_20x21_40_models_60_event_links(self):
        result = self.check()
        self.assertEqual(result["core_feature_rows_verified"], 20)
        self.assertEqual(result["model_input_fingerprints_verified"], 40)
        self.assertEqual(result["original_signal_hash_count"], 60)
        self.assertEqual(result["source_actions_run_id"], "fixture-action")

    def test_readback_end_to_end_first_seal_passes(self):
        blob = archive(self.doc, self.bull_events, self.bear_events)
        result = verify_results_blob(blob)
        self.assertEqual(result["prospective_seals_deep_verified"], 1)
        self.assertEqual(result["prospective_first_seal_status"],
                         "NEW_SESSION_ORIGINAL_INPUTS_AND_EVENTS_ATTESTED_RESEARCH_HOLD")
        self.assertTrue(result["research_hold"])

    def test_readback_rejects_rewritten_feature_even_resigned_zip(self):
        self.doc["models"]["SPY"]["feature_values"][0] += 1
        blob = archive(self.doc, self.bull_events, self.bear_events)
        with self.assertRaisesRegex(RuntimeError, "FEATURE_21_VALUES_OR_HASH_INVALID"):
            verify_results_blob(blob)

    def test_readback_rejects_rewritten_ohlcv_even_resigned_zip(self):
        self.doc["price_26"]["QQQ"]["close"] += 1
        blob = archive(self.doc, self.bull_events, self.bear_events)
        with self.assertRaisesRegex(RuntimeError, "26_PRICE_DIGEST_OR_SYMBOL_COVERAGE"):
            verify_results_blob(blob)

    def test_readback_rejects_original_event_anchoring_drift(self):
        self.doc["models"]["SPY"]["frozen_signal_hashes"]["BULL_LOGISTIC"] = "a" * 64
        with self.assertRaisesRegex(RuntimeError, "ORIGINAL_EVENT_HASH_ANCHOR_MISMATCH"):
            self.check()

    def test_readback_rejects_faked_journal_hash_even_resigned_zip(self):
        self.bull_events[0]["probability"] = .85
        blob = archive(self.doc, self.bull_events, self.bear_events)
        with self.assertRaisesRegex(RuntimeError, "ORIGINAL_JOURNAL_HASH_CHAIN_BROKEN"):
            verify_results_blob(blob)

    def test_readback_rejects_changed_original_prob_if_anchor_regenerated(self):
        event = self.bull_events[0]
        event["candidate"] = False
        event["hash"] = hash_event(event)
        for i in range(1, len(self.bull_events)):
            self.bull_events[i]["prev_hash"] = self.bull_events[i-1]["hash"]
            self.bull_events[i]["hash"] = hash_event(self.bull_events[i])
        self.doc["models"]["SPY"]["frozen_signal_hashes"]["BULL_LOGISTIC"] = event["hash"]
        blob = archive(self.doc, self.bull_events, self.bear_events)
        with self.assertRaisesRegex(RuntimeError, "SCORING_AND_ORIGINAL_EVENT_CONFLICT"):
            verify_results_blob(blob)

    def test_model_digest_missing_is_rejected(self):
        self.doc["models"]["SPY"]["models"]["BULL_LOGISTIC"]["fitted_model_hash"] = None
        with self.assertRaisesRegex(RuntimeError, "TRAINING_OR_FITTED_MODEL_DIGEST_INVALID"):
            self.check()

    def test_model_training_hash_missing_is_rejected(self):
        self.doc["models"]["SPY"]["models"]["BEAR_LOGISTIC"]["training_hash"] = None
        with self.assertRaisesRegex(RuntimeError, "TRAINING_OR_FITTED_MODEL_DIGEST_INVALID"):
            self.check()

    def test_bear_unavailable_model_with_null_hash_is_legitimate(self):
        m = self.doc["models"]["SPY"]["models"]["BEAR_LOGISTIC"]
        m.update({"prediction": None, "fitted_model_hash": None, "fold_status": "NO_TRAIN"})
        self.doc["models"]["SPY"]["scored"]["BEAR_LOGISTIC"]["probability"] = None
        self.bear[(SESSION, "SPY", "BEAR_LOGISTIC")]["probability"] = None
        self.check()

    def test_initial_bear_event_must_match_original_bull_anchor(self):
        self.bear[(SESSION, "SPY", "BEAR_LOGISTIC")]["baseline_signal_hash"] = "b" * 64
        with self.assertRaisesRegex(RuntimeError, "BEAR_EVENT_BULL_BASELINE_LINK_MISMATCH"):
            self.check()

    def test_event_capture_run_must_match_first_frozen_model_run(self):
        self.bear[(SESSION, "SPY", "BEAR_RULE")]["source_actions_run_id"] = "wrong-run"
        with self.assertRaisesRegex(RuntimeError, "ORIGINAL_EVENT_CAPTURE_RUN_MISMATCH"):
            self.check()

    def test_wrong_feature_column_order_rejected(self):
        self.doc["models"]["SPY"]["feature_columns"].reverse()
        with self.assertRaisesRegex(RuntimeError, "FEATURE_21_VALUES_OR_HASH_INVALID"):
            self.check()

    def test_missing_environment_provenance_rejected(self):
        self.doc["software"]["scikit_learn"] = None
        with self.assertRaisesRegex(RuntimeError, "ORIGINAL_ENVIRONMENT_MISSING"):
            self.check()

    def test_false_finality_certification_rejected(self):
        self.doc["source_finality_at_capture"]["verified"] = 26
        with self.assertRaisesRegex(RuntimeError, "SOURCE_FINALITY_AT_FIRST_SEAL_NOT_HOLD"):
            self.check()

    def test_false_backward_seal_is_not_prospectively_attested(self):
        with ZipFile(BytesIO(archive(self.doc, self.bull_events, self.bear_events))) as z:
            result = verify_archive_prospective_seals(z, z.namelist(), ["2026-11-20"])
            self.assertEqual(result["prospective_seals_attested"], 0)
            self.assertEqual(result["status"], "AWAITING_GENUINE_NEW_SESSION")

    def test_unclosed_price_candle_rejected(self):
        self.doc["price_26"]["SPY"]["high"] = 100
        self.doc["price_26_sha256"] = fingerprint(self.doc["price_26"])
        with self.assertRaisesRegex(RuntimeError, "PRICE_OHLCV_RELATION_INVALID"):
            self.check()


if __name__ == "__main__":
    unittest.main()
