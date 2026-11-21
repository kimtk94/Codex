#!/usr/bin/env python3
"""Daily20 prospective provenance snapshot and research-only replay drift gate.

Never rewrites existing sealed forecasts. Copies previous point-in-time
snapshots from a SHA-verified results ZIP, then freezes only genuinely NEW
forward signals. Drift is reported, never used to rewrite historical labels.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
import sklearn

from daily20 import load_bars, load_spec, market_file, write_json
from forward_shadow import check_events, read_score_rows, validate_prior_results_archive
from bear_forward import validate_bear_events
from provenance_audit import (
    COLUMNS, canonical, context_frame, feature_frame,
    fingerprint_feature_row, predict_on_frame, sha_bytes, value_or_null,
)

VERSION = "daily20-prospective-stability-v1"
SNAPSHOT_PREFIX = "research/stability/snapshots/"
HOLD_THRESHOLD_PP = 1.0


def _bool(v):
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    s = str(v).strip().lower()
    if s not in {"true", "false"}:
        raise RuntimeError("STABILITY_INVALID_BOOLEAN:" + s)
    return s == "true"


def _finite_probability(v):
    if v is None or pd.isna(v):
        return None
    n = float(v)
    if not np.isfinite(n) or n < 0 or n > 1:
        raise RuntimeError("STABILITY_INVALID_PROBABILITY")
    return n


def _json_file(path):
    return json.loads(Path(path).read_text())


def _digest(obj):
    return sha_bytes(canonical(obj).encode("utf-8"))


def _software_versions():
    software = {"python": platform.python_version(),
                "numpy": np.__version__, "pandas": pd.__version__,
                "scikit_learn": sklearn.__version__}
    for name in ("numpy", "pandas", "scikit-learn", "scipy", "pyarrow"):
        try:
            d = importlib.metadata.distribution(name)
            record = d.read_text("RECORD")
            software[name + "_installed_record_sha256"] = (
                sha_bytes(record.encode()) if record else None
            )
        except importlib.metadata.PackageNotFoundError:
            software[name + "_installed_record_sha256"] = None
    return software


def _read_journal(path):
    return [json.loads(t) for t in Path(path).read_text().splitlines() if t.strip()]


def _historical_snapshots(prior_bytes, spec):
    # This verifies EVERY ZIP member, not just the provenance files.
    validate_prior_results_archive(prior_bytes, set(spec["core"]))
    copied = {}
    with ZipFile(Path(prior_bytes) if not isinstance(prior_bytes, bytes)
                 else __import__("io").BytesIO(prior_bytes)) as z:
        for name in z.namelist():
            if not name.startswith(SNAPSHOT_PREFIX) or not name.endswith(".json"):
                continue
            date = name[len(SNAPSHOT_PREFIX):-5]
            if len(date) != 10 or date[4] != "-" or date[7] != "-":
                raise RuntimeError("STABILITY_INVALID_ARCHIVED_SNAPSHOT_PATH")
            blob = z.read(name)
            doc = json.loads(blob)
            if doc.get("schema") != VERSION or doc.get("session") != date:
                raise RuntimeError("STABILITY_INVALID_ARCHIVED_SNAPSHOT")
            copied[date] = blob
    return copied


def _bear_csv(path, session, symbols):
    frame = pd.read_csv(path)
    required = {"symbol", "family", "signal_date", "candidate", "probability"}
    if not required.issubset(frame.columns):
        raise RuntimeError("STABILITY_BEAR_CSV_SCHEMA")
    frame = frame[frame["signal_date"].astype(str).eq(session)]
    result = {}
    for row in frame.to_dict("records"):
        key = (row["symbol"], row["family"])
        if key in result:
            raise RuntimeError("STABILITY_DUPLICATE_BEAR_ROW")
        result[key] = {
            "probability": _finite_probability(row["probability"]),
            "candidate": _bool(row["candidate"]),
        }
    expected = {(s, f) for s in symbols for f in ("BEAR_LOGISTIC", "BEAR_RULE")}
    if set(result) != expected:
        raise RuntimeError("STABILITY_INCOMPLETE_BEAR_SCORES")
    return result


def make_current_snapshot(spec, market, features, bull_scores, bear_scores,
                          session, bull_signals, bear_signals):
    """Capture 26 close bars and the exact 21-column/model input for 20 symbols."""
    if len(COLUMNS) != 21:
        raise RuntimeError("STABILITY_FEATURE_SCHEMA_CHANGED")
    market, features = Path(market), Path(features)
    asset_prices = {}
    for symbol in [*spec["core"], *spec["context"]]:
        bars = load_bars(market_file(market, symbol))
        date = pd.Timestamp(session)
        if bars.empty or date != bars.index.max() or date not in bars.index:
            raise RuntimeError("STABILITY_ASOF_BAR_NOT_FINAL:" + symbol)
        row = bars.loc[date]
        if isinstance(row, pd.DataFrame):
            raise RuntimeError("STABILITY_DUPLICATE_BAR:" + symbol)
        asset_prices[symbol] = {
            field: value_or_null(row[field])
            for field in ("open", "high", "low", "close", "volume")
        }
        if any(v is None for v in asset_prices[symbol].values()):
            raise RuntimeError("STABILITY_NONFINITE_OHLCV:" + symbol)
    context = context_frame(market)
    records = {}
    for symbol in spec["core"]:
        bull = bull_signals.get((session, symbol))
        bl = bear_signals.get((session, symbol, "BEAR_LOGISTIC"))
        br = bear_signals.get((session, symbol, "BEAR_RULE"))
        if not (bull and bl and br):
            raise RuntimeError("STABILITY_MISSING_FROZEN_EVENTS:" + symbol)
        frame = feature_frame(symbol, market, features, context,
                              float(spec["round_trip_cost_bps"]))
        if frame.empty or frame.index.max() != pd.Timestamp(session):
            raise RuntimeError("STABILITY_FEATURE_DATE_MISMATCH:" + symbol)
        values = [value_or_null(frame.loc[pd.Timestamp(session), c]) for c in COLUMNS]
        row_hash = fingerprint_feature_row(frame, session)
        models = {}
        for family in ("BULL_LOGISTIC", "BEAR_LOGISTIC"):
            result = predict_on_frame(frame, session, family)
            models[family] = {key: result[key] for key in (
                "prediction", "fold_status", "training_rows",
                "training_hash", "fitted_model_hash"
            )}
        bull_now = bull_scores[symbol]
        bear_now = bear_scores[(symbol, "BEAR_LOGISTIC")]
        rule_now = bear_scores[(symbol, "BEAR_RULE")]
        if models["BULL_LOGISTIC"]["prediction"] is None:
            raise RuntimeError("STABILITY_MISSING_BULL_ESTIMATOR:" + symbol)
        for name, observed in (
            ("BULL_LOGISTIC", bull_now["probability"]),
            ("BEAR_LOGISTIC", bear_now["probability"]),
        ):
            predicted = models[name]["prediction"]
            if (predicted is None) != (observed is None) or (
                predicted is not None and abs(predicted - observed) > 1e-7
            ):
                raise RuntimeError("STABILITY_CURRENT_SCORE_NOT_REPRODUCIBLE:"
                                   + symbol + ":" + name)
        records[symbol] = {
            "ohlcv": asset_prices[symbol],
            "feature_columns": list(COLUMNS),
            "feature_values": values,
            "feature_sha256": row_hash,
            "models": models,
            "scored": {
                "BULL_LOGISTIC": {"probability": bull_now["probability"],
                                  "candidate": bull_now["candidate"]},
                "BEAR_LOGISTIC": bear_now,
                "BEAR_RULE": rule_now,
            },
            "frozen_signal_hashes": {
                "BULL_LOGISTIC": bull["hash"],
                "BEAR_LOGISTIC": bl["hash"],
                "BEAR_RULE": br["hash"],
            },
        }
    return {
        "schema": VERSION, "session": session,
        "research_only": True, "production_writes": False,
        "source_actions_run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "source_sha": os.environ.get("GITHUB_SHA", "local"),
        "price_26": asset_prices,
        "price_26_sha256": _digest(asset_prices),
        "software": _software_versions(),
        "models": records,
        "model_count": 40,
        "rule_count": 20,
        "feature_count": 21,
        "training_cutoff_exclusive": str(pd.Timestamp(session).year) + "-01-01",
    }


def classify(frozen, current, *, threshold_pp=HOLD_THRESHOLD_PP):
    """Separate material model drift from informational price/feature revision."""
    events = []
    if frozen is not None:
        base = frozen["models"]
        for symbol, new in current["models"].items():
            old = base[symbol]
            for family in ("BULL_LOGISTIC", "BEAR_LOGISTIC", "BEAR_RULE"):
                o, n = old["scored"][family], new["scored"][family]
                prob_a, prob_b = o["probability"], n["probability"]
                delta = ((prob_b - prob_a) * 100
                         if prob_a is not None and prob_b is not None else None)
                flip = o["candidate"] != n["candidate"]
                missing = (prob_a is None) != (prob_b is None)
                changed = (old["feature_sha256"] != new["feature_sha256"]
                           or old["ohlcv"] != new["ohlcv"])
                material = bool(flip or missing or
                                (delta is not None and abs(delta) > threshold_pp + 1e-10))
                if material or changed or (delta is not None and abs(delta) > 1e-8):
                    events.append({
                        "symbol": symbol, "family": family,
                        "probability_delta_pp": delta, "candidate_flip": flip,
                        "probability_missing_changed": missing,
                        "asof_input_changed": changed,
                        "training_input_changed": (
                            old["models"].get(family, {}).get("training_hash") !=
                            new["models"].get(family, {}).get("training_hash")
                        ),
                        "coefficient_changed": (
                            old["models"].get(family, {}).get("fitted_model_hash") !=
                            new["models"].get(family, {}).get("fitted_model_hash")
                        ),
                        "research_hold": material,
                    })
    return events, any(e["research_hold"] for e in events)


def run(spec, prior_zip, market, features, score_path, bear_csv,
        bull_journal, bear_journal, bull_report, bear_report, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    qc_date = str(_json_file(bull_report)["last_completed_session"])
    b_report = _json_file(bear_report)
    if b_report["last_completed_session"] != qc_date:
        raise RuntimeError("STABILITY_REPORT_SESSION_MISMATCH")
    bull_signals, _ = check_events(_read_journal(bull_journal), set(spec["core"]))
    bear_signals, _ = validate_bear_events(_read_journal(bear_journal), set(spec["core"]))
    existing = _historical_snapshots(Path(prior_zip).read_bytes(), spec)
    scores = read_score_rows(score_path, spec, qc_date)
    bear_now = _bear_csv(bear_csv, qc_date, spec["core"])
    current = make_current_snapshot(spec, market, features, scores, bear_now,
                                    qc_date, bull_signals, bear_signals)
    previous = json.loads(existing[qc_date]) if qc_date in existing else None

    b_new = _json_file(bull_report)["new_signal_events"]
    r_new = b_report["new_signal_events"]
    if (b_new, r_new) not in ((0, 0), (20, 40)):
        raise RuntimeError("STABILITY_PARTIAL_SEAL_REJECTED")
    if b_new and previous is not None:
        raise RuntimeError("STABILITY_EXISTING_FROZEN_SESSION_RESEALED")
    if b_new:
        for symbol in spec["core"]:
            for family, event in (
                ("BULL_LOGISTIC", bull_signals[(qc_date, symbol)]),
                ("BEAR_LOGISTIC", bear_signals[(qc_date, symbol, "BEAR_LOGISTIC")]),
                ("BEAR_RULE", bear_signals[(qc_date, symbol, "BEAR_RULE")]),
            ):
                now = current["models"][symbol]["scored"][family]
                if (now["candidate"] != event["candidate"] or
                    (now["probability"] is None) != (event["probability"] is None) or
                    (now["probability"] is not None and
                     abs(now["probability"] - event["probability"]) > 1e-9)):
                    raise RuntimeError("STABILITY_INITIAL_SEAL_NOT_IDENTICAL:" + symbol)
        payload = (canonical(current) + "\n").encode()
        existing[qc_date] = payload
    elif previous is not None:
        # Integrity is checked in the manifest, and the original bytes WIN.
        pass
    # Legacy journal dates have no original model-input anchor. Their new
    # retrospective features are diagnostic only, never falsely "frozen".
    incidents, hold = classify(previous, current)
    if previous is None and not b_new:
        # Crosscheck original frozen event probabilities even on pre-v1 days.
        for symbol in spec["core"]:
            for family, event in (
                ("BULL_LOGISTIC", bull_signals[(qc_date, symbol)]),
                ("BEAR_LOGISTIC", bear_signals[(qc_date, symbol, "BEAR_LOGISTIC")]),
                ("BEAR_RULE", bear_signals[(qc_date, symbol, "BEAR_RULE")]),
            ):
                now = current["models"][symbol]["scored"][family]
                old_p, new_p = event["probability"], now["probability"]
                delta = ((new_p - old_p) * 100 if
                         old_p is not None and new_p is not None else None)
                bad = (event["candidate"] != now["candidate"] or
                       (old_p is None) != (new_p is None) or
                       (delta is not None and abs(delta) > HOLD_THRESHOLD_PP + 1e-10))
                if bad:
                    hold = True
                    incidents.append({
                        "symbol": symbol, "family": family,
                        "candidate_flip": event["candidate"] != now["candidate"],
                        "probability_delta_pp": delta,
                        "legacy_event_only_no_original_feature_snapshot": True,
                        "research_hold": True,
                    })
    for session, payload in existing.items():
        (out / "snapshots" / (session + ".json")).parent.mkdir(parents=True, exist_ok=True)
        (out / "snapshots" / (session + ".json")).write_bytes(payload)
    report = {
        "version": VERSION, "session": qc_date,
        "status": ("REPLAY_DRIFT_RESEARCH_HOLD" if hold else
                   "SEALED_NEW_SESSION" if b_new else
                   "REPLAY_AUDITED_WITH_FROZEN_SNAPSHOT" if previous else
                   "LEGACY_NO_ORIGINAL_FEATURE_SNAPSHOT"),
        "research_only": True, "production_writes": False,
        "strategy_promoted": False, "promotional_attribution_allowed": False,
        "research_hold": bool(hold),
        "drift_threshold_percentage_points_exclusive": HOLD_THRESHOLD_PP,
        "new_sealed_bull_signals": b_new, "new_sealed_bear_signals": r_new,
        "frozen_sessions_preserved": len(existing),
        "current_session_has_original_snapshot": bool(previous is not None or b_new),
        "current_snapshot_sha256": _digest(current),
        "frozen_snapshot_sha256": (
            sha_bytes(existing[qc_date]) if qc_date in existing else None),
        "incidents": incidents,
        "incidents_count": len(incidents),
        "no_live_orders": True,
        "warning": "This does not establish Yahoo point-in-time market truth or future performance.",
    }
    write_json(out / "report.json", report)
    print(json.dumps({"DAILY20_STABILITY": {
        "status": report["status"], "hold": hold,
        "incidents": len(incidents), "frozen_days": len(existing)
    }}))
    return report


def main():
    ap = argparse.ArgumentParser()
    for name in ("prior-zip", "market", "features", "scores", "bear-csv",
                 "bull-journal", "bear-journal", "bull-report", "bear-report", "out"):
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--config", default="research/kalman_daily20/universe.json")
    a = ap.parse_args()
    run(load_spec(a.config), a.prior_zip, a.market, a.features, a.scores,
        a.bear_csv, a.bull_journal, a.bear_journal,
        a.bull_report, a.bear_report, a.out)


if __name__ == "__main__":
    main()
