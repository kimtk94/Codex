"""Forward-only as-of seals, prior Drive integrity, and delayed settlements."""
import json
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from zipfile import ZipFile
import hashlib

import numpy as np
import pandas as pd

from daily20 import load_spec, market_file
from forward_shadow import (VERSION, chain_append, check_events,
                            check_signal_admission, event_hash, journal_bytes,
                            read_score_rows, run, validate_prior_results_archive)


def make_prior_zip(*, session="2026-11-20", journal=None, report=None):
    members = {
        "qc.json": json.dumps({"expected_session": session, "ready": 26}),
        "research/summary.json": json.dumps({"latest_score_count": 20}),
        "research/latest_research_scores.csv": "symbol,signal_after_close\nSPY,2026-11-20\n",
    }
    if journal is not None:
        body = journal_bytes(journal)
        members["research/forward_shadow/journal.jsonl"] = body
        members["research/forward_shadow/report.json"] = json.dumps({
            "version": VERSION, "research_only": True,
            "journal_sha256": hashlib.sha256(body).hexdigest(),
        }) if report is None else json.dumps(report)
    hashes = {}
    buff = BytesIO()
    with ZipFile(buff, "w") as archive:
        for path, payload in members.items():
            data = payload.encode() if isinstance(payload, str) else payload
            hashes[path] = hashlib.sha256(data).hexdigest()
            archive.writestr(path, data)
        archive.writestr("drive_manifest.json", json.dumps({
            "format": "kalman-daily20-drive-v1",
            "research_only": True, "production_writes": False,
            "oos_score_count": 20,
            "data_expected_last_closed_xnys": session,
            "source_actions_run_id": "older-run",
            "payload_hashes_sha256": hashes,
        }))
    return buff.getvalue()


def write_score_and_qc(root, spec, day, *, tamper_symbol=None):
    root = Path(root)
    rows = []
    for i, symbol in enumerate(spec["core"]):
        prob = .7 if i % 2 else .4
        if tamper_symbol == symbol:
            prob = .45
        rows.append({
            "symbol": symbol, "signal_after_close": day,
            "logistic_prob_positive_net": prob,
            "research_candidate": prob >= .6,
            "not_order": True,
            "shadow_only": symbol in spec["high_risk_shadow_only"],
        })
    pd.DataFrame(rows).to_csv(root / "scores.csv", index=False)
    (root / "qc.json").write_text(json.dumps({
        "status": "READY", "ready": 26, "expected_session": day,
    }))
    return root / "scores.csv", root / "qc.json"


def write_settlement_prices(root, spec):
    days = pd.DatetimeIndex(["2026-11-20", "2026-11-23",
                             "2026-11-24", "2026-11-25", "2026-11-27"])
    for i, symbol in enumerate(spec["core"]):
        data = pd.DataFrame({
            "timestamp": days, "open": 100. + i,
            "high": 105. + i, "low": 90. + i,
            "close": 101. + i, "volume": 1000,
        })
        filename = market_file(root, symbol)
        filename.parent.mkdir(parents=True, exist_ok=True)
        data.to_parquet(filename, index=False)


class FutureShadowTests(unittest.TestCase):
    def test_signal_is_admitted_after_close_but_never_after_next_open(self):
        yes, _ = check_signal_admission("2026-11-20", pd.Timestamp("2026-11-21T01:30:00Z"))
        no, _ = check_signal_admission("2026-11-20", pd.Timestamp("2026-11-23T16:30:00Z"))
        self.assertTrue(yes)
        self.assertFalse(no)

    def test_hash_link_rejects_mutation_and_missing_link(self):
        j = []
        a = chain_append(j, {
            "kind": "SIGNAL", "signal_date": "2026-11-20", "symbol": "SPY",
            "probability": .7, "candidate": True, "research_only": True,
        })
        b = chain_append(j, {
            "kind": "SETTLED", "signal_date": "2026-11-20", "symbol": "SPY",
            "signal_hash": a["hash"], "entry_date": "2026-11-23",
            "exit_date": "2026-11-27", "research_only": True,
        })
        self.assertEqual(check_events(j, {"SPY"})[1], {("2026-11-20", "SPY")})
        j[0]["probability"] = .3
        with self.assertRaisesRegex(RuntimeError, "JOURNAL_HASH_CHAIN"):
            check_events(j, {"SPY"})

    def test_prior_zip_manifest_sha256_and_seed_cutoff(self):
        spec = load_spec()
        blob = make_prior_zip()
        _, rows = validate_prior_results_archive(blob, set(spec["core"]))
        self.assertEqual(rows, [])
        with ZipFile(BytesIO(blob)) as original:
            altered = BytesIO()
            with ZipFile(altered, "w") as z:
                for filename in original.namelist():
                    value = original.read(filename)
                    if filename == "qc.json":
                        value = b"changed"
                    z.writestr(filename, value)
            with self.assertRaisesRegex(RuntimeError, "PRIOR_RESEARCH_HASH_MISMATCH"):
                validate_prior_results_archive(altered.getvalue(), set(spec["core"]))
        later = make_prior_zip(session="2026-11-27")
        with self.assertRaisesRegex(RuntimeError, "MISSING_FORWARD_HISTORY"):
            validate_prior_results_archive(later, set(spec["core"]))

    def test_first_prospective_capture_and_late_run_fails_closed(self):
        spec = load_spec()
        with TemporaryDirectory() as root:
            scores, qc = write_score_and_qc(root, spec, "2026-11-20")
            with patch("daily20.last_completed_nyse",
                       return_value=pd.Timestamp("2026-11-20").date()):
                report = run(
                    spec, make_prior_zip(), Path(root) / "market", scores, qc,
                    Path(root) / "new", now=pd.Timestamp("2026-11-21T01:30:00Z"),
                    run_id="new-run", source_sha="gitsha"
                )
                self.assertEqual(report["new_signal_events"], 20)
                self.assertEqual(report["settled_events"], 0)
                self.assertEqual(report["pending_events"], 20)
                self.assertEqual(report["first_admitted_session"], "2026-11-20")
                with self.assertRaisesRegex(RuntimeError, "NO_SEED_BEFORE_NEXT_OPEN"):
                    run(spec, make_prior_zip(), Path(root) / "market", scores, qc,
                        Path(root) / "late", now=pd.Timestamp("2026-11-23T16:30:00Z"))
            with self.assertRaisesRegex(RuntimeError, "FROZEN_FORWARD_SIGNAL_REVISED"):
                old = json.loads((Path(root) / "new/report.json").read_text())
                journal = [json.loads(x) for x in
                           (Path(root) / "new/journal.jsonl").read_text().splitlines()]
                prior = make_prior_zip(journal=journal)
                new_scores, qc = write_score_and_qc(
                    Path(root), spec, "2026-11-20", tamper_symbol="SPY"
                )
                with patch("daily20.last_completed_nyse",
                           return_value=pd.Timestamp("2026-11-20").date()):
                    run(spec, prior, Path(root) / "market", new_scores, qc,
                        Path(root) / "modified",
                        now=pd.Timestamp("2026-11-21T02:30:00Z"))

    def test_four_sessions_later_all_20_observations_mature(self):
        spec = load_spec()
        with TemporaryDirectory() as root:
            base = Path(root)
            scores, qc = write_score_and_qc(base, spec, "2026-11-20")
            with patch("daily20.last_completed_nyse",
                       return_value=pd.Timestamp("2026-11-20").date()):
                first = run(spec, make_prior_zip(), base / "market", scores, qc,
                            base / "initial", now=pd.Timestamp("2026-11-21T01:30:00Z"))
            journal = [json.loads(x) for x in
                       (base / "initial/journal.jsonl").read_text().splitlines()]
            self.assertEqual(len(journal), 20)
            prior = make_prior_zip(journal=journal)
            write_settlement_prices(base / "market", spec)
            scores, qc = write_score_and_qc(base, spec, "2026-11-27")
            with patch("daily20.last_completed_nyse",
                       return_value=pd.Timestamp("2026-11-27").date()):
                matured = run(
                    spec, prior, base / "market", scores, qc, base / "matured",
                    now=pd.Timestamp("2026-11-27T21:30:00Z")
                )
            self.assertEqual(matured["signal_events"], 40)
            self.assertEqual(matured["settled_events"], 20)
            self.assertEqual(matured["pending_events"], 20)
            self.assertEqual(matured["newly_settled_events"], 20)
            self.assertEqual(matured["matured_candidate_observations"], 10)
            observations = pd.read_csv(base / "matured/outcomes.csv")
            self.assertEqual(set(observations["exit_date"]), {"2026-11-27"})
            # EOD downside is only an OHLC-based hazard diagnostic, not an
            # executable stop price or actual fill.
            self.assertTrue((observations["worst_four_session_low_vs_entry"] < 0).all())
            recorded = [json.loads(x) for x in
                        (base / "matured/journal.jsonl").read_text().splitlines()]
            self.assertEqual(len(recorded), 60)
            check_events(recorded, set(spec["core"]))
            second_prior = make_prior_zip(session="2026-11-27", journal=recorded)
            _, repeated = validate_prior_results_archive(second_prior, set(spec["core"]))
            self.assertEqual(len(repeated), 60)


if __name__ == "__main__":
    unittest.main()
