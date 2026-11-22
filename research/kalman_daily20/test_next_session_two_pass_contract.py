"""Offline preflight / postflight contracts for the first real XNYS session.

Fixtures use signed SYNTHETIC 2026-11-23 events; no journal is published or
promoted from a test. The protected main run reuses original Drive archives.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forward_shadow import journal_bytes
from prospective_seal_attestation import CORE
from test_prospective_seal_attestation import fake_prospective
from next_session_two_pass_contract import (
    VERSION, BEAR_JOURNAL, BULL_JOURNAL, SNAP_PREFIX,
    decide, postflight,
)

SESSION = "2026-11-23"
RUN = "fixture-action"
CHECK_TIME = "2026-11-24T02:40:00+00:00"


def prior_stub():
    return {
        "prior_manifest_session": "2026-11-20",
        "prior_actions_run_id": "old-archive-run",
        "prior_bull_journal_sha256": sha256(b"").hexdigest(),
        "prior_bear_journal_sha256": sha256(b"").hexdigest(),
        "prior_bull_journal_bytes": 0,
        "prior_bear_journal_bytes": 0,
        "prior_bull_signal_events": 0,
        "prior_bear_signal_events": 0,
        "prior_bull_settled_events": 0,
        "prior_bear_settled_events": 0,
        "frozen_snapshot_sha256": {},
        "existing_bull_sessions": [],
        "existing_bear_sessions": [],
        "current_prior_bull_keys": {},
        "current_prior_bear_keys": {},
        "prior_raw": {BULL_JOURNAL: b"", BEAR_JOURNAL: b""},
    }


def test_file_fixture(root, *, bull_override=None, bear_override=None):
    root = Path(root)
    bull, bear, stability = (root / "bull", root / "bear",
                             root / "stability")
    for path in (bull, bear, stability / "snapshots"):
        path.mkdir(parents=True, exist_ok=True)
    snapshot, _, _, bull_events, bear_events = fake_prospective()
    b_raw = (bull_override if bull_override is not None
             else journal_bytes(bull_events))
    br_raw = (bear_override if bear_override is not None
              else journal_bytes(bear_events))
    (bull / "journal.jsonl").write_bytes(b_raw)
    (bear / "journal.jsonl").write_bytes(br_raw)
    snap_raw = json.dumps(snapshot, sort_keys=True,
                          separators=(",", ":")).encode() + b"\n"
    (stability / "snapshots" / (SESSION + ".json")).write_bytes(snap_raw)
    (bull / "report.json").write_text(json.dumps({
        "last_completed_session": SESSION, "source_run_id": RUN,
        "new_signal_events": 20,
    }))
    (bear / "report.json").write_text(json.dumps({
        "last_completed_session": SESSION, "source_run_id": RUN,
        "new_signal_events": 40,
    }))
    (stability / "report.json").write_text(json.dumps({
        "session": SESSION, "new_sealed_bull_signals": 20,
        "new_sealed_bear_signals": 40,
        "research_only": True, "strategy_promoted": False,
        "source_finality_verified_assets": 0, "research_hold": True,
        "frozen_snapshot_sha256": sha256(snap_raw).hexdigest(),
        "incidents_count": 0,
    }))
    return bull, bear, stability


class TwoPassContractTests(unittest.TestCase):
    def test_nov23_new_first_seal_calendar_real_clock(self):
        p = decide(CORE, prior_stub(), SESSION, clock=CHECK_TIME)
        self.assertEqual(p["mode"], "FIRST_GENUINE_SEAL_EXPECTED")
        self.assertEqual((p["expected_new_bull"], p["expected_new_bear"]),
                         (20, 40))
        self.assertFalse(p["price_certified"])
        self.assertTrue(p["scheduled_admission_open"])

    def test_nov23_second_pass_existing_complete_seal(self):
        prior = prior_stub()
        prior["current_prior_bull_keys"] = {
            (SESSION, s): {} for s in CORE
        }
        prior["current_prior_bear_keys"] = {
            (SESSION, s, fam): {}
            for s in CORE for fam in ("BEAR_LOGISTIC", "BEAR_RULE")
        }
        prior["frozen_snapshot_sha256"] = {
            SNAP_PREFIX + SESSION + ".json": "a" * 64}
        p = decide(CORE, prior, SESSION,
                   clock="2026-11-24T04:40:00+00:00")
        self.assertEqual(p["mode"], "SAME_SESSION_REPLAY_EXPECTED")
        self.assertEqual(p["expected_new_bull"] + p["expected_new_bear"], 0)
        self.assertEqual(p["prior_original_snapshot_sha256"], "a" * 64)

    def test_after_following_open_missed_window_marked_hold(self):
        p = decide(CORE, prior_stub(), SESSION,
                   clock="2026-11-24T17:00:00+00:00")
        self.assertEqual(p["mode"], "FIRST_SEAL_WINDOW_MISSED_HOLD")
        self.assertEqual(p["expected_new_bull"], 0)

    def test_legacy_nov20_does_not_invent_first_snapshot(self):
        old = prior_stub()
        old["current_prior_bull_keys"] = {
            ("2026-11-20", s): {} for s in CORE}
        old["current_prior_bear_keys"] = {
            ("2026-11-20", s, fam): {}
            for s in CORE for fam in ("BEAR_LOGISTIC", "BEAR_RULE")
        }
        p = decide(CORE, old, "2026-11-20",
                   clock="2026-11-21T02:40:00+00:00")
        self.assertEqual(p["mode"],
                         "LEGACY_REPLAY_NO_20261120_ORIGINAL_FEATURES_HOLD")
        self.assertEqual(p["expected_new_bull"], 0)

    def test_old_archive_from_future_rejected(self):
        old = prior_stub()
        old["prior_manifest_session"] = "2026-11-24"
        with self.assertRaisesRegex(RuntimeError, "PRIOR_ARCHIVE_FROM_FUTURE"):
            decide(CORE, old, SESSION, clock=CHECK_TIME)

    def test_partial_prior_bull_fails(self):
        old = prior_stub()
        old["current_prior_bull_keys"][(SESSION, CORE[0])] = {}
        with self.assertRaisesRegex(RuntimeError, "PRIOR_PARTIAL_COHORT"):
            decide(CORE, old, SESSION, clock=CHECK_TIME)

    def test_partial_prior_bear_fails(self):
        old = prior_stub()
        old["current_prior_bear_keys"][(SESSION, CORE[0], "BEAR_LOGISTIC")] = {}
        with self.assertRaisesRegex(RuntimeError, "PRIOR_PARTIAL_COHORT"):
            decide(CORE, old, SESSION, clock=CHECK_TIME)

    def test_inconsistent_full_bull_no_bear_rejected(self):
        old = prior_stub()
        old["current_prior_bull_keys"] = {
            (SESSION, s): {} for s in CORE}
        with self.assertRaisesRegex(RuntimeError, "PRIOR_BULL_BEAR_SEAL_DISAGREEMENT"):
            decide(CORE, old, SESSION, clock=CHECK_TIME)

    def test_preflight_wrong_market_asof_rejected(self):
        with self.assertRaisesRegex(RuntimeError,
                                    "NOT_LATEST_FULLY_CLOSED_XNYS_SESSION"):
            decide(CORE, prior_stub(), SESSION,
                   clock="2026-11-22T02:40:00+00:00")

    def test_first_seal_all_60_signed_event_and_snapshot_checks(self):
        p = decide(CORE, prior_stub(), SESSION, clock=CHECK_TIME)
        with TemporaryDirectory() as tmp:
            dirs = test_file_fixture(tmp)
            proof = postflight(p, prior_stub(), CORE, *dirs, run_id=RUN)
        self.assertTrue(proof["journal_prefix_byte_identical"])
        self.assertTrue(proof["full_26_price_420_feature_40_model_60_event_attested"])
        self.assertEqual(proof["bull_new"], 20)
        self.assertEqual(proof["bear_new"], 40)
        self.assertFalse(proof["full_raw_market_close_certified"])
        self.assertTrue(proof["research_hold"])

    def test_prior_journal_byte_prefix_rewritten_rejected(self):
        p = decide(CORE, prior_stub(), SESSION, clock=CHECK_TIME)
        previous = prior_stub()
        previous["prior_raw"][BULL_JOURNAL] = b"previous-journal-must-survive\n"
        with TemporaryDirectory() as tmp:
            dirs = test_file_fixture(tmp)
            with self.assertRaisesRegex(RuntimeError, "PRIOR_JOURNAL_BYTES_NOT_PREFIX"):
                postflight(p, previous, CORE, *dirs, run_id=RUN)

    def test_partial_added_cohort_fails_even_if_signed(self):
        p = decide(CORE, prior_stub(), SESSION, clock=CHECK_TIME)
        with TemporaryDirectory() as tmp:
            dirs = test_file_fixture(tmp)
            bear = dirs[1]
            report = json.loads((bear / "report.json").read_text())
            report["new_signal_events"] = 20
            (bear / "report.json").write_text(json.dumps(report))
            with self.assertRaisesRegex(RuntimeError, "POSTFLIGHT_NEW_SIGNAL_COUNT"):
                postflight(p, prior_stub(), CORE, *dirs, run_id=RUN)

    def test_wrong_source_run_fails(self):
        p = decide(CORE, prior_stub(), SESSION, clock=CHECK_TIME)
        with TemporaryDirectory() as tmp:
            dirs = test_file_fixture(tmp)
            with self.assertRaisesRegex(RuntimeError, "POSTFLIGHT_RUN_ID_WRONG"):
                postflight(p, prior_stub(), CORE, *dirs, run_id="other-actions-run")

    def test_bad_original_snapshot_bytes_rejected(self):
        p = decide(CORE, prior_stub(), SESSION, clock=CHECK_TIME)
        with TemporaryDirectory() as tmp:
            dirs = test_file_fixture(tmp)
            frozen = dirs[2] / "snapshots" / (SESSION + ".json")
            frozen.write_bytes(frozen.read_bytes() + b"tamper")
            with self.assertRaisesRegex(RuntimeError, "FIRST_SEAL_SNAPSHOT_MISSING"):
                postflight(p, prior_stub(), CORE, *dirs, run_id=RUN)

    def test_false_live_promotion_rejected(self):
        p = decide(CORE, prior_stub(), SESSION, clock=CHECK_TIME)
        with TemporaryDirectory() as tmp:
            dirs = test_file_fixture(tmp)
            path = dirs[2] / "report.json"
            report = json.loads(path.read_text())
            report["strategy_promoted"] = True
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(RuntimeError, "POSTFLIGHT_FALSE_SCIENTIFIC_PROMOTION"):
                postflight(p, prior_stub(), CORE, *dirs, run_id=RUN)


if __name__ == "__main__":
    unittest.main()
