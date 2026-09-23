from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from r8_1_sec_ablation import BASE_FEATURES
from r9_news_features import NEWS_FEATURES, attach_news_features
from r9_2_prospective_shadow import (
    MIN_COVERAGE,
    PROSPECTIVE_START,
    atomic_json,
    atomic_parquet,
    build_live_panel,
    build_news_daily,
    load_source_state,
    readpq,
    reconcile_features,
    sha256_file,
    stable_hash,
    verify_freeze,
)

SCHEMA = "kalman-r9-2-preboundary-diagnostic-v1"
DIAGNOSTIC_ID = "R9D_PREBOUNDARY_20260923"
DIAGNOSTIC_START = pd.Timestamp("2026-09-23T13:30:00Z")
DIAGNOSTIC_END_EXCLUSIVE = PROSPECTIVE_START
REQUIRED_NEWS_DAY = pd.Timestamp("2026-09-22T00:00:00Z")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run isolated R9.2 pre-boundary diagnostic for 2026-09-23"
    )
    root = Path(os.getenv("KALMAN_DATA_ROOT", "/mnt/gdrive"))
    state = Path(
        os.getenv(
            "R9_NEWS_STATE_DIR",
            str(Path.home() / ".local/state/kalman/r9_news_ngram"),
        )
    )
    p.add_argument("--root", default=str(root))
    p.add_argument(
        "--news-history",
        default=str(state / "r9_ngram_shadow_history.csv"),
    )
    p.add_argument(
        "--source-state",
        default=str(state / "r9_shadow_source_state.json"),
    )
    return p.parse_args()


def _load_frozen_models(us: Path):
    out = us / "model_lab_v1/results/r9_2_prospective_shadow"
    freeze_dir = out / "model_freeze"
    r9_manifest_path = freeze_dir / "r9_2_model_freeze_manifest.json"
    r9_model_path = freeze_dir / "r9_2_hgb.joblib"
    r9_medians_path = freeze_dir / "r9_2_training_medians.json"

    r9_manifest = verify_freeze(r9_manifest_path)
    r9_model = joblib.load(r9_model_path)
    r9_medians = pd.Series(
        json.loads(r9_medians_path.read_text(encoding="utf-8")),
        dtype=float,
    )

    r501 = us / "model_lab_v1/results/r5_0_1_research_sandbox_all_data"
    r5_manifest_path = r501 / "model_freeze/r5_1_model_freeze_manifest.json"
    r5_model_path = r501 / "model_freeze/r5_hgb.joblib"
    r5_medians_path = r501 / "model_freeze/r5_training_medians.json"

    r5_manifest = json.loads(r5_manifest_path.read_text(encoding="utf-8"))
    if r5_manifest.get("selected_primary") != "R5C0_HGB_REFERENCE":
        raise RuntimeError("R5.1 frozen lineage drift")
    if r5_manifest.get("production_enabled") is not False:
        raise RuntimeError("R5.1 production invariant drift")
    for name, expected in (r5_manifest.get("artifacts") or {}).items():
        p = r501 / "model_freeze" / name
        if not p.exists() or sha256_file(p) != expected:
            raise RuntimeError(f"R5.1 frozen artifact mismatch: {name}")

    r5_model = joblib.load(r5_model_path)
    r5_medians = pd.Series(
        json.loads(r5_medians_path.read_text(encoding="utf-8")),
        dtype=float,
    )
    return {
        "r9_manifest": r9_manifest,
        "r9_manifest_path": r9_manifest_path,
        "r9_model": r9_model,
        "r9_medians": r9_medians,
        "r5_model": r5_model,
        "r5_model_path": r5_model_path,
        "r5_medians": r5_medians,
        "r501": r501,
        "out": out,
    }


def _append_immutable(
    path: Path,
    rows: pd.DataFrame,
) -> pd.DataFrame:
    old = readpq(path)
    if rows.empty:
        return old
    rows = rows.copy()
    if rows["diagnostic_key"].duplicated().any():
        raise RuntimeError("duplicate diagnostic_key in new diagnostic rows")

    if not old.empty:
        if old["diagnostic_key"].duplicated().any():
            raise RuntimeError("duplicate diagnostic_key in existing diagnostic log")
        overlap = rows.merge(
            old[["diagnostic_key", "decision_hash"]],
            on="diagnostic_key",
            how="inner",
            suffixes=("_new", "_old"),
        )
        if len(overlap) and not (
            overlap["decision_hash_new"] == overlap["decision_hash_old"]
        ).all():
            raise RuntimeError(
                "pre-boundary diagnostic changed for an existing timestamp"
            )
        rows = rows.loc[~rows["diagnostic_key"].isin(old["diagnostic_key"])]

    out = pd.concat([old, rows], ignore_index=True)
    if len(out):
        out = out.sort_values("timestamp").reset_index(drop=True)
    atomic_parquet(out, path)
    return out


def _score_timestamp(
    z: pd.DataFrame,
    ts: pd.Timestamp,
    news_daily: pd.DataFrame,
    last_complete_day: pd.Timestamp,
    frozen: dict,
) -> dict:
    valid = z.dropna(
        subset=[
            "rv_24",
            "ma_dist_24",
            "volume_z_24",
            "bar_range",
            "qqq_rv_24",
            "qqq_ma_dist_24",
        ]
    ).copy()
    if valid.empty:
        raise RuntimeError(f"no eligible base rows at {ts}")

    signal_as_of = ts + pd.Timedelta(1, unit="h")
    news_day_used = signal_as_of.floor("D") - pd.Timedelta(1, unit="D")
    if news_day_used != REQUIRED_NEWS_DAY:
        raise RuntimeError(
            f"diagnostic news day drift at {ts}: "
            f"{news_day_used.date()} != {REQUIRED_NEWS_DAY.date()}"
        )
    if news_day_used > last_complete_day:
        raise RuntimeError(
            f"NGram source incomplete: need {news_day_used.date()}, "
            f"have {last_complete_day.date()}"
        )

    valid, news_audit = attach_news_features(valid, news_daily)
    valid = valid.loc[valid[NEWS_FEATURES].notna().all(axis=1)].copy()
    coverage = int(valid["symbol"].nunique())
    if coverage < MIN_COVERAGE:
        raise RuntimeError(f"diagnostic coverage {coverage} < {MIN_COVERAGE}")

    r9_features = list(BASE_FEATURES) + list(NEWS_FEATURES)
    valid["R9_SCORE"] = frozen["r9_model"].predict(
        valid[r9_features].fillna(frozen["r9_medians"])
    )
    valid["R5_SCORE"] = frozen["r5_model"].predict(
        valid[list(BASE_FEATURES)].fillna(frozen["r5_medians"])
    )

    r9_rank = valid.sort_values(
        ["R9_SCORE", "symbol"], ascending=[False, True]
    ).reset_index(drop=True)
    r5_rank = valid.sort_values(
        ["R5_SCORE", "symbol"], ascending=[False, True]
    ).reset_index(drop=True)

    r9 = r9_rank.iloc[0]
    r5 = r5_rank.iloc[0]

    r9_weight = (
        float(
            np.clip(
                r9["universe_median_rv_24"] / r9["rv_24"],
                0.25,
                1.0,
            )
        )
        if float(r9["rv_24"]) > 0
        else 1.0
    )
    r5_weight = (
        float(
            np.clip(
                r5["universe_median_rv_24"] / r5["rv_24"],
                0.25,
                1.0,
            )
        )
        if float(r5["rv_24"]) > 0
        else 1.0
    )

    spearman = float(
        pd.Series(valid["R9_SCORE"].to_numpy()).corr(
            pd.Series(valid["R5_SCORE"].to_numpy()),
            method="spearman",
        )
    )
    top10_overlap = int(
        len(set(r9_rank.head(10)["symbol"]) & set(r5_rank.head(10)["symbol"]))
    )

    rec = {
        "schema": SCHEMA,
        "diagnostic_id": DIAGNOSTIC_ID,
        "timestamp": ts,
        "signal_as_of": signal_as_of,
        "expected_seq": int(r9["expected_seq"]),
        "news_day_used": news_day_used,
        "universe_coverage": coverage,
        "r9_selected_symbol": str(r9["symbol"]),
        "r9_score": float(r9["R9_SCORE"]),
        "r9_position_weight": r9_weight,
        "r5_selected_symbol": str(r5["symbol"]),
        "r5_score": float(r5["R5_SCORE"]),
        "r5_position_weight": r5_weight,
        "top1_agree": bool(r9["symbol"] == r5["symbol"]),
        "score_spearman": spearman,
        "top10_overlap": top10_overlap,
        "r9_top5": [
            {"symbol": str(x.symbol), "score": float(x.R9_SCORE)}
            for x in r9_rank.head(5).itertuples(index=False)
        ],
        "r5_top5": [
            {"symbol": str(x.symbol), "score": float(x.R5_SCORE)}
            for x in r5_rank.head(5).itertuples(index=False)
        ],
        "news_feature_audit": news_audit,
        "r9_model_sha256": frozen["r9_manifest"]["artifacts"][
            "r9_2_hgb.joblib"
        ],
        "r5_model_sha256": sha256_file(frozen["r5_model_path"]),
        "preboundary_only": True,
        "prospective_evidence": False,
        "trade_entry_created": False,
        "outcome_created": False,
        "neon_write": False,
        "strategy_signal_write": False,
        "live_execution": False,
        "production_changed": False,
    }
    rec["diagnostic_key"] = f"{DIAGNOSTIC_ID}|{ts.isoformat()}"

    hash_payload = {
        k: (
            v.isoformat()
            if isinstance(v, pd.Timestamp)
            else v
        )
        for k, v in rec.items()
        if k not in {"decision_hash", "news_feature_audit"}
    }
    rec["decision_hash"] = stable_hash(hash_payload)
    return rec


def main() -> int:
    a = parse_args()
    root = Path(a.root)
    us = root / "US_ETF"
    frozen = _load_frozen_models(us)

    out = frozen["out"]
    diag_path = out / "r9_2_preboundary_diagnostic.parquet"
    latest_path = out / "r9_2_preboundary_latest.json"

    scored_symbols = pd.read_parquet(
        frozen["r501"] / "r5_0_1_scored_rows.parquet",
        columns=["symbol"],
    )
    symbols = sorted(scored_symbols["symbol"].astype(str).unique())
    if len(symbols) != 93:
        raise RuntimeError(f"expected 93 symbols, got {len(symbols)}")

    source_state, last_complete_day = load_source_state(
        Path(a.source_state)
    )
    if last_complete_day != REQUIRED_NEWS_DAY:
        raise RuntimeError(
            "pre-boundary diagnostic requires source state exactly through "
            f"{REQUIRED_NEWS_DAY.date()}, got {last_complete_day.date()}"
        )

    news_daily = build_news_daily(
        Path(a.news_history),
        symbols,
        last_complete_day,
    )
    panel, live_source_max = build_live_panel(us, symbols)
    recon = reconcile_features(us, panel, symbols)

    candidate_ts = sorted(
        pd.Timestamp(x)
        for x in panel.loc[
            (panel["timestamp"] >= DIAGNOSTIC_START)
            & (panel["timestamp"] < DIAGNOSTIC_END_EXCLUSIVE),
            "timestamp",
        ].dropna().unique()
    )

    if not candidate_ts:
        status = {
            "schema": SCHEMA,
            "diagnostic_id": DIAGNOSTIC_ID,
            "state": "WAITING_FOR_2026_09_23_CANONICAL_BAR",
            "diagnostic_start": DIAGNOSTIC_START.isoformat(),
            "diagnostic_end_exclusive": DIAGNOSTIC_END_EXCLUSIVE.isoformat(),
            "required_news_day": str(REQUIRED_NEWS_DAY.date()),
            "last_complete_news_day": str(last_complete_day.date()),
            "live_source_max_timestamp": str(live_source_max),
            "feature_reconciliation": recon,
            "preboundary_only": True,
            "prospective_evidence": False,
            "trade_entry_created": False,
            "outcome_created": False,
            "neon_write": False,
            "strategy_signal_write": False,
            "live_execution": False,
            "production_changed": False,
        }
        atomic_json(latest_path, status)
        print(json.dumps(status, indent=2, default=str))
        print("R9_2_PREBOUNDARY_DIAGNOSTIC=WAITING")
        return 0

    rows = []
    for ts in candidate_ts:
        z = panel.loc[panel["timestamp"] == ts].copy()
        rows.append(
            _score_timestamp(
                z,
                ts,
                news_daily,
                last_complete_day,
                frozen,
            )
        )

    new = pd.DataFrame(rows)
    full = _append_immutable(diag_path, new)
    latest = full.sort_values("timestamp").iloc[-1].to_dict()

    status = {
        "schema": SCHEMA,
        "diagnostic_id": DIAGNOSTIC_ID,
        "state": "DIAGNOSTIC_AVAILABLE",
        "diagnostic_start": DIAGNOSTIC_START.isoformat(),
        "diagnostic_end_exclusive": DIAGNOSTIC_END_EXCLUSIVE.isoformat(),
        "required_news_day": str(REQUIRED_NEWS_DAY.date()),
        "last_complete_news_day": str(last_complete_day.date()),
        "live_source_max_timestamp": str(live_source_max),
        "feature_reconciliation": recon,
        "rows": int(len(full)),
        "latest": latest,
        "preboundary_only": True,
        "prospective_evidence": False,
        "trade_entry_created": False,
        "outcome_created": False,
        "neon_write": False,
        "strategy_signal_write": False,
        "live_execution": False,
        "production_changed": False,
    }
    atomic_json(latest_path, status)

    print("===== R9.2 PRE-BOUNDARY DIAGNOSTIC =====")
    print(f"timestamp={latest['timestamp']}")
    print(f"signal_as_of={latest['signal_as_of']}")
    print(f"news_day_used={latest['news_day_used']}")
    print(f"coverage={latest['universe_coverage']}")
    print(
        f"R9_TOP1={latest['r9_selected_symbol']} "
        f"score={latest['r9_score']:.8f} "
        f"weight={latest['r9_position_weight']:.4f}"
    )
    print(
        f"R5_TOP1={latest['r5_selected_symbol']} "
        f"score={latest['r5_score']:.8f} "
        f"weight={latest['r5_position_weight']:.4f}"
    )
    print(f"TOP1_AGREE={latest['top1_agree']}")
    print(f"SCORE_SPEARMAN={latest['score_spearman']:.6f}")
    print(f"TOP10_OVERLAP={latest['top10_overlap']}")
    print("R9_TOP5=" + json.dumps(latest["r9_top5"], ensure_ascii=False))
    print("R5_TOP5=" + json.dumps(latest["r5_top5"], ensure_ascii=False))
    print("prospective_evidence=false")
    print("live_execution=false")
    print("production_changed=false")
    print(f"DETAIL={latest_path}")
    print("R9_2_PREBOUNDARY_DIAGNOSTIC=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
