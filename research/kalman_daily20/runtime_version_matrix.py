#!/usr/bin/env python3
"""Isolated, research-only NumPy/PyArrow version comparison on frozen REAL Daily20 data.

The source is a read-only GitHub Actions data artifact produced by a specific
protected main run. No Yahoo refetch, no model policy tuning, no first-seal
journal import, and no broker. Native C/Python parsers run in child processes.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import subprocess
import sys

VERSION = "daily20-fixed-input-version-isolation-v1"
BASELINE_RUN_ID = "45033994883"
ASOF = "2026-11-20"
FAMILIES = ("BULL_LOGISTIC", "BEAR_LOGISTIC")
EXPECTED_PACKAGES = {
    "baseline": {"numpy": "2.3.5", "pyarrow": "24.0.0"},
    "research": {"numpy": "2.4.6", "pyarrow": "26.0.1"},
}
PARSER_FIELDS = ("signal_date", "symbol", "exit_date",
                 "entry_open", "exit_close",
                 "worst_four_session_low_vs_entry", "net_return_20bp")


def require(ok, why):
    if not ok:
        raise ValueError(why)


def filehash(p):
    h = sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_index(root, spec, *, expected=ASOF):
    """Generate exact per-file content anchors. No pandas is needed here."""
    from daily20 import market_file, feature_file
    names = list(spec["core"]) + list(spec["context"])
    require(len(spec["core"]) == 20 and len(spec["context"]) == 6
            and len(set(names)) == 26, "MATRIX_BAD_CANONICAL_UNIVERSE")
    data = {}
    for sym in names:
        paths = {
            "market": market_file(Path(root) / "market", sym),
            "feature": feature_file(Path(root) / "features", sym),
        }
        for typ, path in paths.items():
            require(path.is_file() and path.stat().st_size > 500,
                    "MATRIX_SOURCE_MEMBER_MISSING_" + sym + "_" + typ)
            key = str(path.relative_to(root))
            require(key not in data, "MATRIX_SOURCE_KEY_DUPLICATE")
            data[key] = {"sha256": filehash(path), "bytes": path.stat().st_size}
    return {
        "version": VERSION, "dataset": "PROTECTED_MAIN_ARCHIVED_REAL_BARS_FEATURES",
        "source_actions_run_id": BASELINE_RUN_ID,
        "asof_session": expected, "research_only": True,
        "production_writes": False, "live_execution": False,
        "strategy_promoted": False, "symbol_count": 26,
        "file_count": len(data), "files": dict(sorted(data.items())),
    }


def check_files(root, manifest, spec):
    current = source_index(root, spec, expected=manifest["asof_session"])
    require(manifest == current, "MATRIX_SOURCE_BYTES_CHANGED_OR_TAMPERED")
    return sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def parser_fixture(out, spec):
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PARSER_FIELDS)
        writer.writeheader()
        for i, sym in enumerate(spec["core"]):
            writer.writerow({
                "signal_date": ASOF, "symbol": sym,
                "exit_date": "2026-11-27", "entry_open": f"{100+i:.8f}",
                "exit_close": f"{101+i:.8f}",
                "worst_four_session_low_vs_entry": "-0.091",
                "net_return_20bp": "0.0075",
            })
    return filehash(p)


def probe_parser(path, engine, count):
    import pandas as pd
    require(engine in ("c", "python") and 1 <= count <= 300,
            "MATRIX_PARSER_ARGS")
    source_hash = filehash(path)
    rows_hash = None
    for _ in range(count):
        data = pd.read_csv(path, engine=engine, dtype={"symbol": str})
        require(len(data) == 20 and tuple(data.columns) == PARSER_FIELDS
                and data["exit_date"].nunique() == 1,
                "MATRIX_PARSER_CONTENT_INVALID")
        canonical = data.to_csv(index=False).encode()
        dig = sha256(canonical).hexdigest()
        require(rows_hash in (None, dig), "MATRIX_PARSER_REPEAT_NONDETERMINISM")
        rows_hash = dig
    return {"engine": engine, "source_sha256": source_hash,
            "rows": 20, "iterations": count,
            "parsed_canonical_sha256": rows_hash, "result": "PASS"}


def child_probes(script, fixture):
    outcome = []
    for engine in ("c", "python"):
        cmd = [sys.executable, str(script), "parser-probe",
               "--fixture", str(fixture), "--engine", engine,
               "--iterations", "150"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=90, check=False)
            try:
                result = json.loads(proc.stdout.strip()) if proc.returncode == 0 else None
            except json.JSONDecodeError:
                result = None
            status = ("PASS" if proc.returncode == 0 and
                      isinstance(result, dict) and result.get("result") == "PASS"
                      else "CRASH_OR_ERROR_RESEARCH_HOLD")
            outcome.append({"engine": engine, "status": status,
                            "returncode": proc.returncode,
                            "result": result,
                            "stderr_tail": proc.stderr[-1500:]})
        except subprocess.TimeoutExpired:
            outcome.append({"engine": engine, "status": "TIMEOUT_RESEARCH_HOLD",
                            "returncode": None, "result": None})
    return outcome


def work(root, spec, manifest, fixture, variant, *, output):
    from importlib import metadata
    import numpy as np
    import pandas as pd
    import pyarrow
    from provenance_audit import (
        predict_on_frame, fingerprint_feature_row, training_digest,
    )
    from train import COLUMNS, context_frame, feature_frame
    from model_runtime_lineage import package_info
    from daily20 import load_bars, market_file
    require(variant in EXPECTED_PACKAGES, "MATRIX_VARIANT_UNKNOWN")
    expected = EXPECTED_PACKAGES[variant]
    require(np.__version__ == expected["numpy"] and
            pyarrow.__version__ == expected["pyarrow"] and
            pd.__version__ == "2.3.3" and
            metadata.version("scikit-learn") == "1.9.1",
            "MATRIX_INSTALLED_STACK_UNEXPECTED")
    manifest_hash = check_files(root, manifest, spec)
    session = manifest["asof_session"]
    require(session == ASOF, "MATRIX_ARCHIVE_SESSION_UNEXPECTED")
    context = context_frame(Path(root) / "market")
    observations = []
    for sym in spec["core"]:
        bars = load_bars(market_file(Path(root) / "market", sym))
        require(str(bars.index.max().date()) == session,
                "MATRIX_MARKET_SESSION_MISMATCH_" + sym)
        frame = feature_frame(
            sym, Path(root) / "market", Path(root) / "features",
            context, float(spec["round_trip_cost_bps"]))
        require(not frame.empty and str(frame.index.max().date()) == session,
                "MATRIX_FEATURE_SESSION_MISMATCH_" + sym)
        feature_digest = fingerprint_feature_row(frame, session)
        for family in FAMILIES:
            r = predict_on_frame(frame, session, family)
            if sym in ("SPY", "NVDA"):
                repeat = predict_on_frame(frame, session, family)
                require(all(r[key] == repeat[key] for key in (
                    "prediction", "training_hash", "fitted_model_hash",
                    "fold_status", "training_rows"
                )), "MATRIX_SAME_ENV_RECOMPUTE_NOT_DETERMINISTIC_" + sym)
            observations.append({
                "symbol": sym, "family": family,
                "asof_feature_sha256": feature_digest,
                "prediction": r["prediction"], "fold_status": r["fold_status"],
                "training_rows": r["training_rows"],
                "training_hash": r["training_hash"],
                "fitted_model_hash": r["fitted_model_hash"],
            })
    results = child_probes(Path(__file__).resolve(), fixture)
    require(len(observations) == 40 and len(results) == 2,
            "MATRIX_INCOMPLETE_OUTPUT")
    report = {
        "version": VERSION, "variant": variant, "asof_session": session,
        "source_actions_run_id": BASELINE_RUN_ID,
        "research_only": True, "production_writes": False,
        "live_execution": False, "strategy_promoted": False,
        "real_source_manifest_sha256": manifest_hash,
        "native_parser_fixture_sha256": filehash(fixture),
        "models_fitted_or_attempted": 40, "assets": 20,
        "package_versions": {
            k: metadata.version(k) for k in (
                "numpy", "pandas", "pyarrow", "scipy", "scikit-learn")
        },
        "package_records": {
            k: package_info(k) for k in (
                "numpy", "pandas", "pyarrow", "scipy", "scikit-learn")
        },
        "code_file_sha256": filehash(
            "research/kalman_daily20/train.py"),
        "observations": observations, "parser_probe": results,
        "same_environment_repeat_checked_symbols": ["SPY", "NVDA"],
        "primary_price_certified": False,
        "causal_model_drift_claimed": False,
    }
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    return report


def compare(left, right):
    require(left["variant"] == "baseline" and right["variant"] == "research",
            "MATRIX_VARIANTS_WRONG")
    for data in (left, right):
        require(data.get("version") == VERSION
                and data.get("research_only") is True
                and data.get("strategy_promoted") is False
                and data.get("live_execution") is False
                and data.get("production_writes") is False
                and data.get("primary_price_certified") is False
                and data.get("causal_model_drift_claimed") is False
                and data.get("models_fitted_or_attempted") == 40
                and data.get("assets") == 20
                and data.get("source_actions_run_id") == BASELINE_RUN_ID,
                "MATRIX_FALSE_SCIENTIFIC_OR_COMPLETENESS_CLAIM")
        for pkg, version in EXPECTED_PACKAGES[data["variant"]].items():
            require(data["package_versions"][pkg] == version,
                    "MATRIX_UNEXPECTED_PINNED_VERSION")
    for field in ("asof_session", "real_source_manifest_sha256",
                  "native_parser_fixture_sha256", "code_file_sha256"):
        require(left[field] == right[field], "MATRIX_NOT_IDENTICAL_INPUT_" + field)
    def by_key(data):
        result = {}
        for row in data["observations"]:
            key = (row["symbol"], row["family"])
            require(key not in result, "MATRIX_DUPLICATE_MODEL_KEY")
            result[key] = row
        return result
    a, b = by_key(left), by_key(right)
    require(len(a) == len(b) == 40 and set(a) == set(b),
            "MATRIX_MODEL_KEY_MISSING")
    rows = []
    for key in sorted(a):
        old, new = a[key], b[key]
        for field in ("asof_feature_sha256", "training_hash", "training_rows",
                      "fold_status"):
            require(old[field] == new[field],
                    "MATRIX_INPUT_OR_TRAINING_CHANGED_" + str(key) + "_" + field)
        p, q = old["prediction"], new["prediction"]
        require((p is None) == (q is None), "MATRIX_MISSING_PREDICTION_CHANGED")
        delta = (q - p) * 100 if p is not None else None
        require(delta is None or math.isfinite(delta),
                "MATRIX_NONFINITE_PREDICTION_DELTA")
        rows.append({
            "symbol": key[0], "family": key[1],
            "baseline_probability": p, "research_probability": q,
            "probability_delta_percentage_points": delta,
            "feature_sha256_identical": True, "training_sha256_identical": True,
            "fitted_model_hash_identical":
                old["fitted_model_hash"] == new["fitted_model_hash"],
        })
    nums = [abs(r["probability_delta_percentage_points"])
            for r in rows if r["probability_delta_percentage_points"] is not None]
    parser = {v: {x["engine"]: x["status"] for x in d["parser_probe"]}
              for v, d in (("baseline", left), ("research", right))}
    return {
        "version": VERSION, "research_only": True,
        "production_writes": False, "live_execution": False,
        "strategy_promoted": False,
        "status": "CONTROLLED_REAL_INPUT_RUNTIME_MATRIX_RESEARCH_HOLD",
        "asof_session": left["asof_session"],
        "source_actions_run_id": BASELINE_RUN_ID,
        "input_manifest_sha256": left["real_source_manifest_sha256"],
        "model_code_sha256": left["code_file_sha256"],
        "compared_models": len(rows), "compared_core_symbols": 20,
        "input_feature_hash_mismatches": 0,
        "training_input_hash_mismatches": 0,
        "max_probability_delta_pp": max(nums) if nums else None,
        "model_probabilities_changed_over_1e_8_pp":
            sum(x > 1e-8 for x in nums),
        "model_probabilities_changed_over_1pp":
            sum(x > 1 for x in nums),
        "fitted_model_hash_changed": sum(
            not x["fitted_model_hash_identical"] for x in rows),
        "parser_status_by_variant": parser,
        "experimental_reproducibility": (
            "NUMERICAL_RUNTIME_SENSITIVITY_OBSERVED"
            if any(x > 1e-8 for x in nums)
            else "RUNTIME_MATRIX_NO_MODEL_DIFFERENCE_OBSERVED"),
        "cause_of_historical_20261120_drift_certified": False,
        "historic_first_seal_input_available": False,
        "independent_16et_official_price_certified": False,
        "model_or_trading_rules_changed": False,
        "rows": rows,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_subparsers(dest="mode", required=True)
    a = mode.add_parser("manifest")
    a.add_argument("--root", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--fixture", required=True)
    b = mode.add_parser("work")
    b.add_argument("--root", required=True)
    b.add_argument("--manifest", required=True)
    b.add_argument("--fixture", required=True)
    b.add_argument("--variant", choices=tuple(EXPECTED_PACKAGES), required=True)
    b.add_argument("--out", required=True)
    c = mode.add_parser("parser-probe")
    c.add_argument("--fixture", required=True)
    c.add_argument("--engine", choices=("c", "python"), required=True)
    c.add_argument("--iterations", type=int, default=150)
    d = mode.add_parser("compare")
    d.add_argument("--baseline", required=True)
    d.add_argument("--research", required=True)
    d.add_argument("--out", required=True)
    x = p.parse_args()
    if x.mode in ("manifest", "work"):
        from daily20 import load_spec
        spec = load_spec()
    if x.mode == "manifest":
        result = source_index(x.root, spec)
        result["parser_fixture_sha256"] = parser_fixture(x.fixture, spec)
        out = Path(x.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        print("DAILY20_MATRIX_MANIFEST", result["file_count"],
              "real files", result["asof_session"])
    elif x.mode == "work":
        raw = json.loads(Path(x.manifest).read_text())
        fixture_hash = raw.pop("parser_fixture_sha256", None)
        require(fixture_hash == filehash(x.fixture),
                "MATRIX_PARSER_FIXTURE_SOURCE_CHANGED")
        result = work(x.root, spec, raw, x.fixture, x.variant, output=x.out)
        print("DAILY20_MATRIX_VARIANT", x.variant, "models", 40,
              "parser", [z["status"] for z in result["parser_probe"]])
    elif x.mode == "parser-probe":
        print(json.dumps(probe_parser(x.fixture, x.engine, x.iterations)))
    else:
        a = json.loads(Path(x.baseline).read_text())
        b = json.loads(Path(x.research).read_text())
        result = compare(a, b)
        out = Path(x.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        print("DAILY20_MATRIX_COMPARE", result["compared_models"],
              "max_delta_pp", result["max_probability_delta_pp"],
              "numerical_changed", result["model_probabilities_changed_over_1e_8_pp"],
              "certified_cause", result["cause_of_historical_20261120_drift_certified"])


if __name__ == "__main__":
    main()
