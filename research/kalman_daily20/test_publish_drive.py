"""Offline Drive persistence checks: no OAuth calls, no secrets."""
import json
import os
import hashlib
from forward_shadow import chain_append, journal_bytes
from bear_forward import add_event
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from publish_drive import EXPECTED_TARGETS, build_zip, inspect_payload


def seed(root):
    d, r = Path(root) / "data", Path(root) / "results"
    p = d / "market/raw/yfinance"
    f = d / "features/talib"
    p.mkdir(parents=True)
    f.mkdir(parents=True)
    symbols = [
        "SPY", "QQQ", "QLD", "IWM", "AAPL", "MSFT", "AMZN", "GOOGL",
        "META", "NVDA", "AMD", "AVGO", "MU", "TSLA", "PLTR", "IONQ",
        "COIN", "MSTR", "JPM", "XOM",
        "SMH", "^VIX", "HYG", "LQD", "TLT", "GLD",
    ]
    import re
    key = lambda x: re.sub("[^a-z0-9]+", "_", x.lower()).strip("_")
    for s in symbols:
        (p / ("yf_" + key(s) + ".parquet")).write_bytes(b"PAR1" + b"a" * 128)
        (f / (key("VIX" if s == "^VIX" else s) + ".parquet")).write_bytes(b"PAR1" + b"b" * 128)
    (r / "research").mkdir(parents=True)
    (r / "qc.json").write_text(json.dumps({
        "status": "READY", "required": 26, "ready": 26,
        "expected_session": "2026-11-20",
        "symbols": [{"symbol": x, "status": "READY"} for x in symbols]
    }))
    (r / "research/summary.json").write_text(json.dumps({
        "research_only": True, "live_execution": False,
        "latest_score_count": 20, "total_oos_trades": 1499,
        "version": "kalman-daily20-v1-20261121"
    }))
    (r / "universe-derived.json").write_text(json.dumps({
        "assets": [{"provider_symbol": x, "group": ("DAILY20_CORE" if x in symbols[:20] else "DAILY20_CONTEXT")} for x in symbols]
    }))
    (r / "research/portfolio_summary.json").write_text(json.dumps({
        "research_only": True, "live_execution": False,
        "portfolio_mdd_available": True, "tradable_strategy_approved": False,
        "scenario_count": 16, "primary_scenarios": [{}] * 4,
        "benchmark": {"SPY": {}, "QQQ": {}},
    }))
    for filename in ("portfolio_daily_equity.csv", "portfolio_executions.csv",
                     "portfolio_annual.csv", "portfolio_scenarios.csv"):
        (r / "research" / filename).write_text("column1,column2\\nvalue1,value2\\n")
    bear = r / "research/regime_challenger"
    bear.mkdir(parents=True)
    (bear / "regime_summary.json").write_text(json.dumps({
        "version": "daily20-bear-oos-v1", "research_only": True,
        "live_execution": False, "tradable_strategy_approved": False,
        "scenario_count": 20, "unique_bear_oos_trades": 0,
        "scenario_results": [{}] * 20,
        "per_year_market_coverage": [{"year": 2024}, {"year": 2025}, {"year": 2026}],
    }))
    (bear / "baseline_loss_attribution.json").write_text(json.dumps({
        "research_only": True, "causal_attribution": False,
        "used_for_strategy_selection": False
    }))
    for filename in ("regime_scenarios.csv", "regime_daily_equity.csv",
                     "regime_executions.csv", "regime_annual.csv",
                     "regime_year_coverage.csv", "regime_session_context.csv",
                     "bear_model_coverage.csv", "bear_oos_trades.csv",
                     "baseline_loss_attribution.csv"):
        (bear / filename).write_text("column1,column2\\nvalue1,value2\\n")
    future = r / "research/forward_shadow"
    future.mkdir(parents=True)
    journal = []
    for symbol in symbols[:20]:
        chain_append(journal, {
            "kind": "SIGNAL", "research_only": True,
            "signal_date": "2026-11-20", "symbol": symbol,
            "probability": 0.7, "candidate": True,
            "shadow_only": symbol in {"QLD", "IONQ", "COIN", "MSTR"},
        })
    payload = journal_bytes(journal)
    (future / "journal.jsonl").write_bytes(payload)
    (future / "report.json").write_text(json.dumps({
        "version": "daily20-forward-shadow-v1",
        "status": "RESEARCH_ONLY", "research_only": True,
        "live_execution": False, "approved_live": False,
        "historical_oos_2024_26_promoted": False,
        "retrospective_backfill": False,
        "last_completed_session": "2026-11-20",
        "source_run_id": os.environ.get("GITHUB_RUN_ID", "test-run"),
        "first_admitted_session": "2026-11-20",
        "signal_events": 20, "settled_events": 0,
        "pending_events": 20, "journal_hash_tip": journal[-1]["hash"],
        "journal_sha256": hashlib.sha256(payload).hexdigest(),
    }))
    (future / "snapshots.csv").write_text(
        "symbol,probability\n" + "\n".join(f"{s},0.7" for s in symbols[:20]) + "\n"
    )
    (future / "outcomes.csv").write_text(
        "signal_date,symbol,exit_date\n"
    )
    bdir = r / "research/bear_forward"
    bdir.mkdir(parents=True)
    bj = []
    for orig in journal:
        for family in ("BEAR_LOGISTIC", "BEAR_RULE"):
            add_event(bj, {
                "kind": "SIGNAL", "research_only": True,
                "signal_date": "2026-11-20", "symbol": orig["symbol"],
                "family": family, "model_version": "daily20-bear-forward-v1",
                "baseline_signal_hash": orig["hash"],
                "candidate": True, "eligible": True,
                "probability": .7 if family == "BEAR_LOGISTIC" else None,
                "shadow_only": orig["shadow_only"],
                "feature_sha256": "a" * 64,
                "recorded_at_utc": "2026-11-21T02:00:00+00:00",
            })
    bear_data = journal_bytes(bj)
    (bdir / "journal.jsonl").write_bytes(bear_data)
    (bdir / "report.json").write_text(json.dumps({
        "version": "daily20-bear-forward-v1",
        "status": "RESEARCH_ONLY", "research_only": True,
        "live_execution": False, "approved_live": False,
        "historical_oos_promoted": False,
        "backdated_signal_reconstruction": False,
        "benchmark_model_not_modified": True, "no_broker_order": True,
        "last_completed_session": "2026-11-20",
        "source_run_id": os.environ.get("GITHUB_RUN_ID", "test-run"),
        "signal_events": 40, "settled_events": 0, "pending_events": 40,
        "frozen_sessions": 1, "journal_sha256": hashlib.sha256(bear_data).hexdigest(),
        "frozen_replay_drift": 0, "frozen_replay_differences": [],
        "journal_hash_tip": bj[-1]["hash"],
        "family": {"BEAR_LOGISTIC": {"signals": 20, "candidates": 20},
                   "BEAR_RULE": {"signals": 20, "candidates": 20}},
    }))
    for filename in ("snapshots.csv", "outcomes.csv", "latest_candidates.csv"):
        (bdir / filename).write_text("col1,col2\nexample,example\n")
    mc = r / "research/monte_carlo"
    mc.mkdir(parents=True)
    (mc / "monte_carlo_summary.json").write_text(json.dumps({
        "version": "daily20-monte-carlo-v1",
        "status": "HISTORICAL_RESAMPLING_ONLY",
        "research_only": True, "approved_live": False,
        "model_selection_allowed": False, "future_oos_validated": False,
        "not_a_forecast_probability": True,
        "sampling_method": "paired_circular_moving_block_bootstrap_year_stratified",
        "block_lengths": [1, 5, 20],
        "replications_per_block": 2000,
        "strategy_scenarios": 36, "benchmarks": ["SPY", "QQQ"],
        "scenario_rows": 114, "sessions": 726,
        "last_session": "2026-11-20",
        "primary_block20": [{}] * 6,
    }))
    (mc / "monte_carlo_observed_baseline.csv").write_text(
        "scenario,observed_total_return,sessions\nSPY,0.5,726\n"
    )
    import csv
    scenarios = [f"MODEL_{i}" for i in range(36)] + [
        "BENCHMARK_SPY", "BENCHMARK_QQQ"
    ]
    with (mc / "monte_carlo_scenarios.csv").open("w", newline="") as output:
        cols = ["scenario", "block_length", "n_resamples", "status",
                "approved_live", "loss_probability",
                "mdd_at_least_20pct_probability",
                "mdd_at_least_30pct_probability",
                "probability_underperform_spy", "probability_underperform_qqq",
                "return_p05", "return_median", "return_p95",
                "mdd_p05_worst", "mdd_median", "mdd_p95_best"]
        writer = csv.DictWriter(output, fieldnames=cols)
        writer.writeheader()
        for length in (1, 5, 20):
            for symbol in scenarios:
                writer.writerow({
                    "scenario": symbol, "block_length": length,
                    "n_resamples": 2000, "status": "HISTORICAL_RESAMPLING_ONLY",
                    "approved_live": False,
                    "loss_probability": .45,
                    "mdd_at_least_20pct_probability": .3,
                    "mdd_at_least_30pct_probability": .1,
                    "probability_underperform_spy": .7,
                    "probability_underperform_qqq": .8,
                    "return_p05": -.4, "return_median": .1, "return_p95": .35,
                    "mdd_p05_worst": -.5, "mdd_median": -.15,
                    "mdd_p95_best": -.05,
                })
    return d, r


class DrivePublisherTests(unittest.TestCase):
    def test_two_pinned_verified_targets(self):
        self.assertEqual(len(EXPECTED_TARGETS), 2)
        self.assertTrue(all(len(v[0]) >= 20 and v[1].endswith(".zip")
                            for v in EXPECTED_TARGETS.values()))

    def test_validates_26_plus_26_and_zip_manifest(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            mf = inspect_payload(data, results)
            self.assertTrue(mf["research_only"])
            self.assertFalse(mf["production_writes"])
            self.assertEqual(mf["feature_symbols"], 26)
            dst = build_zip(data, Path(root) / "output" / "data.zip", mf)
            with ZipFile(dst) as z:
                self.assertEqual(len(z.namelist()), 53)
                self.assertIsNone(z.testzip())
                payload = json.loads(z.read("drive_manifest.json"))
                self.assertEqual(len(payload["payload_hashes_sha256"]), 52)

    def test_missing_or_incomplete_data_blocks_before_auth(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            (data / "market/raw/yfinance/yf_spy.parquet").unlink()
            with self.assertRaisesRegex(RuntimeError, "INCOMPLETE_PARQUET"):
                inspect_payload(data, results)

    def test_qc_failure_blocks_before_auth(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            path = results / "qc.json"
            payload = json.loads(path.read_text())
            payload["ready"] = 25
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(RuntimeError, "DATA_QC"):
                inspect_payload(data, results)

    def test_live_flag_fails_closed(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            path = results / "research/summary.json"
            payload = json.loads(path.read_text())
            payload["live_execution"] = True
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(RuntimeError, "RESEARCH_ISOLATION"):
                inspect_payload(data, results)

    def test_portfolio_evidence_required(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            (results / "research/portfolio_summary.json").unlink()
            with self.assertRaisesRegex(RuntimeError, "PORTFOLIO_EVIDENCE"):
                inspect_payload(data, results)

    def test_cannot_auto_promote_portfolio_to_live(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            path = results / "research/portfolio_summary.json"
            report = json.loads(path.read_text())
            report["tradable_strategy_approved"] = True
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(RuntimeError, "PORTFOLIO_GOVERNANCE"):
                inspect_payload(data, results)

    def test_reject_missing_bear_evidence(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            (results / "research/regime_challenger/regime_summary.json").unlink()
            with self.assertRaisesRegex(RuntimeError, "BEAR_RESEARCH_EVIDENCE"):
                inspect_payload(data, results)

    def test_reject_bear_rule_promotion_to_live(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            path = results / "research/regime_challenger/regime_summary.json"
            report = json.loads(path.read_text())
            report["tradable_strategy_approved"] = True
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(RuntimeError, "BEAR_RESEARCH_GOVERNANCE"):
                inspect_payload(data, results)


    def test_missing_prospective_journal_blocks_upload(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            (results / "research/forward_shadow/journal.jsonl").unlink()
            with self.assertRaisesRegex(RuntimeError, "MISSING_SEALED_FORWARD"):
                inspect_payload(data, results)

    def test_modified_prospective_event_blocks_upload(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            journal = results / "research/forward_shadow/journal.jsonl"
            altered = journal.read_text().replace('"probability":0.7', '"probability":0.4')
            journal.write_text(altered)
            # Even if a manifest/report were changed, the inner chain must still match.
            report_file = results / "research/forward_shadow/report.json"
            report = json.loads(report_file.read_text())
            report["journal_sha256"] = hashlib.sha256(journal.read_bytes()).hexdigest()
            report_file.write_text(json.dumps(report))
            with self.assertRaisesRegex(RuntimeError, "FORWARD_SHADOW_EVENT_CHAIN"):
                inspect_payload(data, results)

    def test_prospective_governance_never_approves_live(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            p = results / "research/forward_shadow/report.json"
            x = json.loads(p.read_text())
            x["approved_live"] = True
            p.write_text(json.dumps(x))
            with self.assertRaisesRegex(RuntimeError, "FORWARD_SHADOW_PUBLISH_GOVERNANCE"):
                inspect_payload(data, results)


    def test_unanchored_frozen_score_replay_drift_blocks_publishing(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            report_file = results / "research/forward_shadow/report.json"
            report = json.loads(report_file.read_text())
            report["frozen_replay_drift_detected"] = True
            report["frozen_replay_drift_count"] = 1
            report["frozen_journal_on_drift"] = "UNMODIFIED"
            report["replay_drift_never_tradable"] = True
            report["frozen_replay_differences"] = [{
                "symbol": "SPY", "frozen_event_hash": "f" * 64,
                "frozen_probability": .7, "frozen_candidate": True,
                "classification": "REPLAY_DRIFT_NO_FROZEN_EVENT_MODIFIED",
            }]
            report_file.write_text(json.dumps(report))
            with self.assertRaisesRegex(RuntimeError, "FROZEN_REPLAY_AUDIT_ANCHOR_INVALID"):
                inspect_payload(data, results)

    def test_bear_forward_is_required_for_drive_publishing(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            (results / "research/bear_forward/journal.jsonl").unlink()
            with self.assertRaisesRegex(RuntimeError, "BEAR_FORWARD_EVIDENCE_INCOMPLETE"):
                inspect_payload(data, results)

    def test_bear_forward_rejects_mutated_family_candidate(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            file = results / "research/bear_forward/journal.jsonl"
            text = file.read_text().replace('"candidate":true', '"candidate":false', 1)
            file.write_text(text)
            report_file = results / "research/bear_forward/report.json"
            report = json.loads(report_file.read_text())
            report["journal_sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
            report_file.write_text(json.dumps(report))
            with self.assertRaisesRegex(RuntimeError, "BEAR_FORWARD_CHAIN_INVALID"):
                inspect_payload(data, results)

    def test_bear_forward_never_promotes_live(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            file = results / "research/bear_forward/report.json"
            data_report = json.loads(file.read_text())
            data_report["approved_live"] = True
            file.write_text(json.dumps(data_report))
            with self.assertRaisesRegex(RuntimeError, "BEAR_FORWARD_GOVERNANCE_INVALID"):
                inspect_payload(data, results)

    def test_monte_carlo_required_before_drive_publishing(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            (results / "research/monte_carlo/monte_carlo_scenarios.csv").unlink()
            with self.assertRaisesRegex(RuntimeError, "MONTE_CARLO_EVIDENCE_INCOMPLETE"):
                inspect_payload(data, results)

    def test_monte_carlo_rejects_fake_forward_validation(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            path = results / "research/monte_carlo/monte_carlo_summary.json"
            report = json.loads(path.read_text())
            report["future_oos_validated"] = True
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(RuntimeError, "MONTE_CARLO_GOVERNANCE_FAILED"):
                inspect_payload(data, results)

    def test_monte_carlo_bad_tail_probability_fails_closed(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            path = results / "research/monte_carlo/monte_carlo_scenarios.csv"
            content = path.read_text()
            content = content.replace(",0.45,", ",1.45,", 1)
            path.write_text(content)
            with self.assertRaisesRegex(RuntimeError, "MONTE_CARLO_PROBABILITY_OUTSIDE_UNIT_INTERVAL"):
                inspect_payload(data, results)


    def test_bear_forward_drift_audit_must_reference_original_event_hash(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            report_path = results / "research/bear_forward/report.json"
            report = json.loads(report_path.read_text())
            report["frozen_replay_drift"] = 1
            report["frozen_replay_differences"] = [{
                "symbol": "SPY", "family": "BEAR_LOGISTIC",
                "classification": "REPLAY_DRIFT_FROZEN_EVENT_PRESERVED",
                "frozen_event_hash": "0" * 64,
                "frozen_candidate": True, "frozen_probability": 0.7,
                "changed_fields": ["probability"],
            }]
            report_path.write_text(json.dumps(report))
            with self.assertRaisesRegex(RuntimeError, "BEAR_FORWARD_REPLAY_AUDIT_INVALID"):
                inspect_payload(data, results)



if __name__ == "__main__":
    unittest.main()
