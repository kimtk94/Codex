"""Synthetic prospective Bear shadow contracts, no private Drive credentials."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from zipfile import ZipFile

import numpy as np
import pandas as pd

from daily20 import load_spec, market_file
from forward_shadow import chain_append, journal_bytes
from bear_forward import (
    FAMILIES, FILES, JOURNAL, REPORT, VERSION,
    add_event, read_prior_bear, run, score_bear_asof, validate_bear_events,
)
from test_forward_shadow import make_prior_zip, write_settlement_prices


def current_bull(spec, day="2026-11-20", journal=None):
    journal = list(journal or [])
    for symbol in spec["core"]:
        chain_append(journal, {
            "kind": "SIGNAL", "research_only": True,
            "signal_date": day, "symbol": symbol,
            "recorded_at_utc": "2026-11-21T01:30:00+00:00",
            "probability": 0.7, "candidate": False,
        })
    return journal


def stub_score(spec, market, features, session):
    result = {}
    for symbol in spec["core"]:
        for family in FAMILIES:
            result[(symbol, family)] = {
                "eligible": True,
                "candidate": family == "BEAR_LOGISTIC",
                "probability": 0.71 if family == "BEAR_LOGISTIC" else None,
                "shadow_only": symbol in spec["high_risk_shadow_only"],
                "feature_sha256": "a" * 64,
                "fold_status": ("OOS_BEAR_MODEL_EVALUATED" if family == "BEAR_LOGISTIC"
                                else "FROZEN_RULE_NO_FIT"),
                "bear_training_rows": 200 if family == "BEAR_LOGISTIC" else None,
                "vix_prior": 21.0, "rsi14": 36.0,
                "macd_hist": -0.01, "ret1": 0.01,
                "policy": {"id": "v1"},
            }
    return result


def make_archive_with_bear(baseline, bear, *, session="2026-11-20"):
    original = make_prior_zip(session=session, journal=baseline)
    result = {}
    with ZipFile(BytesIO(original)) as zf:
        for name in zf.namelist():
            if name != "drive_manifest.json":
                result[name] = zf.read(name)
    encoded = journal_bytes(bear)
    result[JOURNAL] = encoded
    result[REPORT] = json.dumps({
        "version": VERSION, "research_only": True,
        "live_execution": False, "approved_live": False,
        "journal_sha256": hashlib.sha256(encoded).hexdigest(),
        "signal_events": sum(e["kind"] == "SIGNAL" for e in bear),
        "settled_events": sum(e["kind"] == "SETTLED" for e in bear),
        "journal_hash_tip": bear[-1]["hash"],
    }).encode()
    for filename in FILES:
        name = "research/bear_forward/" + filename
        result.setdefault(name, b"col1,col2\nx,y\n")
    with ZipFile(BytesIO(original)) as zf:
        manifest = json.loads(zf.read("drive_manifest.json"))
    manifest["payload_hashes_sha256"] = {
        name: hashlib.sha256(value).hexdigest()
        for name, value in result.items()
    }
    memory = BytesIO()
    with ZipFile(memory, "w") as zf:
        for name, payload in result.items():
            zf.writestr(name, payload)
        zf.writestr("drive_manifest.json", json.dumps(manifest).encode())
    return memory.getvalue()


def qc_file(root, date):
    p = Path(root) / "qc.json"
    p.write_text(json.dumps({
        "status": "READY", "required": 26, "ready": 26,
        "expected_session": date,
    }))
    return p


class BearShadowContracts(unittest.TestCase):
    def test_separate_family_hash_link_and_fail_on_rewrite(self):
        spec = load_spec()
        bear = []
        bull_hash = "d" * 64
        for family in FAMILIES:
            add_event(bear, {
                "kind": "SIGNAL", "research_only": True,
                "signal_date": "2026-11-20", "symbol": "SPY",
                "family": family, "model_version": VERSION,
                "baseline_signal_hash": bull_hash,
                "candidate": False, "eligible": True,
                "probability": 0.6 if family == "BEAR_LOGISTIC" else None,
                "shadow_only": False, "feature_sha256": "a" * 64,
            })
        s, o = validate_bear_events(bear, set(spec["core"]))
        self.assertEqual(len(s), 2)
        self.assertFalse(o)
        bear[0]["probability"] = 0.01
        with self.assertRaisesRegex(RuntimeError, "BEAR_JOURNAL_HASH"):
            validate_bear_events(bear, set(spec["core"]))

    def test_two_families_all_20_capture_before_next_open(self):
        spec = load_spec()
        with TemporaryDirectory() as root:
            path = Path(root)
            bull = current_bull(spec)
            (path / "bull.jsonl").write_bytes(journal_bytes(bull))
            qc = qc_file(path, "2026-11-20")
            with patch("daily20.last_completed_nyse",
                       return_value=pd.Timestamp("2026-11-20").date()):
                report = run(spec, make_prior_zip(journal=bull),
                             path / "market", path / "features", qc,
                             path / "bull.jsonl", path / "output",
                             now=pd.Timestamp("2026-11-21T02:30:00Z"),
                             scorer=stub_score)
            self.assertEqual(report["new_signal_events"], 40)
            self.assertEqual(report["settled_events"], 0)
            self.assertEqual(report["pending_events"], 40)
            self.assertEqual(report["family"]["BEAR_LOGISTIC"]["candidates"], 20)
            self.assertEqual(report["family"]["BEAR_RULE"]["candidates"], 0)
            journal = [json.loads(t) for t in
                       (path / "output/journal.jsonl").read_text().splitlines()]
            self.assertEqual(len(journal), 40)
            self.assertEqual({e["family"] for e in journal}, set(FAMILIES))
            self.assertEqual(
                {e["baseline_signal_hash"] for e in journal},
                {e["hash"] for e in bull},
            )
            with patch("daily20.last_completed_nyse",
                       return_value=pd.Timestamp("2026-11-20").date()):
                with self.assertRaisesRegex(RuntimeError, "FIRST_SEAL_MISSED"):
                    run(spec, make_prior_zip(journal=bull),
                        path / "market", path / "features", qc,
                        path / "bull.jsonl", path / "too_late",
                        now=pd.Timestamp("2026-11-23T16:30:00Z"),
                        scorer=stub_score)

    def test_prior_mandatory_and_same_session_rescoring_rejected(self):
        spec = load_spec()
        with TemporaryDirectory() as root:
            base = Path(root)
            bull = current_bull(spec)
            (base / "bull.jsonl").write_bytes(journal_bytes(bull))
            qc = qc_file(base, "2026-11-20")
            with patch("daily20.last_completed_nyse",
                       return_value=pd.Timestamp("2026-11-20").date()):
                run(spec, make_prior_zip(journal=bull), base / "market",
                    base / "features", qc, base / "bull.jsonl", base / "first",
                    now=pd.Timestamp("2026-11-21T02:30:00Z"), scorer=stub_score)
            events = [json.loads(x) for x in
                      (base / "first/journal.jsonl").read_text().splitlines()]
            archive = make_archive_with_bear(bull, events)
            _, _, recovered = read_prior_bear(archive, set(spec["core"]))
            self.assertEqual(len(recovered), 40)
            def changed(spec, market, features, session):
                result = stub_score(spec, market, features, session)
                result[("SPY", "BEAR_LOGISTIC")]["probability"] = .98
                return result
            with patch("daily20.last_completed_nyse",
                       return_value=pd.Timestamp("2026-11-20").date()):
                with self.assertRaisesRegex(RuntimeError, "BEAR_FROZEN"):
                    path = base / "prior.zip"
                    path.write_bytes(archive)
                    run(spec, path, base / "market", base / "features", qc,
                        base / "bull.jsonl", base / "revision",
                        now=pd.Timestamp("2026-11-21T03:30:00Z"), scorer=changed)
            with self.assertRaisesRegex(RuntimeError, "BEAR_JOURNAL_BOOTSTRAP"):
                read_prior_bear(make_prior_zip(session="2026-11-23", journal=bull),
                                set(spec["core"]))

    def test_settlement_only_after_fourth_us_session(self):
        spec = load_spec()
        with TemporaryDirectory() as root:
            base = Path(root)
            bull = current_bull(spec)
            (base / "bull.jsonl").write_bytes(journal_bytes(bull))
            qc = qc_file(base, "2026-11-20")
            with patch("daily20.last_completed_nyse",
                       return_value=pd.Timestamp("2026-11-20").date()):
                run(spec, make_prior_zip(journal=bull), base / "market",
                    base / "features", qc, base / "bull.jsonl", base / "first",
                    now=pd.Timestamp("2026-11-21T02:30:00Z"), scorer=stub_score)
            events = [json.loads(x) for x in
                      (base / "first/journal.jsonl").read_text().splitlines()]
            zip_path = base / "saved.zip"
            zip_path.write_bytes(make_archive_with_bear(bull, events))
            write_settlement_prices(base / "market", spec)
            qc = qc_file(base, "2026-11-27")
            second_bull = current_bull(spec, day="2026-11-27", journal=bull)
            (base / "bull.jsonl").write_bytes(journal_bytes(second_bull))
            with patch("daily20.last_completed_nyse",
                       return_value=pd.Timestamp("2026-11-27").date()):
                report = run(spec, zip_path, base / "market", base / "features",
                             qc, base / "bull.jsonl", base / "settled",
                             now=pd.Timestamp("2026-11-27T21:30:00Z"),
                             scorer=stub_score)
            self.assertEqual(report["signal_events"], 80)
            self.assertEqual(report["new_signal_events"], 40)
            self.assertEqual(report["settled_events"], 40)
            self.assertEqual(report["pending_events"], 40)
            self.assertEqual(report["family"]["BEAR_LOGISTIC"]["matured_candidate_observations"], 20)
            observations = pd.read_csv(base / "settled/outcomes.csv")
            self.assertEqual(set(observations["exit_date"]), {"2026-11-27"})
            self.assertEqual(set(observations["family"]), set(FAMILIES))

    def test_real_feature_scoring_requires_latest_completed_session(self):
        spec = load_spec()
        index = pd.bdate_range("2026-11-17", periods=4)
        fake = pd.DataFrame(index=index)
        from train import COLUMNS
        for col in COLUMNS:
            fake[col] = 0.2
        fake["spy_above200_lag"] = 0.
        fake["vix_lag"] = 23.
        fake["rsi14"] = 40.
        fake["ret1"] = .01
        fake["macd_hist"] = [-.1, -.06, -.03, -.01]
        with patch("bear_forward.context_frame", return_value=pd.DataFrame()), \
             patch("bear_forward.feature_frame", return_value=fake), \
             patch("bear_forward.fit_bear_year",
                   return_value=(None, None, {
                       "status": "INSUFFICIENT_BEAR_TRAINING",
                       "bear_training_rows": 0,
                   })):
            rows = score_bear_asof(
                spec, "unused", "unused", str(index[-1].date()))
            self.assertEqual(len(rows), 40)
            self.assertTrue(all(rows[(s, "BEAR_RULE")]["candidate"]
                                for s in spec["core"]))
            self.assertTrue(all(not rows[(s, "BEAR_LOGISTIC")]["candidate"]
                                for s in spec["core"]))
            self.assertTrue(all(rows[(s, "BEAR_LOGISTIC")]["probability"] is None
                                for s in spec["core"]))
            with self.assertRaisesRegex(RuntimeError, "BEAR_ASOF_FEATURE_SESSION_MISMATCH"):
                score_bear_asof(spec, "unused", "unused", "2026-11-19")


if __name__ == "__main__":
    unittest.main()
