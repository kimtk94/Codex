from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.base import clone

from r8_1_sec_ablation import (
    BASE_FEATURES,
    RESEARCH_CUTOFF,
    build_training_rows,
    sha256_file,
)
from r9_news_features import (
    FEATURE_READY_SIGNAL_DAY,
    NEWS_FEATURES,
    attach_news_features,
    build_daily_features,
)

SCHEMA = "kalman-r9-2-prospective-model-freeze-v1"
CANDIDATE = "R9P_NGRAM_ATTENTION_FROZEN"
PROSPECTIVE_START = pd.Timestamp("2026-09-24T13:30:00Z")
CONFIRM = "CONFIRM_R9_2_PROSPECTIVE_FREEZE"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Freeze/verify the R9.2 prospective HGB model")
    root = Path(os.getenv("KALMAN_DATA_ROOT", "/mnt/gdrive"))
    state = Path(
        os.getenv(
            "R9_NEWS_STATE_DIR",
            str(Path.home() / ".local/state/kalman/r9_news_ngram"),
        )
    )
    p.add_argument("--root", default=str(root))
    p.add_argument("--mentions", default=str(state / "r9_ngram_historical.csv"))
    p.add_argument("--verify-only", action="store_true")
    return p.parse_args()


def nowiso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, obj: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _verify_manifest(manifest_path: Path) -> dict:
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    if m.get("schema") != SCHEMA:
        raise RuntimeError(f"unexpected R9.2 freeze schema: {m.get('schema')}")
    if m.get("candidate") != CANDIDATE:
        raise RuntimeError("R9.2 candidate drift")
    if pd.Timestamp(m["prospective_start"]) != PROSPECTIVE_START:
        raise RuntimeError("R9.2 prospective boundary drift")
    if m.get("production_enabled") is not False:
        raise RuntimeError("R9.2 production invariant violated")
    if m.get("refit_allowed") is not False:
        raise RuntimeError("R9.2 refit invariant violated")

    base = manifest_path.parent
    for name, expected in (m.get("artifacts") or {}).items():
        p = base / name
        if not p.exists():
            raise FileNotFoundError(p)
        actual = sha256_file(p)
        if actual != expected:
            raise RuntimeError(f"R9.2 artifact hash mismatch: {name}")

    return m


def main() -> int:
    a = parse_args()
    root = Path(a.root)
    us = root / "US_ETF"
    state_mentions = Path(a.mentions)

    r501 = us / "model_lab_v1/results/r5_0_1_research_sandbox_all_data"
    r91 = us / "model_lab_v1/results/r9_1_ngram_attention"
    out = us / "model_lab_v1/results/r9_2_prospective_shadow/model_freeze"
    out.mkdir(parents=True, exist_ok=True)

    template_path = r501 / "model_freeze/r5_hgb.joblib"
    r5_manifest_path = r501 / "model_freeze/r5_1_model_freeze_manifest.json"
    r91_decision_path = r91 / "r9_1_selection_decision.json"

    model_path = out / "r9_2_hgb.joblib"
    medians_path = out / "r9_2_training_medians.json"
    manifest_path = out / "r9_2_model_freeze_manifest.json"

    if manifest_path.exists():
        m = _verify_manifest(manifest_path)
        print(json.dumps({"status": "VERIFIED_EXISTING_FREEZE", **m}, indent=2, default=str))
        return 0

    if a.verify_only:
        raise FileNotFoundError("R9.2 freeze manifest does not exist")

    if os.getenv("R9_2_FREEZE_MODEL") != "YES":
        raise RuntimeError("set R9_2_FREEZE_MODEL=YES for the one-time freeze")
    if os.getenv("R9_2_FREEZE_CONFIRM") != CONFIRM:
        raise RuntimeError(f"set R9_2_FREEZE_CONFIRM={CONFIRM}")

    for p in (template_path, r5_manifest_path, r91_decision_path, state_mentions):
        if not p.exists():
            raise FileNotFoundError(p)

    r5_manifest = json.loads(r5_manifest_path.read_text(encoding="utf-8"))
    if r5_manifest.get("selected_primary") != "R5C0_HGB_REFERENCE":
        raise RuntimeError("unexpected R5.1 template lineage")
    if r5_manifest.get("production_enabled") is not False:
        raise RuntimeError("R5.1 freeze invariant drift")

    r91 = json.loads(r91_decision_path.read_text(encoding="utf-8"))
    if r91.get("schema") != "kalman-r9-1-ngram-attention-ablation-v1":
        raise RuntimeError("unexpected R9.1 result schema")
    if r91.get("candidate") != "R9C1_NGRAM_ATTENTION":
        raise RuntimeError("unexpected R9.1 candidate")
    if r91.get("post_result_tuning_allowed") is not False:
        raise RuntimeError("R9.1 no-tuning invariant drift")
    if list(r91.get("news_features") or []) != list(NEWS_FEATURES):
        raise RuntimeError("R9.1 news feature contract drift")

    scored_path = r501 / "r5_0_1_scored_rows.parquet"
    scored = pd.read_parquet(
        scored_path,
        columns=["symbol"],
    )
    symbols = sorted(scored["symbol"].astype(str).unique())
    if len(symbols) != 93:
        raise RuntimeError(f"expected 93 symbols, got {len(symbols)}")

    train = build_training_rows(root, symbols)
    mentions = pd.read_csv(state_mentions)
    daily = build_daily_features(mentions, symbols)
    train, news_audit = attach_news_features(train, daily)

    train = train.loc[
        (train["timestamp"] >= FEATURE_READY_SIGNAL_DAY)
        & (train["target_timestamp_4b"] < RESEARCH_CUTOFF)
    ].copy()
    if train.empty:
        raise RuntimeError("no R9.2 training rows")
    if train[NEWS_FEATURES].isna().any().any():
        raise RuntimeError("R9.2 frozen news features contain missing values")

    features = list(BASE_FEATURES) + list(NEWS_FEATURES)
    medians = train[features].median()
    if medians.isna().any():
        raise RuntimeError("R9.2 training medians contain NaN")

    template = joblib.load(template_path)
    model = clone(template)
    model.fit(
        train[features].fillna(medians),
        pd.to_numeric(train["relative_ret_4b"], errors="raise"),
    )

    # Write artifacts only after the complete deterministic fit succeeds.
    tmp_model = model_path.with_suffix(".joblib.tmp")
    joblib.dump(model, tmp_model)
    os.replace(tmp_model, model_path)

    _atomic_json(
        medians_path,
        {k: float(v) for k, v in medians.items()},
    )

    manifest = {
        "schema": SCHEMA,
        "frozen_at_utc": nowiso(),
        "candidate": CANDIDATE,
        "research_cutoff": RESEARCH_CUTOFF.isoformat(),
        "prospective_start": PROSPECTIVE_START.isoformat(),
        "train_rows": int(len(train)),
        "train_first_timestamp": str(train["timestamp"].min()),
        "train_last_feature_timestamp": str(train["timestamp"].max()),
        "train_last_target_timestamp": str(train["target_timestamp_4b"].max()),
        "features": features,
        "base_features": list(BASE_FEATURES),
        "news_features": list(NEWS_FEATURES),
        "target": "relative_ret_4b",
        "source": "GDELT_BIGQUERY_WEB_1GRAMS_2GRAMS",
        "pit_contract": (
            "signal_as_of=timestamp+60m; "
            "news_day_used=UTC day strictly before signal day"
        ),
        "news_audit_before_feature_ready_filter": news_audit,
        "r5_template_manifest_sha256": sha256_file(r5_manifest_path),
        "r5_template_model_sha256": sha256_file(template_path),
        "r9_1_result_sha256": sha256_file(r91_decision_path),
        "training_mentions_sha256": sha256_file(state_mentions),
        "artifacts": {
            model_path.name: sha256_file(model_path),
            medians_path.name: sha256_file(medians_path),
        },
        "production_enabled": False,
        "live_execution": False,
        "strategy_signal_write": False,
        "refit_allowed": False,
    }
    _atomic_json(manifest_path, manifest)
    _verify_manifest(manifest_path)

    print(json.dumps({"status": "FROZEN", **manifest}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
