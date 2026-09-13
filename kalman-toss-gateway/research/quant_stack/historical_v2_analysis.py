from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from .historical_backfill import _fit_model, _predict_probability
from .portfolio_targets import (
    build_rolling_portfolio_targets,
    load_sleeve_returns,
    portfolio_equity_from_targets,
    portfolio_metrics,
)
from .qlib_recorder import record_market_experiment

MARKETS = ("US", "KR", "BTC")
CORE_METHODS = ("equal_weight", "inverse_volatility", "hrp")


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _analysis_dir(output_root: Path) -> Path:
    path = output_root / "analysis_v2"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_provenance(
    output_root: Path,
    *,
    analysis_git_sha: str,
    pinned_code_sha: str,
) -> dict[str, Any]:
    resume_path = output_root / "historical_resume_complete.json"
    resume = _load_json(resume_path) if resume_path.exists() else {}

    market_git_sha: dict[str, str | None] = {}
    immutable_files: dict[str, dict[str, str]] = {}
    for market in MARKETS:
        market_dir = output_root / market.lower()
        experiment_path = market_dir / "experiment.json"
        if not experiment_path.exists():
            continue
        experiment = _load_json(experiment_path)
        market_git_sha[market] = experiment.get("git_sha")
        immutable_files[market] = {}
        for name in (
            "historical_model_output.parquet",
            "historical_strategy_signal.parquet",
            "fold_metrics.json",
            "experiment.json",
            "historical_trades.parquet",
            "historical_equity.parquet",
            "historical_performance.json",
            "run_summary.json",
        ):
            path = market_dir / name
            if path.exists():
                immutable_files[market][name] = _sha256(path)

    return {
        "status": "READY",
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
        "historical_reused": True,
        "market_backtests_rerun": False,
        "run_tag": output_root.name,
        "market_backtest_git_sha": market_git_sha,
        "resume_git_sha": resume.get("git_sha"),
        "analysis_git_sha": analysis_git_sha,
        "pinned_code_sha": pinned_code_sha,
        "immutable_market_artifact_sha256": immutable_files,
    }


def run_core_portfolio_benchmarks(
    output_root: Path,
    *,
    lookback_days: int = 180,
    min_observations: int = 90,
    rebalance_frequency: str = "M",
) -> dict[str, Any]:
    status = _load_json(output_root / "historical_experiment_status.json")
    markets = [
        market
        for market in MARKETS
        if status.get("markets", {}).get(market, {}).get("status") == "READY"
    ]
    if len(markets) < 2:
        raise RuntimeError("portfolio benchmark requires at least two READY markets")

    returns = load_sleeve_returns(output_root, markets)
    root = _analysis_dir(output_root) / "portfolio_benchmarks"
    rows: list[dict[str, Any]] = []

    for method in CORE_METHODS:
        targets = build_rolling_portfolio_targets(
            returns,
            method=method,
            lookback_days=lookback_days,
            min_observations=min_observations,
            rebalance_frequency=rebalance_frequency,
        )
        equity = portfolio_equity_from_targets(returns, targets)
        metrics = portfolio_metrics(equity)

        method_dir = root / method
        method_dir.mkdir(parents=True, exist_ok=True)
        targets.to_parquet(method_dir / "portfolio_target.parquet", index=False)
        equity.to_parquet(method_dir / "portfolio_equity.parquet", index=False)
        _write_json(method_dir / "portfolio_performance.json", metrics)

        rows.append(
            {
                "method": method,
                "source": "PYPFOPT" if method == "hrp" else "KALMAN",
                "target_rows": int(len(targets)),
                "rebalance_count": int(targets["effective_ts"].nunique()),
                **metrics,
            }
        )

    comparison = pd.DataFrame(rows)
    comparison.to_csv(root / "core_portfolio_comparison.csv", index=False)
    payload = {
        "status": "READY",
        "methods": list(CORE_METHODS),
        "markets": markets,
        "lookback_days": lookback_days,
        "min_observations": min_observations,
        "rebalance_frequency": rebalance_frequency,
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
        "rows": rows,
    }
    _write_json(root / "core_portfolio_summary.json", payload)
    return payload


def _slice_fold(frame: pd.DataFrame, fold: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = frame.loc[
        (frame["as_of"] >= pd.Timestamp(fold["train_start"]))
        & (frame["as_of"] <= pd.Timestamp(fold["train_end"]))
    ].copy()
    validation = frame.loc[
        (frame["as_of"] >= pd.Timestamp(fold["valid_start"]))
        & (frame["as_of"] <= pd.Timestamp(fold["valid_end"]))
    ].copy()
    test = frame.loc[
        (frame["as_of"] >= pd.Timestamp(fold["test_start"]))
        & (frame["as_of"] <= pd.Timestamp(fold["test_end"]))
    ].copy()
    return train, validation, test


def run_feature_oos_importance(
    output_root: Path,
    matrix_dir: Path,
    *,
    repeats: int = 3,
) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("repeats must be >= 1")

    root = _analysis_dir(output_root) / "feature_oos"
    root.mkdir(parents=True, exist_ok=True)
    combined_rows: list[pd.DataFrame] = []
    market_summary: dict[str, Any] = {}

    for market in MARKETS:
        matrix_path = matrix_dir / f"{market.lower()}_matrix.parquet"
        fold_path = output_root / market.lower() / "fold_metrics.json"
        if not matrix_path.exists() or not fold_path.exists():
            continue

        frame = pd.read_parquet(matrix_path)
        frame["as_of"] = pd.to_datetime(frame["as_of"], utc=True, errors="raise")
        frame = (
            frame.sort_values("as_of")
            .drop_duplicates("as_of", keep="last")
            .loc[lambda x: x["target_label"].notna()]
            .reset_index(drop=True)
        )
        folds = _load_json(fold_path)
        contributions: list[dict[str, Any]] = []
        usable_folds = 0

        for item in folds:
            fold = item["fold"]
            train, validation, test = _slice_fold(frame, fold)
            features = [str(x) for x in item.get("selected_features", [])]
            features = [x for x in features if x in frame.columns]
            if not features or min(len(train), len(validation), len(test)) < 20:
                continue

            y_test = pd.to_numeric(test["target_label"], errors="coerce")
            if y_test.nunique(dropna=True) < 2:
                continue

            fit_frame = pd.concat([train, validation], ignore_index=True)
            imputer, scaler, model = _fit_model(
                fit_frame,
                features,
                c_value=float(item["best_c"]),
            )
            baseline_prob = _predict_probability(
                test,
                features,
                imputer,
                scaler,
                model,
            )
            baseline_auc = float(roc_auc_score(y_test, baseline_prob))
            usable_folds += 1

            for feature in features:
                drops: list[float] = []
                for repeat in range(repeats):
                    seed_text = f"{market}|{fold['fold_id']}|{feature}|{repeat}"
                    seed = int(hashlib.sha256(seed_text.encode()).hexdigest()[:8], 16)
                    rng = np.random.default_rng(seed)
                    shuffled = test.copy()
                    values = shuffled[feature].to_numpy(copy=True)
                    shuffled[feature] = values[rng.permutation(len(values))]
                    perm_prob = _predict_probability(
                        shuffled,
                        features,
                        imputer,
                        scaler,
                        model,
                    )
                    perm_auc = float(roc_auc_score(y_test, perm_prob))
                    drops.append(baseline_auc - perm_auc)

                contributions.append(
                    {
                        "market": market,
                        "fold_id": int(fold["fold_id"]),
                        "feature": feature,
                        "baseline_auc": baseline_auc,
                        "mean_auc_drop": float(np.mean(drops)),
                        "median_auc_drop": float(np.median(drops)),
                        "positive_drop_ratio": float(np.mean(np.asarray(drops) > 0)),
                        "repeats": repeats,
                    }
                )

        detail = pd.DataFrame(contributions)
        if detail.empty:
            market_summary[market] = {
                "status": "SKIPPED",
                "reason": "no usable folds for OOS permutation importance",
            }
            continue

        detail.to_parquet(root / f"{market.lower()}_feature_oos_detail.parquet", index=False)
        summary = (
            detail.groupby(["market", "feature"], as_index=False)
            .agg(
                selected_fold_count=("fold_id", "nunique"),
                mean_auc_drop=("mean_auc_drop", "mean"),
                median_auc_drop=("median_auc_drop", "median"),
                positive_drop_ratio=("positive_drop_ratio", "mean"),
                mean_baseline_auc=("baseline_auc", "mean"),
            )
            .sort_values(["mean_auc_drop", "selected_fold_count"], ascending=[False, False])
            .reset_index(drop=True)
        )
        summary["selection_frequency"] = summary["selected_fold_count"] / max(usable_folds, 1)
        summary.to_csv(root / f"{market.lower()}_feature_oos_summary.csv", index=False)
        combined_rows.append(summary)

        market_summary[market] = {
            "status": "READY",
            "usable_folds": usable_folds,
            "features_evaluated": int(summary["feature"].nunique()),
            "top_features": summary.head(15).to_dict("records"),
        }

    combined = pd.concat(combined_rows, ignore_index=True) if combined_rows else pd.DataFrame()
    if not combined.empty:
        combined.to_csv(root / "combined_feature_oos_summary.csv", index=False)

    payload = {
        "status": "READY" if not combined.empty else "SKIPPED",
        "method": "walk_forward_test_fold_permutation_auc_drop",
        "permutation_repeats": repeats,
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
        "markets": market_summary,
    }
    _write_json(root / "feature_oos_summary.json", payload)
    return payload


def record_existing_run_with_qlib(
    output_root: Path,
    *,
    tracking_root: Path,
    provider_root: Path,
    experiment_name: str,
) -> dict[str, Any]:
    results: dict[str, Any] = {}

    for market in MARKETS:
        market_dir = output_root / market.lower()
        experiment_path = market_dir / "experiment.json"
        performance_path = market_dir / "historical_performance.json"
        if not experiment_path.exists() or not performance_path.exists():
            continue

        experiment = _load_json(experiment_path)
        performance = _load_json(performance_path)
        result = record_market_experiment(
            experiment_name=experiment_name,
            tracking_root=tracking_root,
            provider_root=provider_root,
            params={
                "market": market,
                "mode": "BACKTEST",
                "experiment_hash": str(experiment.get("experiment_hash", "")),
                "feature_version": str(experiment.get("feature_version", "")),
                "model_version": str(experiment.get("model_version", "")),
                "start_date": str(experiment.get("start_date", "")),
                "completed_folds": int(experiment.get("completed_folds", 0)),
                "git_sha": str(experiment.get("git_sha", "")),
                "historical_reused": True,
                "market_backtests_rerun": False,
            },
            metrics=performance,
            artifact_manifest={
                "market": market,
                "output_dir": str(market_dir),
                "source_run_tag": output_root.name,
                "historical_reused": True,
                "market_backtests_rerun": False,
                "research_only": True,
                "live_execution": False,
                "toss_execution": False,
                "neon_write": False,
            },
        )
        results[market] = result

    payload = {
        "status": "READY" if results else "SKIPPED",
        "experiment_name": experiment_name,
        "tracking_root": str(tracking_root),
        "provider_root": str(provider_root),
        "historical_reused": True,
        "market_backtests_rerun": False,
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
        "markets": results,
    }
    _write_json(_analysis_dir(output_root) / "qlib_recording.json", payload)
    return payload


def aggregate_summary(output_root: Path) -> dict[str, Any]:
    root = _analysis_dir(output_root)
    rows: list[dict[str, Any]] = []

    core_path = root / "portfolio_benchmarks" / "core_portfolio_comparison.csv"
    if core_path.exists():
        core = pd.read_csv(core_path)
        rows.extend(core.to_dict("records"))

    risk_path = root / "portfolio_benchmarks" / "riskfolio_portfolio_comparison.csv"
    if risk_path.exists():
        risk = pd.read_csv(risk_path)
        rows.extend(risk.to_dict("records"))

    portfolio = pd.DataFrame(rows)
    if not portfolio.empty:
        for col in ("sharpe", "cagr", "total_return", "max_drawdown"):
            if col in portfolio:
                portfolio[col] = pd.to_numeric(portfolio[col], errors="coerce")
        portfolio = portfolio.sort_values(
            ["sharpe", "cagr"],
            ascending=[False, False],
            na_position="last",
        ).reset_index(drop=True)
        portfolio.to_csv(root / "portfolio_benchmark_all.csv", index=False)

    vectorbt_path = root / "vectorbt" / "vectorbt_validation_summary.json"
    feature_path = root / "feature_oos" / "feature_oos_summary.json"
    qlib_path = root / "qlib_recording.json"
    provenance_path = root / "provenance.json"

    payload = {
        "status": "COMPLETE",
        "run_tag": output_root.name,
        "portfolio_ranking": portfolio.to_dict("records") if not portfolio.empty else [],
        "vectorbt": _load_json(vectorbt_path) if vectorbt_path.exists() else None,
        "feature_oos": _load_json(feature_path) if feature_path.exists() else None,
        "qlib": _load_json(qlib_path) if qlib_path.exists() else None,
        "provenance": _load_json(provenance_path) if provenance_path.exists() else None,
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
        "promotion_recommendation": "RESEARCH_ONLY",
    }
    _write_json(root / "historical_v2_analysis_summary.json", payload)
    return payload


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kalman Historical V2 analysis utilities")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--matrix-dir")
    p.add_argument(
        "--mode",
        choices=["core", "qlib", "summary", "provenance"],
        required=True,
    )
    p.add_argument("--analysis-git-sha", default="")
    p.add_argument("--pinned-code-sha", default="")
    p.add_argument("--qlib-tracking-root")
    p.add_argument("--qlib-provider-root")
    p.add_argument("--qlib-experiment-name", default="kalman_historical_2017_v2_analysis")
    p.add_argument("--permutation-repeats", type=int, default=3)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_dir).expanduser()

    if args.mode == "provenance":
        payload = build_provenance(
            output_root,
            analysis_git_sha=args.analysis_git_sha,
            pinned_code_sha=args.pinned_code_sha,
        )
        _write_json(_analysis_dir(output_root) / "provenance.json", payload)
    elif args.mode == "core":
        if not args.matrix_dir:
            raise ValueError("--matrix-dir is required for core mode")
        portfolio = run_core_portfolio_benchmarks(output_root)
        feature = run_feature_oos_importance(
            output_root,
            Path(args.matrix_dir).expanduser(),
            repeats=args.permutation_repeats,
        )
        payload = {"portfolio": portfolio, "feature_oos": feature}
    elif args.mode == "qlib":
        if not args.qlib_tracking_root or not args.qlib_provider_root:
            raise ValueError("Qlib roots are required for qlib mode")
        payload = record_existing_run_with_qlib(
            output_root,
            tracking_root=Path(args.qlib_tracking_root).expanduser(),
            provider_root=Path(args.qlib_provider_root).expanduser(),
            experiment_name=args.qlib_experiment_name,
        )
    else:
        payload = aggregate_summary(output_root)

    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
