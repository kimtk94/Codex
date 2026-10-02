#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd



SCHEMA_VERSION = "kalman-r5-conditional-allocation-v1"

def _max_drawdown(returns: pd.Series) -> float:
    wealth = (1.0 + returns.fillna(0.0)).cumprod()
    if wealth.empty:
        return float("nan")
    drawdown = wealth / wealth.cummax() - 1.0
    return float(drawdown.min())


def strategy_metrics(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {}

    returns = pd.to_numeric(frame["net_return"], errors="coerce").dropna()
    if returns.empty:
        return {}

    total_return = float((1.0 + returns).prod() - 1.0)
    max_drawdown = _max_drawdown(returns)

    start = pd.Timestamp(frame["entry_timestamp"].min())
    end = pd.Timestamp(frame["exit_timestamp"].max())
    years = max(
        (end - start).total_seconds() / (365.25 * 86400.0),
        1.0 / 365.25,
    )

    cagr = (
        float((1.0 + total_return) ** (1.0 / years) - 1.0)
        if total_return > -1.0
        else -1.0
    )

    trades_per_year = len(returns) / years
    sd = float(returns.std(ddof=0))
    sharpe = (
        float(returns.mean() / sd * math.sqrt(trades_per_year))
        if sd > 0 and trades_per_year > 0
        else None
    )

    downside = returns.loc[returns < 0]
    downside_sd = (
        float(np.sqrt(np.mean(np.square(downside))))
        if len(downside)
        else 0.0
    )
    sortino = (
        float(returns.mean() / downside_sd * math.sqrt(trades_per_year))
        if downside_sd > 0
        else None
    )

    return {
        "trades": int(len(returns)),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "cagr_over_abs_mdd": (
            float(cagr / abs(max_drawdown))
            if max_drawdown < 0
            else None
        ),
        "trade_sharpe_annualized": sharpe,
        "trade_sortino_annualized": sortino,
        "win_rate": float((returns > 0).mean()),
        "mean_net_return": float(returns.mean()),
        "median_net_return": float(returns.median()),
        "best_trade": float(returns.max()),
        "worst_trade": float(returns.min()),
    }

STRATEGIES = (
    "TOP1_ALWAYS",
    "GAP_70_30",
    "GAP_50_50",
    "CONF_TOP1_OR_50CASH",
    "GAP70_CONF50CASH",
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def prepare_features(
    panel: pd.DataFrame,
    *,
    min_history: int,
    gap_quantile: float,
    confidence_quantile: float,
) -> pd.DataFrame:
    z = panel.copy()
    z = z.sort_values(["entry_timestamp", "expected_seq"]).reset_index(drop=True)

    required = [
        "expected_seq",
        "entry_timestamp",
        "exit_timestamp",
        "rank1_score",
        "rank2_score",
        "rank1_raw_return",
        "rank2_raw_return",
    ]
    missing = [c for c in required if c not in z.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    for c in [
        "rank1_score",
        "rank2_score",
        "rank1_raw_return",
        "rank2_raw_return",
    ]:
        z[c] = pd.to_numeric(z[c], errors="coerce")

    z["entry_timestamp"] = pd.to_datetime(
        z["entry_timestamp"], utc=True, errors="coerce"
    )
    z["exit_timestamp"] = pd.to_datetime(
        z["exit_timestamp"], utc=True, errors="coerce"
    )

    z["score_gap"] = z["rank1_score"] - z["rank2_score"]
    denom = z["rank1_score"].abs().clip(lower=1e-12)
    z["relative_score_gap"] = z["score_gap"] / denom

    # No lookahead:
    # each threshold at row t is estimated only from rows < t.
    z["gap_threshold"] = (
        z["relative_score_gap"]
        .shift(1)
        .expanding(min_periods=min_history)
        .quantile(gap_quantile)
    )
    z["confidence_threshold"] = (
        z["rank1_score"]
        .shift(1)
        .expanding(min_periods=min_history)
        .quantile(confidence_quantile)
    )

    z["threshold_ready"] = (
        z["gap_threshold"].notna()
        & z["confidence_threshold"].notna()
    )
    z["close_gap"] = (
        z["threshold_ready"]
        & (z["relative_score_gap"] <= z["gap_threshold"])
    )
    z["low_confidence"] = (
        z["threshold_ready"]
        & (z["rank1_score"] <= z["confidence_threshold"])
    )

    return z


def weights_for_row(strategy: str, row: pd.Series) -> tuple[float, float, float]:
    # Returns (rank1_weight, rank2_weight, cash_weight)
    if strategy == "TOP1_ALWAYS":
        return 1.0, 0.0, 0.0

    ready = bool(row["threshold_ready"])
    close_gap = bool(row["close_gap"]) if ready else False
    low_conf = bool(row["low_confidence"]) if ready else False

    if strategy == "GAP_70_30":
        if close_gap:
            return 0.70, 0.30, 0.0
        return 1.0, 0.0, 0.0

    if strategy == "GAP_50_50":
        if close_gap:
            return 0.50, 0.50, 0.0
        return 1.0, 0.0, 0.0

    if strategy == "CONF_TOP1_OR_50CASH":
        if low_conf:
            return 0.50, 0.0, 0.50
        return 1.0, 0.0, 0.0

    if strategy == "GAP70_CONF50CASH":
        if low_conf:
            return 0.50, 0.0, 0.50
        if close_gap:
            return 0.70, 0.30, 0.0
        return 1.0, 0.0, 0.0

    raise ValueError(strategy)


def evaluate(
    features: pd.DataFrame,
    *,
    cost_bps: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail_rows: list[dict] = []

    cost_rate = float(cost_bps) / 10000.0

    for _, row in features.iterrows():
        for strategy in STRATEGIES:
            w1, w2, wcash = weights_for_row(strategy, row)
            invested = w1 + w2

            gross = (
                w1 * float(row["rank1_raw_return"])
                + w2 * float(row["rank2_raw_return"])
            )

            # Preserve the existing 10 bp convention for fully invested
            # portfolios, but charge only on invested capital when cash is held.
            cost = cost_rate * invested
            net = gross - cost

            detail_rows.append(
                {
                    "strategy": strategy,
                    "expected_seq": int(row["expected_seq"]),
                    "entry_timestamp": row["entry_timestamp"],
                    "exit_timestamp": row["exit_timestamp"],
                    "rank1_symbol": row.get("rank1_symbol"),
                    "rank2_symbol": row.get("rank2_symbol"),
                    "rank1_score": float(row["rank1_score"]),
                    "rank2_score": float(row["rank2_score"]),
                    "score_gap": float(row["score_gap"]),
                    "relative_score_gap": float(row["relative_score_gap"]),
                    "gap_threshold": (
                        float(row["gap_threshold"])
                        if pd.notna(row["gap_threshold"])
                        else np.nan
                    ),
                    "confidence_threshold": (
                        float(row["confidence_threshold"])
                        if pd.notna(row["confidence_threshold"])
                        else np.nan
                    ),
                    "threshold_ready": bool(row["threshold_ready"]),
                    "close_gap": bool(row["close_gap"]),
                    "low_confidence": bool(row["low_confidence"]),
                    "rank1_weight": w1,
                    "rank2_weight": w2,
                    "cash_weight": wcash,
                    "gross_return": gross,
                    "cost_return": cost,
                    "net_return": net,
                }
            )

    detail = pd.DataFrame(detail_rows)

    summary_rows: list[dict] = []
    for strategy in STRATEGIES:
        sub = detail.loc[detail["strategy"].eq(strategy)].copy()
        metrics = strategy_metrics(sub)
        metrics["strategy"] = strategy
        metrics["close_gap_trades"] = int(sub["close_gap"].sum())
        metrics["low_confidence_trades"] = int(sub["low_confidence"].sum())
        metrics["mean_rank1_weight"] = float(sub["rank1_weight"].mean())
        metrics["mean_rank2_weight"] = float(sub["rank2_weight"].mean())
        metrics["mean_cash_weight"] = float(sub["cash_weight"].mean())
        summary_rows.append(metrics)

    summary = pd.DataFrame(summary_rows)
    cols = ["strategy"] + [c for c in summary.columns if c != "strategy"]
    return detail, summary[cols]


def conditional_diagnostics(features: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []

    conditions = {
        "ALL": pd.Series(True, index=features.index),
        "CLOSE_GAP": features["close_gap"],
        "NOT_CLOSE_GAP": features["threshold_ready"] & ~features["close_gap"],
        "LOW_CONFIDENCE": features["low_confidence"],
        "NOT_LOW_CONFIDENCE": (
            features["threshold_ready"] & ~features["low_confidence"]
        ),
        "CLOSE_GAP_AND_LOW_CONF": (
            features["close_gap"] & features["low_confidence"]
        ),
        "CLOSE_GAP_AND_OK_CONF": (
            features["close_gap"]
            & features["threshold_ready"]
            & ~features["low_confidence"]
        ),
    }

    for name, mask in conditions.items():
        sub = features.loc[mask].copy()
        if sub.empty:
            continue

        r1 = pd.to_numeric(sub["rank1_raw_return"], errors="coerce")
        r2 = pd.to_numeric(sub["rank2_raw_return"], errors="coerce")
        spread = r1 - r2

        rows.append(
            {
                "condition": name,
                "n": int(len(sub)),
                "rank1_mean": float(r1.mean()),
                "rank2_mean": float(r2.mean()),
                "rank1_win_rate": float((r1 > 0).mean()),
                "rank2_win_rate": float((r2 > 0).mean()),
                "rank1_minus_rank2_mean": float(spread.mean()),
                "rank2_beats_rank1_rate": float((r2 > r1).mean()),
                "both_loss_rate": float(((r1 < 0) & (r2 < 0)).mean()),
                "rank1_loss_rank2_gain_rate": float(
                    ((r1 < 0) & (r2 > 0)).mean()
                ),
            }
        )

    return pd.DataFrame(rows)


def score_bucket_diagnostics(
    features: pd.DataFrame,
    *,
    buckets: int = 10,
) -> pd.DataFrame:
    z = features.loc[features["threshold_ready"]].copy()
    if z.empty:
        return pd.DataFrame()

    # This is descriptive only. qcut uses the full sample and MUST NOT be
    # used as a trading threshold. Trading strategies above use expanding,
    # lagged thresholds only.
    z["gap_decile"] = pd.qcut(
        z["relative_score_gap"],
        q=buckets,
        labels=False,
        duplicates="drop",
    )
    z["confidence_decile"] = pd.qcut(
        z["rank1_score"],
        q=buckets,
        labels=False,
        duplicates="drop",
    )

    rows: list[dict] = []
    for kind, col in [
        ("GAP", "gap_decile"),
        ("CONFIDENCE", "confidence_decile"),
    ]:
        for bucket, sub in z.groupby(col, dropna=True):
            r1 = sub["rank1_raw_return"]
            r2 = sub["rank2_raw_return"]
            rows.append(
                {
                    "dimension": kind,
                    "bucket": int(bucket) + 1,
                    "n": int(len(sub)),
                    "rank1_mean": float(r1.mean()),
                    "rank2_mean": float(r2.mean()),
                    "rank1_win_rate": float((r1 > 0).mean()),
                    "rank2_win_rate": float((r2 > 0).mean()),
                    "rank2_beats_rank1_rate": float((r2 > r1).mean()),
                    "both_loss_rate": float(((r1 < 0) & (r2 < 0)).mean()),
                    "mean_relative_gap": float(
                        sub["relative_score_gap"].mean()
                    ),
                    "mean_rank1_score": float(sub["rank1_score"].mean()),
                }
            )

    return pd.DataFrame(rows)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="R5.1 conditional Top1/Top2/cash allocation experiment"
    )
    p.add_argument(
        "--input",
        type=Path,
        default=(
            Path.home()
            / ".cache/kalman-r5-topk/output/"
            "r5_1_topk_portfolio_v1/"
            "r5_topk_common_trade_panel.parquet"
        ),
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=(
            Path.home()
            / ".cache/kalman-r5-topk/output/"
            "r5_1_conditional_allocation_v1"
        ),
    )
    p.add_argument("--cost-bps", type=float, default=10.0)
    p.add_argument("--min-history", type=int, default=100)
    p.add_argument("--gap-quantile", type=float, default=0.25)
    p.add_argument("--confidence-quantile", type=float, default=0.25)
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if not args.input.is_file():
        raise FileNotFoundError(args.input)

    panel = pd.read_parquet(args.input)

    features = prepare_features(
        panel,
        min_history=args.min_history,
        gap_quantile=args.gap_quantile,
        confidence_quantile=args.confidence_quantile,
    )

    detail, summary = evaluate(
        features,
        cost_bps=args.cost_bps,
    )
    diagnostics = conditional_diagnostics(features)
    buckets = score_bucket_diagnostics(features)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    features.to_parquet(
        args.output_dir / "r5_conditional_features.parquet",
        index=False,
    )
    detail.to_parquet(
        args.output_dir / "r5_conditional_trade_detail.parquet",
        index=False,
    )
    summary.to_csv(
        args.output_dir / "r5_conditional_summary.csv",
        index=False,
    )
    diagnostics.to_csv(
        args.output_dir / "r5_conditional_diagnostics.csv",
        index=False,
    )
    buckets.to_csv(
        args.output_dir / "r5_conditional_score_buckets.csv",
        index=False,
    )

    status = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "input": str(args.input),
        "rows": int(len(panel)),
        "threshold_ready_rows": int(features["threshold_ready"].sum()),
        "cost_bps": float(args.cost_bps),
        "min_history": int(args.min_history),
        "gap_quantile": float(args.gap_quantile),
        "confidence_quantile": float(args.confidence_quantile),
        "no_lookahead_thresholds": True,
        "strategies": STRATEGIES,
        "summary": summary.to_dict(orient="records"),
    }
    _write_json(args.output_dir / "status.json", status)

    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    print("\n===== SUMMARY =====")
    print(summary.to_csv(index=False))
    print("===== CONDITIONAL DIAGNOSTICS =====")
    print(diagnostics.to_csv(index=False))
    print("===== SCORE BUCKETS =====")
    print(buckets.to_csv(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
