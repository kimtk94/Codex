#!/usr/bin/env python3
"""Deep, dependency-free first-seal verification against original signed journals.

Verifies recorded evidence consistency, not provider accuracy, positive alpha,
an exchange-certified close, or the original snapshot of a legacy forecast.
Only genuinely prospective snapshots (2026-11-23 or later) are covered.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
import math
import re

VERSION = "daily20-prospective-first-seal-proof-v1"
FIRST_ELIGIBLE = "2026-11-23"
CORE = (
    "SPY", "QQQ", "QLD", "IWM", "AAPL", "MSFT", "AMZN", "GOOGL", "META",
    "NVDA", "AMD", "AVGO", "MU", "TSLA", "PLTR", "IONQ", "COIN", "MSTR",
    "JPM", "XOM",
)
CONTEXT = ("SMH", "^VIX", "HYG", "LQD", "TLT", "GLD")
COLS = (
    "ret1", "ret5", "ret20", "sma20_gap", "sma50_gap", "sma200_gap",
    "volume_z20", "rsi14", "macd_hist", "adx14", "natr14", "roc10",
    "bb_pctb", "spy_mom5_lag", "spy_above200_lag", "qqq_mom5_lag",
    "smh_relative_lag", "credit_mom5_lag", "vix_lag", "tlt_mom5_lag",
    "gld_mom5_lag",
)
FAMILIES = ("BULL_LOGISTIC", "BEAR_LOGISTIC", "BEAR_RULE")
HASH_RE = re.compile(r"^[a-f0-9]{64}$")
JOURNALS = {
    "BULL_LOGISTIC": "research/forward_shadow/journal.jsonl",
    "BEAR_LOGISTIC": "research/bear_forward/journal.jsonl",
    "BEAR_RULE": "research/bear_forward/journal.jsonl",
}
ROOT_HASH = "0" * 64


def ensure(cond, code):
    if not cond:
        raise RuntimeError("FIRST_SEAL_" + code)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(obj):
    return sha256(canonical(obj).encode()).hexdigest()


def is_hash(value):
    return isinstance(value, str) and HASH_RE.fullmatch(value) is not None


def valid_num(value, *, positive=False, nonnegative=False):
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        return False
    return ((value > 0) if positive else
            (value >= 0) if nonnegative else True)


def prob(value, *, optional=False):
    return (value is None and optional or
            valid_num(value, nonnegative=True) and value <= 1)


def _event_index(z, members, name, family):
    ensure(name in members, "ORIGINAL_JOURNAL_MISSING")
    body = z.read(name)
    ensure(len(body) <= 5_000_000, "ORIGINAL_JOURNAL_OVERSIZE")
    previous = ROOT_HASH
    signals = {}
    for i, line in enumerate(body.splitlines(), 1):
        try:
            event = json.loads(line)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("FIRST_SEAL_JOURNAL_JSON_INVALID") from exc
        ensure(isinstance(event, dict) and event.get("seq") == i and
               event.get("prev_hash") == previous and
               is_hash(event.get("hash")) and
               event["hash"] == fingerprint({k: v for k, v in event.items()
                                             if k != "hash"}),
               "ORIGINAL_JOURNAL_HASH_CHAIN_BROKEN")
        previous = event["hash"]
        if event.get("kind") != "SIGNAL":
            continue
        ensure(event.get("research_only") is True, "JOURNAL_NOT_RESEARCH_ONLY")
        if family == "BULL":
            ensure(event.get("symbol") in CORE, "JOURNAL_UNKNOWN_SYMBOL")
            key = (event.get("signal_date"), event["symbol"], "BULL_LOGISTIC")
        else:
            ensure(event.get("symbol") in CORE and
                   event.get("family") in ("BEAR_LOGISTIC", "BEAR_RULE"),
                   "JOURNAL_INVALID_BEAR_FAMILY")
            key = (event.get("signal_date"), event["symbol"], event["family"])
        ensure(key not in signals, "DUPLICATE_FROZEN_EVENT")
        signals[key] = event
    return signals


def attest_snapshot(snapshot, day, bull, bear):
    ensure(isinstance(snapshot, dict) and
           snapshot.get("schema") == "daily20-prospective-stability-v1" and
           snapshot.get("session") == day and
           snapshot.get("research_only") is True and
           snapshot.get("production_writes") is False,
           "ORIGINAL_SNAPSHOT_GOVERNANCE")
    ensure(isinstance(snapshot.get("source_actions_run_id"), str) and
           snapshot["source_actions_run_id"] and
           isinstance(snapshot.get("source_sha"), str) and
           snapshot["source_sha"],
           "ORIGINAL_RUN_OR_COMMIT_MISSING")
    ensure(snapshot.get("model_count") == 40 and
           snapshot.get("rule_count") == 20 and
           snapshot.get("feature_count") == 21 and
           snapshot.get("training_cutoff_exclusive") == day[:4] + "-01-01",
           "ORIGINAL_MODEL_FEATURE_COUNTS")
    software = snapshot.get("software")
    ensure(isinstance(software, dict) and
           all(isinstance(software.get(k), str) and software[k]
               for k in ("python", "numpy", "pandas", "scikit_learn")),
           "ORIGINAL_ENVIRONMENT_MISSING")
    prices = snapshot.get("price_26")
    ensure(isinstance(prices, dict) and
           set(prices) == set(CORE + CONTEXT) and
           snapshot.get("price_26_sha256") == fingerprint(prices),
           "26_PRICE_DIGEST_OR_SYMBOL_COVERAGE")
    for symbol, item in prices.items():
        ensure(isinstance(item, dict) and
               all(k in item and valid_num(item[k], positive=k != "volume",
                                           nonnegative=k == "volume")
                   for k in ("open", "high", "low", "close", "volume")),
               "PRICE_OHLCV_INVALID:" + symbol)
        ensure(item["low"] <= min(item["open"], item["close"]) and
               item["high"] >= max(item["open"], item["close"]) and
               item["low"] <= item["high"],
               "PRICE_OHLCV_RELATION_INVALID:" + symbol)
    models = snapshot.get("models")
    ensure(isinstance(models, dict) and set(models) == set(CORE),
           "20_MODEL_SYMBOLS_MISSING")
    observed_hashes = []
    for symbol in CORE:
        row = models[symbol]
        ensure(isinstance(row, dict) and row.get("ohlcv") == prices[symbol],
               "CORE_PRICE_INPUT_MISMATCH:" + symbol)
        feature_names = row.get("feature_columns")
        features = row.get("feature_values")
        ensure(feature_names == list(COLS) and
               isinstance(features, list) and len(features) == 21 and
               all(v is None or valid_num(v) for v in features) and
               row.get("feature_sha256") == fingerprint(features),
               "FEATURE_21_VALUES_OR_HASH_INVALID:" + symbol)
        fitted = row.get("models")
        scored = row.get("scored")
        anchors = row.get("frozen_signal_hashes")
        ensure(isinstance(fitted, dict) and set(fitted) ==
               {"BULL_LOGISTIC", "BEAR_LOGISTIC"} and
               isinstance(scored, dict) and set(scored) == set(FAMILIES) and
               isinstance(anchors, dict) and set(anchors) == set(FAMILIES),
               "MODEL_AND_EVENT_FAMILIES_INCOMPLETE:" + symbol)
        for family in ("BULL_LOGISTIC", "BEAR_LOGISTIC"):
            m = fitted[family]
            ensure(isinstance(m, dict) and is_hash(m.get("training_hash")) and
                   type(m.get("training_rows")) is int and
                   m["training_rows"] >= 0 and
                   isinstance(m.get("fold_status"), str) and m["fold_status"] and
                   prob(m.get("prediction"), optional=(family == "BEAR_LOGISTIC")) and
                   ((m.get("fitted_model_hash") is None and m["prediction"] is None)
                    or (is_hash(m.get("fitted_model_hash")) and
                        m["prediction"] is not None)),
                   "TRAINING_OR_FITTED_MODEL_DIGEST_INVALID:" + symbol)
        for family in FAMILIES:
            event = (bull if family == "BULL_LOGISTIC" else bear).get(
                (day, symbol, family))
            ensure(event is not None and is_hash(anchors[family]) and
                   event["hash"] == anchors[family],
                   "ORIGINAL_EVENT_HASH_ANCHOR_MISMATCH:" + symbol + ":" + family)
            ensure(event.get("source_actions_run_id") ==
                   snapshot["source_actions_run_id"] and
                   event.get("source_sha") == snapshot["source_sha"],
                   "ORIGINAL_EVENT_CAPTURE_RUN_MISMATCH:" + symbol + ":" + family)
            if family != "BULL_LOGISTIC":
                ensure(event.get("baseline_signal_hash") ==
                       bull[(day, symbol, "BULL_LOGISTIC")]["hash"],
                       "BEAR_EVENT_BULL_BASELINE_LINK_MISMATCH:" + symbol)
            score = scored[family]
            ensure(isinstance(score, dict) and
                   type(score.get("candidate")) is bool and
                   score["candidate"] is event.get("candidate") and
                   prob(score.get("probability"), optional=family != "BULL_LOGISTIC") and
                   (score.get("probability") is None) ==
                   (event.get("probability") is None),
                   "SCORING_AND_ORIGINAL_EVENT_CONFLICT:" + symbol + ":" + family)
            if score["probability"] is not None:
                ensure(abs(score["probability"] - event["probability"]) <= 1e-9,
                       "SCORING_PROBABILITY_CHANGED:" + symbol + ":" + family)
            if family != "BEAR_RULE":
                ensure(score.get("probability") ==
                       fitted[family].get("prediction") or
                       (score["probability"] is not None and
                        fitted[family].get("prediction") is not None and
                        abs(score["probability"] -
                            fitted[family]["prediction"]) <= 1e-7),
                       "MODEL_PREDICTION_SCORED_INCONSISTENT:" + symbol)
            if family == "BEAR_RULE":
                ensure(score["probability"] is None,
                       "RULE_PROBABILITY_MUST_BE_NULL")
            observed_hashes.append(anchors[family])
    captured = snapshot.get("source_finality_at_capture")
    ensure(isinstance(captured, dict) and
           captured.get("provisional") is True and
           captured.get("verified") == 0 and
           captured.get("required") == 26 and
           captured.get("research_hold") is True and
           captured.get("status") in ("SOURCE_FINALITY_HOLD",
                                      "REPLAY_DRIFT_RESEARCH_HOLD") and
           is_hash(captured.get("evidence_sha256")),
           "SOURCE_FINALITY_AT_FIRST_SEAL_NOT_HOLD")
    return {
        "session": day,
        "price_26_sha256": snapshot["price_26_sha256"],
        "source_actions_run_id": snapshot["source_actions_run_id"],
        "original_signal_hash_count": len(observed_hashes),
        "core_feature_rows_verified": 20,
        "model_input_fingerprints_verified": 40,
        "unverified_source_finality_at_capture": True,
    }


def verify_archive_prospective_seals(z, names, snapshot_days):
    """Called only after every ZIP member SHA-256 is independently checked."""
    prospective = sorted(day for day in snapshot_days if day >= FIRST_ELIGIBLE)
    if not prospective:
        return {"version": VERSION, "prospective_seals_attested": 0,
                "status": "AWAITING_GENUINE_NEW_SESSION",
                "first_genuine_seal_not_backfilled": True,
                "research_only": True, "source_finality_certified": False,
                "seals": []}
    names = set(names)
    bull = _event_index(z, names, JOURNALS["BULL_LOGISTIC"], "BULL")
    bear = _event_index(z, names, JOURNALS["BEAR_RULE"], "BEAR")
    reports = []
    for day in prospective:
        name = "research/stability/snapshots/" + day + ".json"
        ensure(name in names, "FROZEN_SNAPSHOT_FILE_MISSING")
        obj = json.loads(z.read(name))
        reports.append(attest_snapshot(obj, day, bull, bear))
    return {
        "version": VERSION, "prospective_seals_attested": len(reports),
        "status": "NEW_SESSION_ORIGINAL_INPUTS_AND_EVENTS_ATTESTED_RESEARCH_HOLD",
        "first_genuine_seal_not_backfilled": True,
        "research_only": True, "source_finality_certified": False,
        "seals": reports,
    }
