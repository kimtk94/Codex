#!/usr/bin/env python3
"""Attest model-critical execution environment without certifying market prices.

Records installed wheel RECORD digests *and actual selected native extension
bytes*. Compares current research job with its contract job and with the
previous authenticated results ZIP, retaining missing-baseline and source
revision states as HOLD. Never rewrites forecasts, inputs or Drive archives.
"""
from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import sys
import sysconfig
from zipfile import ZipFile

VERSION = "daily20-model-runtime-lineage-v1"
MEMBER = "research/model_runtime_lineage/report.json"
CORE = ("numpy", "pandas", "scipy", "scikit-learn", "pyarrow")
OPTIONAL = ("TA-Lib", "yfinance")
THREAD_KEYS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
               "ARROW_NUM_THREADS")
CODE_FILES = (
    "research/kalman_daily20/train.py",
    "research/kalman_daily20/regime_challenger.py",
    "research/kalman_daily20/provenance_audit.py",
    "research/kalman_daily20/stability_gate.py",
    "research/kalman_daily20/forward_shadow.py",
    "research/kalman_daily20/bear_forward.py",
    "kalman-toss-gateway/engine/market_data/requirements.txt",
)
# Actual relevant native parser/model extensions; first matching .so per family.
EXTENSION_HINTS = {
    "numpy": ("_multiarray_umath",),
    "pandas": ("parsers",),
    "scipy": ("_fblas", "_ufuncs"),
    "scikit-learn": ("_cd_fast", "_liblinear"),
    "pyarrow": ("lib.cpython", "lib.so"),
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def valid_digest(value):
    return (type(value) is str and len(value) == 64 and
            all(x in "0123456789abcdef" for x in value))


def file_sha(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_info(name):
    try:
        pkg = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return {"installed": False, "version": None,
                "record_sha256": None, "native_extensions": {}}
    record = pkg.read_text("RECORD")
    native = {}
    hints = EXTENSION_HINTS.get(name, ())
    if hints:
        files = sorted((f for f in (pkg.files or ())
                        if str(f).endswith((".so", ".pyd"))),
                       key=lambda f: str(f))
        for hint in hints:
            matches = [f for f in files
                       if hint in str(f).rsplit("/", 1)[-1]]
            if matches:
                candidate = pkg.locate_file(matches[0])
                require(Path(candidate).is_file(),
                        "RUNTIME_NATIVE_EXTENSION_MISSING_" + name)
                native[hint] = file_sha(candidate)
    return {
        "installed": True,
        "version": pkg.version,
        "record_sha256": sha256(record.encode()).hexdigest() if record else None,
        "native_extensions": native,
    }


def environment():
    packages = {name: package_info(name) for name in (*CORE, *OPTIONAL)}
    require(all(packages[name]["installed"] for name in CORE),
            "RUNTIME_MODEL_REQUIRED_PACKAGE_MISSING")
    paths = {p: file_sha(p) for p in CODE_FILES}
    return {
        "python": platform.python_version(),
        "python_abi": sysconfig.get_config_var("SOABI"),
        "machine": platform.machine(),
        "system": platform.system(),
        "architecture_bits": 64 if sys.maxsize > (1 << 32) else 32,
        "packages": packages,
        "thread_config": {name: os.environ.get(name) for name in THREAD_KEYS},
        "model_source_sha256": paths,
    }


def load_previous(raw):
    if raw is None:
        return None
    require(isinstance(raw, bytes), "RUNTIME_BAD_PRIOR_ZIP_BYTES")
    with ZipFile(__import__("io").BytesIO(raw)) as zf:
        names = set(zf.namelist())
        require("drive_manifest.json" in names,
                "RUNTIME_PRIOR_DRIVE_MANIFEST_ABSENT")
        manifest = json.loads(zf.read("drive_manifest.json"))
        hashes = manifest.get("payload_hashes_sha256")
        require(isinstance(hashes, dict)
                and manifest.get("research_only") is True
                and manifest.get("production_writes") is False,
                "RUNTIME_PRIOR_MANIFEST_INVALID")
        if MEMBER not in names and MEMBER not in hashes:
            return None
        require(MEMBER in names and MEMBER in hashes
                and valid_digest(hashes[MEMBER]),
                "RUNTIME_PRIOR_REPORT_MANIFEST_INCONSISTENT")
        content = zf.read(MEMBER)
        require(sha256(content).hexdigest() == hashes[MEMBER],
                "RUNTIME_PRIOR_REPORT_HASH_MISMATCH")
        report = json.loads(content)
        require(report.get("version") == VERSION
                and report.get("research_only") is True
                and report.get("production_writes") is False
                and report.get("strategy_promoted") is False
                and report.get("live_execution") is False,
                "RUNTIME_PRIOR_REPORT_FALSE_CLAIM")
        return report


def compare(left, right):
    require(isinstance(left, dict) and isinstance(right, dict)
            and all(isinstance(d.get("packages"), dict)
                    for d in (left, right)), "RUNTIME_ENVIRONMENT_INVALID")
    compared = [x for x in CORE if
                left["packages"].get(x, {}).get("installed") is True and
                right["packages"].get(x, {}).get("installed") is True]
    differences = []
    for name in compared:
        for field in ("version", "record_sha256", "native_extensions"):
            a = left["packages"][name].get(field)
            b = right["packages"][name].get(field)
            if a != b:
                differences.append({"package": name, "field": field,
                                    "before": a, "after": b})
    code_different = sorted(
        p for p in set(left.get("model_source_sha256", {})) |
                         set(right.get("model_source_sha256", {}))
        if left.get("model_source_sha256", {}).get(p) !=
        right.get("model_source_sha256", {}).get(p)
    )
    runtime_fields = ("python", "python_abi", "machine",
                      "system", "architecture_bits", "thread_config")
    platform_different = [key for key in runtime_fields
                          if left.get(key) != right.get(key)]
    return {
        "compared_required_packages": compared,
        "package_differences": differences,
        "model_source_changed_files": code_different,
        "runtime_fields_changed": platform_different,
        "fully_comparable_required_packages": len(compared) == len(CORE),
        "model_environment_identical": (
            len(compared) == len(CORE) and not differences
            and not code_different and not platform_different
        ),
    }


def build(*, phase, current, run_id, run_attempt, session=None,
          contract=None, previous=None, prior_present=False,
          replay=None, stability=None):
    require(phase in ("contracts", "research"), "RUNTIME_PHASE_INVALID")
    require(isinstance(current, dict), "RUNTIME_CURRENT_MISSING")
    require(type(run_id) is str and bool(run_id.strip())
            and type(run_attempt) is str and bool(run_attempt.strip()),
            "RUNTIME_RUN_ID_ABSENT")
    if phase == "contracts":
        require(session is None and contract is None and previous is None
                and replay is None and stability is None,
                "RUNTIME_CONTRACTS_MUST_BE_INDEPENDENT")
        return {
            "version": VERSION, "phase": phase, "research_only": True,
            "live_execution": False, "production_writes": False,
            "strategy_promoted": False, "run_id": run_id,
            "run_attempt": run_attempt, "session": None,
            "environment": current, "status": "CONTRACTS_RUNTIME_ATTESTED",
        }
    require(isinstance(session, str), "RUNTIME_SESSION_REQUIRED")
    date.fromisoformat(session)
    require(isinstance(contract, dict)
            and contract.get("version") == VERSION
            and contract.get("phase") == "contracts"
            and contract.get("run_id") == run_id
            and contract.get("run_attempt") == run_attempt
            and contract.get("research_only") is True
            and contract.get("production_writes") is False,
            "RUNTIME_CONTRACT_JOB_UNATTESTED")
    cross = compare(contract["environment"], current)
    if previous is not None:
        require(prior_present and previous.get("phase") == "research",
                "RUNTIME_PRIOR_NOT_RESEARCH")
        require(isinstance(previous.get("session"), str),
                "RUNTIME_PRIOR_SESSION_MISSING")
        require(date.fromisoformat(previous["session"]) <= date.fromisoformat(session),
                "RUNTIME_PRIOR_FROM_FUTURE")
        require(previous.get("run_id") != run_id or
                previous.get("run_attempt") != run_attempt,
                "RUNTIME_PRIOR_SAME_RUN_NOT_DISTINCT")
        prior_comparison = compare(previous["environment"], current)
        scope = ("SAME_SESSION" if previous["session"] == session
                 else "DIFFERENT_SESSION")
        prior_status = (
            "SAME_SESSION_RUNTIME_MATCH_RESEARCH_ONLY"
            if scope == "SAME_SESSION" and prior_comparison["model_environment_identical"]
            else "SAME_SESSION_RUNTIME_DIFFERENCE_RESEARCH_HOLD"
            if scope == "SAME_SESSION"
            else "CROSS_SESSION_RUNTIME_MATCH_NOT_REPLAY_PROOF"
            if prior_comparison["model_environment_identical"]
            else "CROSS_SESSION_RUNTIME_CHANGED_NOT_CAUSAL_PROOF"
        )
    else:
        prior_comparison = None
        scope = None
        prior_status = ("PRIOR_ARCHIVE_REPORT_MISSING_LEGACY_HOLD"
                        if prior_present else "PR_OR_OFFLINE_NO_PRIOR_REFERENCE_HOLD")
    if replay is not None or stability is not None:
        require(isinstance(replay, dict) and isinstance(stability, dict)
                and replay.get("session") == stability.get("session") == session
                and replay.get("version") == "daily20-replay-reconciliation-v1"
                and stability.get("version") == "daily20-prospective-stability-v1"
                and replay.get("independent_source_finality_verified") == 0
                and replay.get("causal_upstream_mechanism_certified") is False
                and replay.get("research_only") is True
                and stability.get("research_only") is True
                and stability.get("strategy_promoted") is False,
                "RUNTIME_MODEL_REPLAY_SCOPE_MISMATCH")
        replay_obs = {
            "bull_drift_count": replay["bull_drift_count"],
            "bull_material_count": replay["bull_material_count"],
            "bear_drift_count": replay["bear_drift_count"],
            "legacy_without_original_21_feature_snapshot":
                replay["legacy_without_original_21_feature_snapshot"],
            "original_21_feature_snapshot_available":
                replay["original_21_feature_snapshot_available"],
            "frozen_snapshot_sha256": stability.get("frozen_snapshot_sha256"),
        }
    else:
        require(replay is None and stability is None,
                "RUNTIME_PARTIAL_REPLAY_EVIDENCE")
        replay_obs = None
    return {
        "version": VERSION, "phase": phase, "session": session,
        "run_id": run_id, "run_attempt": run_attempt,
        "research_only": True, "live_execution": False,
        "production_writes": False, "strategy_promoted": False,
        "status": "MODEL_RUNTIME_PROVENANCE_RESEARCH_HOLD",
        "environment": current,
        "contracts_comparison": cross,
        "prior_results_zip_available": prior_present,
        "prior_runtime_report_available": previous is not None,
        "prior_session": previous["session"] if previous else None,
        "prior_run_id": previous["run_id"] if previous else None,
        "prior_compare_scope": scope,
        "prior_runtime_comparison": prior_comparison,
        "prior_runtime_status": prior_status,
        "replay_observations": replay_obs,
        "frozen_signals_modified": False,
        "independent_price_certified": False,
        "numerical_drift_cause_certified": False,
        "notes": (
            "RECORD SHA records package installation metadata; selected native "
            "extension bytes are independently SHA256 hashed. This checks "
            "runtime comparability, not source market truth. A match never "
            "reconstructs the absent original 2026-11-20 features."
        ),
    }


def run(*, phase, out, contracts=None, prior_zip=None, qc=None,
        replay=None, stability=None):
    current = environment()
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    if phase == "contracts":
        result = build(phase=phase, current=current,
                       run_id=run_id, run_attempt=attempt)
    else:
        require(all(x is not None for x in (contracts, qc)),
                "RUNTIME_RESEARCH_REQUIRED_INPUTS")
        contract = json.loads(Path(contracts).read_bytes())
        quality = json.loads(Path(qc).read_bytes())
        require(quality.get("research_only") is True and
                quality.get("required") == 26 and quality.get("ready") == 26
                and quality.get("status") == "READY",
                "RUNTIME_QC_SOURCE_NOT_READY")
        prev_bytes = Path(prior_zip).read_bytes() if prior_zip is not None else None
        prev = load_previous(prev_bytes) if prev_bytes else None
        replay_doc = json.loads(Path(replay).read_bytes()) if replay else None
        stability_doc = json.loads(Path(stability).read_bytes()) if stability else None
        result = build(
            phase=phase, current=current, run_id=run_id,
            run_attempt=attempt, session=quality["expected_session"],
            contract=contract, previous=prev, prior_present=bool(prev_bytes),
            replay=replay_doc, stability=stability_doc,
        )
        result["input_sha256"] = {
            "contracts": file_sha(contracts), "qc": file_sha(qc),
            **({"prior_results_zip": file_sha(prior_zip)} if prior_zip else {}),
            **({"replay": file_sha(replay)} if replay else {}),
            **({"stability": file_sha(stability)} if stability else {}),
        }
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("DAILY20_MODEL_RUNTIME", phase, result["status"],
          "session", result.get("session"),
          "contract_env_identical",
          result.get("contracts_comparison", {}).get("model_environment_identical"),
          "prior", result.get("prior_runtime_status"))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", required=True, choices=["contracts", "research"])
    p.add_argument("--out", required=True)
    p.add_argument("--contracts")
    p.add_argument("--qc")
    p.add_argument("--prior-zip")
    p.add_argument("--replay")
    p.add_argument("--stability")
    a = p.parse_args()
    run(phase=a.phase, out=a.out, contracts=a.contracts, qc=a.qc,
        prior_zip=a.prior_zip, replay=a.replay, stability=a.stability)


if __name__ == "__main__":
    main()
