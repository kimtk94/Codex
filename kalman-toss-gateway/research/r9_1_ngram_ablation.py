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
    COST,
    FOLDS,
    MIN_UNIVERSE,
    RESEARCH_CUTOFF,
    SCORED_COLUMNS,
    build_training_rows,
    effective_names,
    metrics,
    nts,
    paired_bootstrap,
    reconcile_base_features,
    reconcile_target,
    schedule_audit,
    sha256_file,
    simulate,
    ts,
)
from r9_news_features import (
    FEATURE_READY_SIGNAL_DAY,
    NEWS_FEATURES,
    attach_news_features,
    build_daily_features,
)

SCHEMA = "kalman-r9-1-ngram-attention-ablation-v1"
CONTROL = "R9C0_WINDOW_MATCHED_BASE"
CHALLENGER = "R9C1_NGRAM_ATTENTION"
FROZEN_R5 = "R5C0_HGB_REFERENCE"

# Only folds fully after the 2024-08 historical source start are admitted.
EVAL_FOLDS = FOLDS[4:]
EVAL_FOLD_NAMES = {x[0] for x in EVAL_FOLDS}
B_DEFAULT = 2000


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    root = Path(os.getenv("KALMAN_DATA_ROOT", "/mnt/gdrive"))
    state = Path(os.getenv(
        "R9_NEWS_STATE_DIR",
        str(Path.home() / ".local/state/kalman/r9_news_ngram"),
    ))
    p.add_argument("--root", default=str(root))
    p.add_argument("--mentions", default=str(state / "r9_ngram_historical.csv"))
    p.add_argument("--news-manifest", default=str(state / "manifest.json"))
    p.add_argument("--bootstrap", type=int, default=B_DEFAULT)
    return p.parse_args()


def _fit_predict(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    features: list[str],
    model_template,
    score_col: str,
) -> pd.DataFrame:
    med = train[features].median()
    model = clone(model_template)
    model.fit(train[features].fillna(med), train["relative_ret_4b"])
    out = test.copy()
    out[score_col] = model.predict(out[features].fillna(med))
    return out


def main() -> int:
    a = parse_args()
    root = Path(a.root)
    mentions_path = Path(a.mentions)
    manifest_path = Path(a.news_manifest)

    if os.getenv("R9_ALLOW_LIVE", "").lower() == "true":
        raise RuntimeError("R9.1 refuses LIVE mode")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "kalman-r9-news-ngram-readiness-v1":
        raise RuntimeError(f"unexpected R9 manifest schema: {manifest.get('schema')}")
    if not manifest.get("r9_ngram_ready"):
        raise RuntimeError("R9 NGram readiness gate not ready")
    if manifest.get("next_action") != "PREREGISTER_SINGLE_R9_NGRAM_ABLATION":
        raise RuntimeError("R9 readiness next_action drift")
    if int(manifest.get("universe_symbols") or 0) != 93:
        raise RuntimeError("R9 universe drift")
    if float(manifest.get("usable_span_months") or 0) < 24:
        raise RuntimeError("R9 usable span below 24 months")

    us = root / "US_ETF"
    r50 = us / "model_lab_v1/results/r5_0_1_research_sandbox_all_data"
    outdir = us / "model_lab_v1/results/r9_1_ngram_attention"
    outdir.mkdir(parents=True, exist_ok=True)

    scored_path = r50 / "r5_0_1_scored_rows.parquet"
    ledger_path = r50 / "r5_0_1_trade_ledger.parquet"
    model_path = r50 / "model_freeze/r5_hgb.joblib"

    scored = pd.read_parquet(scored_path, columns=SCORED_COLUMNS)
    model_template = joblib.load(model_path)

    scored["timestamp"] = nts(scored["timestamp"])
    scored["target_timestamp_4b"] = nts(scored["target_timestamp_4b"])
    scored = scored.loc[
        scored["target_timestamp_4b"].notna()
        & (scored["target_timestamp_4b"] < RESEARCH_CUTOFF)
    ].copy()
    if scored["symbol"].nunique() != 93:
        raise RuntimeError(f"expected 93 symbols, got {scored['symbol'].nunique()}")

    symbols = sorted(scored["symbol"].astype(str).unique())
    train_all = build_training_rows(root, symbols)

    base_audit = reconcile_base_features(train_all, scored)
    if not base_audit["pass"]:
        raise RuntimeError(f"base feature reconciliation failed: {base_audit}")
    target_audit = reconcile_target(train_all, scored)
    if not target_audit["pass"]:
        raise RuntimeError(f"target reconciliation failed: {target_audit}")

    mentions = pd.read_csv(mentions_path)
    daily = build_daily_features(mentions, symbols)

    train_all, train_news_audit = attach_news_features(train_all, daily)
    scored, scored_news_audit = attach_news_features(scored, daily)

    train_all = train_all.loc[
        train_all["timestamp"] >= FEATURE_READY_SIGNAL_DAY
    ].copy()

    if train_all.empty:
        raise RuntimeError("no R9 feature-ready training rows")
    if train_all[NEWS_FEATURES].isna().any().any():
        raise RuntimeError("R9 training features contain missing values after burn-in")

    # Integrity-only protocol correction:
    # replay the already-frozen R5 score on the exact R9-admissible evaluation
    # rows. The historical frozen trade ledger was generated on a different
    # non-overlap path, so slicing it by fold does not guarantee timestamp
    # identity with a newly reconstructed challenger ledger.
    r5_parts = []
    control_parts = []
    challenger_parts = []
    fold_contract = []

    for fold, ss, ee in EVAL_FOLDS:
        start, end = ts(ss), ts(ee)

        tr = train_all.loc[train_all["target_timestamp_4b"] < start].copy()
        te = scored.loc[
            (scored["fold"].astype(str) == fold)
            & (scored["timestamp"] >= start)
            & (scored["timestamp"] < end)
        ].copy()

        te = te.loc[te[NEWS_FEATURES].notna().all(axis=1)].copy()
        valid_ts = te.groupby("timestamp")["symbol"].nunique()
        valid_ts = set(valid_ts[valid_ts >= MIN_UNIVERSE].index)
        te = te.loc[te["timestamp"].isin(valid_ts)].copy()
        te["eval_fold"] = fold

        if len(tr) < 5000:
            raise RuntimeError(f"{fold}: too few window-matched train rows: {len(tr)}")
        if te.empty:
            raise RuntimeError(f"{fold}: no evaluable rows")

        r5_parts.append(te.copy())

        c0 = _fit_predict(
            tr,
            te,
            features=BASE_FEATURES,
            model_template=model_template,
            score_col=CONTROL,
        )
        c1 = _fit_predict(
            tr,
            te,
            features=BASE_FEATURES + NEWS_FEATURES,
            model_template=model_template,
            score_col=CHALLENGER,
        )
        control_parts.append(c0)
        challenger_parts.append(c1)

        fold_contract.append({
            "fold": fold,
            "train_rows": int(len(tr)),
            "test_rows": int(len(te)),
            "test_timestamps": int(te["timestamp"].nunique()),
            "train_first_signal": str(tr["timestamp"].min()),
            "train_last_target": str(tr["target_timestamp_4b"].max()),
            "news_coverage_test": float(te[NEWS_FEATURES].notna().all(axis=1).mean()),
        })

    r5_rows = pd.concat(r5_parts, ignore_index=True)
    control_rows = pd.concat(control_parts, ignore_index=True)
    challenger_rows = pd.concat(challenger_parts, ignore_index=True)

    frozen_r5 = simulate(r5_rows, FROZEN_R5)
    control_ledger = simulate(control_rows, CONTROL)
    challenger_ledger = simulate(challenger_rows, CHALLENGER)
    frozen_r5["candidate"] = FROZEN_R5
    control_ledger["candidate"] = CONTROL
    challenger_ledger["candidate"] = CHALLENGER

    sched_c = schedule_audit(control_ledger, challenger_ledger)
    if not sched_c["exact_match"]:
        raise RuntimeError(f"control/challenger schedule mismatch: {sched_c}")

    sched_r5 = schedule_audit(frozen_r5, challenger_ledger)
    if not sched_r5["exact_match"]:
        raise RuntimeError(f"frozen R5/challenger schedule mismatch: {sched_r5}")

    control_m = metrics(control_ledger)
    chal_m = metrics(challenger_ledger)
    r5_m = metrics(frozen_r5)

    c_eff, c_top = effective_names(control_ledger["symbol"], control_ledger["weight"])
    ch_eff, ch_top = effective_names(challenger_ledger["symbol"], challenger_ledger["weight"])
    r5_eff, r5_top = effective_names(frozen_r5["symbol"], frozen_r5["weight"])

    boot = paired_bootstrap(control_ledger, challenger_ledger, a.bootstrap)
    positive_folds = int(sum(x["paired_log_diff"] > 0 for x in boot["folds"]))

    survivor = bool(
        chal_m["trades"] >= 150
        and chal_m["log_growth"] > control_m["log_growth"]
        and chal_m["profit_factor"] >= control_m["profit_factor"]
        and chal_m["mdd"] >= control_m["mdd"] - 0.02
        and chal_m["log_growth"] > r5_m["log_growth"]
        and chal_m["profit_factor"] >= r5_m["profit_factor"]
        and positive_folds >= 3
        and boot["ci95_low"] > 0
        and boot["p_one_sided"] < 0.05
        and ch_eff >= 5
        and ch_top <= 0.35
    )

    leaderboard = pd.DataFrame([
        {
            "candidate": FROZEN_R5,
            **r5_m,
            "effective_names": r5_eff,
            "top_ticker_share": r5_top,
        },
        {
            "candidate": CONTROL,
            **control_m,
            "effective_names": c_eff,
            "top_ticker_share": c_top,
        },
        {
            "candidate": CHALLENGER,
            **chal_m,
            "effective_names": ch_eff,
            "top_ticker_share": ch_top,
            "paired_rows": boot["paired_rows"],
            "paired_days": boot["days"],
            "paired_mean_daily_log_diff": boot["obs_mean_daily_paired_log_diff"],
            "ci95_low": boot["ci95_low"],
            "ci95_high": boot["ci95_high"],
            "p_one_sided": boot["p_one_sided"],
            "positive_paired_folds": positive_folds,
            "research_survivor": survivor,
        },
    ])

    decision = {
        "schema": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "SUCCESS",
        "research_only": True,
        "production_changed": False,
        "r5_1_untouched": True,
        "candidate": CHALLENGER,
        "control": CONTROL,
        "frozen_champion": FROZEN_R5,
        "news_features": NEWS_FEATURES,
        "feature_ready_signal_day": str(FEATURE_READY_SIGNAL_DAY),
        "eval_folds": [x[0] for x in EVAL_FOLDS],
        "target": "relative_ret_4b frozen R5 target",
        "pit_contract": "signal_as_of=timestamp+60m; use only UTC days strictly before DATE(signal_as_of)",
        "base_feature_reconciliation": base_audit,
        "target_reconciliation": target_audit,
        "train_news_audit": train_news_audit,
        "scored_news_audit": scored_news_audit,
        "schedule_control_vs_challenger": sched_c,
        "schedule_r5_vs_challenger": sched_r5,
        "frozen_r5_reference_mode": "REPLAY_FROZEN_R5_SCORE_ON_EXACT_R9_ADMISSIBLE_ROWS",
        "historical_frozen_ledger_used_for_performance": False,
        "frozen_r5": r5_m,
        "window_matched_control": control_m,
        "challenger": chal_m,
        "paired_bootstrap_vs_window_matched_control": boot,
        "positive_paired_folds": positive_folds,
        "research_survivor": survivor,
        "promotion_eligible": survivor,
        "live_action": "NONE",
        "post_result_tuning_allowed": False,
    }

    challenger_rows[
        [
            "timestamp", "target_timestamp_4b", "expected_seq", "symbol", "eval_fold",
            "fwd_ret_4b", "rv_24", "universe_median_rv24",
            *BASE_FEATURES, *NEWS_FEATURES, CHALLENGER,
        ]
    ].to_parquet(outdir / "r9_1_scored_rows.parquet", index=False)
    control_ledger.to_parquet(outdir / "r9_1_control_trade_ledger.parquet", index=False)
    challenger_ledger.to_parquet(outdir / "r9_1_trade_ledger.parquet", index=False)
    leaderboard.to_csv(outdir / "r9_1_leaderboard.csv", index=False)
    pd.DataFrame(fold_contract).to_csv(outdir / "r9_1_fold_contract.csv", index=False)
    pd.DataFrame(boot["folds"]).to_csv(
        outdir / "r9_1_paired_fold_summary.csv", index=False
    )
    (outdir / "r9_1_selection_decision.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    (outdir / "r9_1_manifest.json").write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "sources": {
                    str(scored_path): sha256_file(scored_path),
                    str(ledger_path): sha256_file(ledger_path),
                    str(model_path): sha256_file(model_path),
                    str(mentions_path): sha256_file(mentions_path),
                    str(manifest_path): sha256_file(manifest_path),
                },
                "research_only": True,
                "production_changed": False,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(decision, indent=2, default=str))
    print("\nLEADERBOARD")
    print(leaderboard.to_string(index=False))
    print("\nR9_1_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
