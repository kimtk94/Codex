"""Offline contracts: runtime evidence never certifies replay causality or prices."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from model_runtime_lineage import (
    VERSION, MEMBER, CORE, build, compare, load_previous, run,
)

DIGEST = "a" * 64
SESSION = "2026-11-20"


def fake_env():
    packages = {
        name: {"installed": True, "version": "2.1.0",
               "record_sha256": DIGEST, "native_extensions": {"selected": DIGEST}}
        for name in CORE
    }
    for key in ("TA-Lib", "yfinance"):
        packages[key] = {
            "installed": False, "version": None, "record_sha256": None,
            "native_extensions": {},
        }
    return {
        "python": "3.11.18", "python_abi": "cpython-311-x86_64-linux-gnu",
        "machine": "x86_64", "system": "Linux",
        "architecture_bits": 64, "packages": packages,
        "thread_config": {"OMP_NUM_THREADS": "1"},
        "model_source_sha256": {"research/kalman_daily20/train.py": DIGEST},
    }


def contract():
    return build(phase="contracts", current=fake_env(),
                 run_id="444", run_attempt="1")


def replay():
    return {
        "version": "daily20-replay-reconciliation-v1", "session": SESSION,
        "independent_source_finality_verified": 0,
        "causal_upstream_mechanism_certified": False,
        "research_only": True, "bull_drift_count": 20,
        "bull_material_count": 4, "bear_drift_count": 32,
        "legacy_without_original_21_feature_snapshot": True,
        "original_21_feature_snapshot_available": False,
    }


def stability():
    return {
        "version": "daily20-prospective-stability-v1",
        "session": SESSION, "research_only": True,
        "strategy_promoted": False,
        "frozen_snapshot_sha256": None,
    }


def prior_report():
    r = build(phase="research", current=fake_env(),
              run_id="333", run_attempt="1", session=SESSION,
              contract={**contract(), "run_id": "333"},
              prior_present=False, replay=replay(), stability=stability())
    return r


def archive(report=None, *, corrupt=False, orphans=False):
    manifest = {
        "format": "kalman-daily20-drive-v1",
        "research_only": True,
        "production_writes": False,
        "payload_hashes_sha256": {},
    }
    payload = json.dumps(report or prior_report()).encode()
    if report is not None or not orphans:
        manifest["payload_hashes_sha256"][MEMBER] = (
            "b" * 64 if corrupt else sha256(payload).hexdigest()
        )
    stream = BytesIO()
    with ZipFile(stream, "w") as z:
        if not orphans:
            z.writestr(MEMBER, payload)
        z.writestr("drive_manifest.json", json.dumps(manifest))
    return stream.getvalue()


class ModelRuntimeContracts(unittest.TestCase):
    def test_contract_report_cannot_claim_certification(self):
        r = contract()
        self.assertEqual(r["version"], VERSION)
        self.assertTrue(r["research_only"])
        self.assertFalse(r["strategy_promoted"])
        self.assertEqual(r["phase"], "contracts")

    def test_same_session_identical_environment_not_price_truth(self):
        r = build(phase="research", current=fake_env(), run_id="444",
                  run_attempt="1", session=SESSION, contract=contract(),
                  previous=prior_report(), prior_present=True,
                  replay=replay(), stability=stability())
        self.assertEqual(r["prior_runtime_status"],
                         "SAME_SESSION_RUNTIME_MATCH_RESEARCH_ONLY")
        self.assertTrue(r["prior_runtime_comparison"]["model_environment_identical"])
        self.assertFalse(r["numerical_drift_cause_certified"])
        self.assertFalse(r["independent_price_certified"])
        self.assertEqual(r["replay_observations"]["bull_material_count"], 4)

    def test_changed_package_binary_hash_does_not_infer_price_cause(self):
        now = fake_env()
        now["packages"]["pandas"]["native_extensions"]["selected"] = "b" * 64
        report = build(phase="research", current=now, run_id="444",
                       run_attempt="1", session=SESSION, contract=contract(),
                       previous=prior_report(), prior_present=True)
        self.assertEqual(report["prior_runtime_status"],
                         "SAME_SESSION_RUNTIME_DIFFERENCE_RESEARCH_HOLD")
        diffs = report["prior_runtime_comparison"]["package_differences"]
        self.assertTrue(any(d["package"] == "pandas" and
                            d["field"] == "native_extensions" for d in diffs))
        self.assertFalse(report["numerical_drift_cause_certified"])

    def test_same_version_different_wheel_metadata_not_equivalent(self):
        old = fake_env()
        now = deepcopy(old)
        now["packages"]["numpy"]["record_sha256"] = "b" * 64
        cmp = compare(old, now)
        self.assertFalse(cmp["model_environment_identical"])
        self.assertEqual(cmp["package_differences"][0]["field"], "record_sha256")

    def test_model_source_code_delta_is_independent_axis(self):
        old = fake_env()
        now = deepcopy(old)
        now["model_source_sha256"]["research/kalman_daily20/train.py"] = "b" * 64
        cmp = compare(old, now)
        self.assertIn("research/kalman_daily20/train.py",
                      cmp["model_source_changed_files"])
        self.assertFalse(cmp["model_environment_identical"])

    def test_thread_change_is_not_silent_runtime_equivalence(self):
        old = fake_env()
        now = deepcopy(old)
        now["thread_config"]["OMP_NUM_THREADS"] = "8"
        cmp = compare(old, now)
        self.assertIn("thread_config", cmp["runtime_fields_changed"])

    def test_missing_prior_report_is_legacy_hold(self):
        report = build(phase="research", current=fake_env(), run_id="444",
                       run_attempt="1", session=SESSION, contract=contract(),
                       prior_present=True, replay=replay(), stability=stability())
        self.assertFalse(report["prior_runtime_report_available"])
        self.assertEqual(report["prior_runtime_status"],
                         "PRIOR_ARCHIVE_REPORT_MISSING_LEGACY_HOLD")
        self.assertIsNone(report["prior_runtime_comparison"])

    def test_future_prior_session_is_rejected(self):
        previous = prior_report()
        previous["session"] = "2026-11-23"
        with self.assertRaisesRegex(ValueError, "RUNTIME_PRIOR_FROM_FUTURE"):
            build(phase="research", current=fake_env(), run_id="444",
                  run_attempt="1", session=SESSION, contract=contract(),
                  previous=previous, prior_present=True)

    def test_same_run_not_independent(self):
        previous = prior_report()
        previous["run_id"] = "444"
        with self.assertRaisesRegex(ValueError, "RUNTIME_PRIOR_SAME_RUN"):
            build(phase="research", current=fake_env(), run_id="444",
                  run_attempt="1", session=SESSION, contract=contract(),
                  previous=previous, prior_present=True)

    def test_contract_job_must_match_run_id(self):
        with self.assertRaisesRegex(ValueError, "RUNTIME_CONTRACT_JOB_UNATTESTED"):
            build(phase="research", current=fake_env(), run_id="445",
                  run_attempt="1", session=SESSION, contract=contract())

    def test_replay_report_session_not_backdated(self):
        bad = replay()
        bad["session"] = "2026-11-19"
        with self.assertRaisesRegex(ValueError, "RUNTIME_MODEL_REPLAY_SCOPE"):
            build(phase="research", current=fake_env(), run_id="444",
                  run_attempt="1", session=SESSION, contract=contract(),
                  replay=bad, stability=stability())

    def test_one_missing_report_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "RUNTIME_PARTIAL_REPLAY"):
            build(phase="research", current=fake_env(), run_id="444",
                  run_attempt="1", session=SESSION, contract=contract(),
                  replay=replay(), stability=None)

    def test_cross_session_match_cannot_claim_replay_identical(self):
        prior = prior_report()
        prior["session"] = "2026-11-19"
        r = build(phase="research", current=fake_env(), run_id="444",
                  run_attempt="1", session=SESSION, contract=contract(),
                  previous=prior, prior_present=True)
        self.assertEqual(r["prior_compare_scope"], "DIFFERENT_SESSION")
        self.assertEqual(r["prior_runtime_status"],
                         "CROSS_SESSION_RUNTIME_MATCH_NOT_REPLAY_PROOF")

    def test_archive_hash_authentication(self):
        data = archive(prior_report())
        got = load_previous(data)
        self.assertEqual(got["phase"], "research")
        self.assertEqual(got["run_id"], "333")
        with self.assertRaisesRegex(ValueError, "RUNTIME_PRIOR_REPORT_HASH_MISMATCH"):
            load_previous(archive(prior_report(), corrupt=True))

    def test_legacy_no_member_is_not_invented(self):
        self.assertIsNone(load_previous(archive(orphans=True)))

    def test_partial_missing_member_fails(self):
        payload = archive(prior_report())
        mem = BytesIO()
        with ZipFile(BytesIO(payload)) as first, ZipFile(mem, "w") as out:
            out.writestr("drive_manifest.json", first.read("drive_manifest.json"))
        with self.assertRaisesRegex(ValueError, "RUNTIME_PRIOR_REPORT_MANIFEST_INCONSISTENT"):
            load_previous(mem.getvalue())

    def test_fake_prior_live_claim_rejected(self):
        old = prior_report()
        old["strategy_promoted"] = True
        with self.assertRaisesRegex(ValueError, "RUNTIME_PRIOR_REPORT_FALSE_CLAIM"):
            load_previous(archive(old))

    def test_contract_phase_ignores_replay_reports(self):
        with self.assertRaisesRegex(ValueError, "RUNTIME_CONTRACTS_MUST_BE_INDEPENDENT"):
            build(phase="contracts", current=fake_env(),
                  run_id="444", run_attempt="1", replay=replay())


if __name__ == "__main__":
    unittest.main()
