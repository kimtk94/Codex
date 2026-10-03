#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


SCHEMA_VERSION = "kalman-r5-conditional-robustness-grid-v1"


def max_drawdown(returns: pd.Series) -> float:
    r = pd.to_numeric(returns, errors="coerce").fillna(0.0)
    if r.empty:
        return float("nan")
    wealth = (1.0 + r).cumprod()
    dd = wealth / wealth.cummax() - 1.0
    return float(dd.min())


def metrics(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {}

    r = pd.to_numeric(frame["net_return"], errors="coerce").dropna()
    if r.empty:
        return {}

    total_return = float((1.0 + r).prod() - 1.0)
    mdd = max_drawdown(r)

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

    trades_per_year = len(r) / years
    sd = float(r.std(ddof=0))
    sharpe = (
        float(r.mean() / sd * math.sqrt(trades_per_year))
        if sd > 0 and trades_per_year > 0
        else None
    )

    downside = r.loc[r < 0]
    downside_sd = (
        float(np.sqrt(np.mean(np.square(downside))))
        if len(downside)
        else 0.0
    )
    sortino = (
        float(r.mean() / downside_sd * math.sqrt(trades_per_year))
        if downside_sd > 0 and trades_per_year > 0
        else None
    )

    return {
        "trades": int(len(r)),
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": mdd,
        "cagr_over_abs_mdd": (
            float(cagr / abs(mdd)) if mdd < 0 else None
        ),
        "sharpe": sharpe,
        "sortino": sortino,
        "win_rate": float((r > 0).mean()),
        "mean_net_return": float(r.mean()),
        "median_net_return": float(r.median()),
        "best_trade": float(r.max()),
        "worst_trade": float(r.min()),
    }


def prepare_base(panel: pd.DataFrame) -> pd.DataFrame:
    z = panel.copy().sort_values(
        ["entry_timestamp", "expected_seq"]
    ).reset_index(drop=True)

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

    z["entry_timestamp"] = pd.to_datetime(
        z["entry_timestamp"], utc=True, errors="coerce"
    )
    z["exit_timestamp"] = pd.to_datetime(
        z["exit_timestamp"], utc=True, errors="coerce"
    )

    for c in [
        "rank1_score",
        "rank2_score",
        "rank1_raw_return",
        "rank2_raw_return",
    ]:
        z[c] = pd.to_numeric(z[c], errors="coerce")

    z["score_gap"] = z["rank1_score"] - z["rank2_score"]
    z["relative_score_gap"] = (
        z["score_gap"]
        / z["rank1_score"].abs().clip(lower=1e-12)
    )
    z["year"] = z["entry_timestamp"].dt.year.astype("Int64")
    return z


def add_thresholds(
    base: pd.DataFrame,
    *,
    min_history: int,
    gap_quantile: float,
    confidence_quantile: float,
) -> pd.DataFrame:
    z = base.copy()

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


def simulate(
    frame: pd.DataFrame,
    *,
    rank2_weight: float,
    cash_fraction_on_low_conf: float,
    cost_bps: float,
) -> pd.DataFrame:
    z = frame.copy()

    w1 = np.ones(len(z), dtype=float)
    w2 = np.zeros(len(z), dtype=float)
    cash = np.zeros(len(z), dtype=float)

    ready = z["threshold_ready"].to_numpy(dtype=bool)
    close_gap = z["close_gap"].to_numpy(dtype=bool)
    low_conf = z["low_confidence"].to_numpy(dtype=bool)

    # Precedence: low confidence -> cash reduction.
    # Otherwise, close score gap -> diversify into rank 2.
    low_idx = ready & low_conf
    gap_idx = ready & (~low_conf) & close_gap

    w1[low_idx] = 1.0 - cash_fraction_on_low_conf
    cash[low_idx] = cash_fraction_on_low_conf

    w1[gap_idx] = 1.0 - rank2_weight
    w2[gap_idx] = rank2_weight

    r1 = z["rank1_raw_return"].to_numpy(dtype=float)
    r2 = z["rank2_raw_return"].to_numpy(dtype=float)

    gross = w1 * r1 + w2 * r2
    invested = w1 + w2
    cost = (cost_bps / 10000.0) * invested
    net = gross - cost

    out = z[
        [
            "expected_seq",
            "entry_timestamp",
            "exit_timestamp",
            "year",
            "threshold_ready",
            "close_gap",
            "low_confidence",
        ]
    ].copy()
    out["rank1_weight"] = w1
    out["rank2_weight"] = w2
    out["cash_weight"] = cash
    out["gross_return"] = gross
    out["cost_return"] = cost
    out["net_return"] = net
    return out


def baseline_top1(
    base: pd.DataFrame,
    *,
    cost_bps: float,
) -> pd.DataFrame:
    out = base[
        ["expected_seq", "entry_timestamp", "exit_timestamp", "year"]
    ].copy()
    out["net_return"] = (
        base["rank1_raw_return"].astype(float)
        - cost_bps / 10000.0
    )
    return out


def period_rows(
    detail: pd.DataFrame,
    *,
    name: str,
    mask: pd.Series,
) -> dict:
    sub = detail.loc[mask].copy()
    m = metrics(sub)
    return {
        "period": name,
        **m,
    }


def evaluate_periods(detail: pd.DataFrame) -> list[dict]:
    years = detail["year"]

    rows = [
        period_rows(
            detail,
            name="ALL",
            mask=pd.Series(True, index=detail.index),
        ),
        period_rows(
            detail,
            name="DEV_2023_2024",
            mask=years.isin([2023, 2024]),
        ),
        period_rows(
            detail,
            name="VAL_2025",
            mask=years.eq(2025),
        ),
        period_rows(
            detail,
            name="HOLDOUT_2026",
            mask=years.eq(2026),
        ),
    ]

    for year in sorted(int(y) for y in years.dropna().unique()):
        rows.append(
            period_rows(
                detail,
                name=str(year),
                mask=years.eq(year),
            )
        )
    return rows


def summarize_config(
    *,
    config_id: str,
    gap_quantile: float,
    confidence_quantile: float,
    rank2_weight: float,
    cash_fraction: float,
    detail: pd.DataFrame,
    baseline_periods: dict[str, dict],
) -> tuple[list[dict], dict]:
    period_out: list[dict] = []

    for row in evaluate_periods(detail):
        period = row["period"]
        baseline = baseline_periods.get(period, {})
        enriched = {
            "config_id": config_id,
            "gap_quantile": gap_quantile,
            "confidence_quantile": confidence_quantile,
            "rank2_weight": rank2_weight,
            "cash_fraction": cash_fraction,
            **row,
            "delta_cagr_vs_top1": (
                row.get("cagr") - baseline.get("cagr")
                if row.get("cagr") is not None
                and baseline.get("cagr") is not None
                else None
            ),
            "delta_mdd_vs_top1": (
                row.get("max_drawdown") - baseline.get("max_drawdown")
                if row.get("max_drawdown") is not None
                and baseline.get("max_drawdown") is not None
                else None
            ),
            "delta_sharpe_vs_top1": (
                row.get("sharpe") - baseline.get("sharpe")
                if row.get("sharpe") is not None
                and baseline.get("sharpe") is not None
                else None
            ),
        }
        period_out.append(enriched)

    by_period = {x["period"]: x for x in period_out}
    all_m = by_period["ALL"]
    val = by_period["VAL_2025"]
    hold = by_period["HOLDOUT_2026"]

    yearly = [
        x for x in period_out
        if x["period"] in {"2023", "2024", "2025", "2026"}
    ]

    positive_years = sum(
        1 for x in yearly
        if x.get("total_return") is not None
        and x["total_return"] > 0
    )
    beats_top1_cagr_years = sum(
        1 for x in yearly
        if x.get("delta_cagr_vs_top1") is not None
        and x["delta_cagr_vs_top1"] > 0
    )

    stability = {
        "config_id": config_id,
        "gap_quantile": gap_quantile,
        "confidence_quantile": confidence_quantile,
        "rank2_weight": rank2_weight,
        "cash_fraction": cash_fraction,
        "all_cagr": all_m.get("cagr"),
        "all_mdd": all_m.get("max_drawdown"),
        "all_cagr_over_abs_mdd": all_m.get("cagr_over_abs_mdd"),
        "all_sharpe": all_m.get("sharpe"),
        "all_delta_cagr_vs_top1": all_m.get("delta_cagr_vs_top1"),
        "all_delta_mdd_vs_top1": all_m.get("delta_mdd_vs_top1"),
        "val_2025_cagr": val.get("cagr"),
        "val_2025_delta_cagr_vs_top1": val.get("delta_cagr_vs_top1"),
        "val_2025_delta_mdd_vs_top1": val.get("delta_mdd_vs_top1"),
        "holdout_2026_cagr": hold.get("cagr"),
        "holdout_2026_delta_cagr_vs_top1": hold.get("delta_cagr_vs_top1"),
        "holdout_2026_delta_mdd_vs_top1": hold.get("delta_mdd_vs_top1"),
        "positive_years": positive_years,
        "beats_top1_cagr_years": beats_top1_cagr_years,
        "min_year_cagr": min(
            x["cagr"] for x in yearly
            if x.get("cagr") is not None
        ),
        "max_year_mdd_abs": max(
            abs(x["max_drawdown"]) for x in yearly
            if x.get("max_drawdown") is not None
        ),
        "close_gap_trades": int(detail["close_gap"].sum()),
        "low_confidence_trades": int(detail["low_confidence"].sum()),
        "mean_rank1_weight": float(detail["rank1_weight"].mean()),
        "mean_rank2_weight": float(detail["rank2_weight"].mean()),
        "mean_cash_weight": float(detail["cash_weight"].mean()),
    }

    # Robustness flags are descriptive gates, not an optimization target.
    stability["passes_2025_2026_nonnegative_delta"] = bool(
        (stability["val_2025_delta_cagr_vs_top1"] or 0.0) >= 0
        and (stability["holdout_2026_delta_cagr_vs_top1"] or 0.0) >= 0
    )
    stability["passes_overall_cagr_and_mdd"] = bool(
        (stability["all_delta_cagr_vs_top1"] or 0.0) >= 0
        and (stability["all_delta_mdd_vs_top1"] or 0.0) >= 0
    )
    stability["robust_candidate"] = bool(
        stability["passes_2025_2026_nonnegative_delta"]
        and stability["passes_overall_cagr_and_mdd"]
        and stability["positive_years"] >= 4
    )

    return period_out, stability


def parse_float_list(text: str) -> list[float]:
    return [float(x.strip()) for x in text.split(",") if x.strip()]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "R5.1 no-lookahead conditional-allocation robustness grid"
        )
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
            "r5_1_conditional_robustness_v1"
        ),
    )
    p.add_argument("--cost-bps", type=float, default=10.0)
    p.add_argument("--min-history", type=int, default=100)
    p.add_argument(
        "--gap-quantiles",
        default="0.10,0.15,0.20,0.25,0.30,0.35,0.40",
    )
    p.add_argument(
        "--confidence-quantiles",
        default="0.10,0.15,0.20,0.25,0.30,0.35,0.40",
    )
    p.add_argument(
        "--rank2-weights",
        default="0.10,0.20,0.30,0.40,0.50",
    )
    p.add_argument(
        "--cash-fractions",
        default="0.25,0.50,0.75",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if not args.input.is_file():
        raise FileNotFoundError(args.input)

    panel = pd.read_parquet(args.input)
    base = prepare_base(panel)

    baseline = baseline_top1(base, cost_bps=args.cost_bps)
    baseline_period_rows = evaluate_periods(baseline)
    baseline_periods = {
        row["period"]: row for row in baseline_period_rows
    }

    gap_qs = parse_float_list(args.gap_quantiles)
    conf_qs = parse_float_list(args.confidence_quantiles)
    rank2_ws = parse_float_list(args.rank2_weights)
    cash_fs = parse_float_list(args.cash_fractions)

    all_period_rows: list[dict] = []
    stability_rows: list[dict] = []

    threshold_cache: dict[tuple[float, float], pd.DataFrame] = {}

    total = len(gap_qs) * len(conf_qs) * len(rank2_ws) * len(cash_fs)
    done = 0

    for gq, cq in itertools.product(gap_qs, conf_qs):
        key = (gq, cq)
        if key not in threshold_cache:
            threshold_cache[key] = add_thresholds(
                base,
                min_history=args.min_history,
                gap_quantile=gq,
                confidence_quantile=cq,
            )

        feature_frame = threshold_cache[key]

        for r2w, cashf in itertools.product(rank2_ws, cash_fs):
            done += 1
            config_id = (
                f"GQ{int(round(gq*100)):02d}_"
                f"CQ{int(round(cq*100)):02d}_"
                f"R2W{int(round(r2w*100)):02d}_"
                f"CASH{int(round(cashf*100)):02d}"
            )

            detail = simulate(
                feature_frame,
                rank2_weight=r2w,
                cash_fraction_on_low_conf=cashf,
                cost_bps=args.cost_bps,
            )

            period_rows, stability = summarize_config(
                config_id=config_id,
                gap_quantile=gq,
                confidence_quantile=cq,
                rank2_weight=r2w,
                cash_fraction=cashf,
                detail=detail,
                baseline_periods=baseline_periods,
            )
            all_period_rows.extend(period_rows)
            stability_rows.append(stability)

            if done % 100 == 0 or done == total:
                print(f"[GRID] {done}/{total}", flush=True)

    period_df = pd.DataFrame(all_period_rows)
    stability_df = pd.DataFrame(stability_rows)

    # Sort for inspection only; do not treat this as a model-selection winner.
    stability_df = stability_df.sort_values(
        [
            "robust_candidate",
            "passes_2025_2026_nonnegative_delta",
            "all_cagr_over_abs_mdd",
            "all_cagr",
        ],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    baseline_df = pd.DataFrame(baseline_period_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    baseline_df.to_csv(
        args.output_dir / "r5_robustness_top1_baseline.csv",
        index=False,
    )
    period_df.to_parquet(
        args.output_dir / "r5_robustness_period_metrics.parquet",
        index=False,
    )
    stability_df.to_csv(
        args.output_dir / "r5_robustness_grid_summary.csv",
        index=False,
    )

    robust = stability_df.loc[
        stability_df["robust_candidate"].eq(True)
    ].copy()
    robust.to_csv(
        args.output_dir / "r5_robustness_candidates.csv",
        index=False,
    )

    status = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "input": str(args.input),
        "rows": int(len(base)),
        "grid_configs": int(len(stability_df)),
        "robust_candidates": int(len(robust)),
        "cost_bps": float(args.cost_bps),
        "min_history": int(args.min_history),
        "gap_quantiles": gap_qs,
        "confidence_quantiles": conf_qs,
        "rank2_weights": rank2_ws,
        "cash_fractions": cash_fs,
        "no_lookahead_thresholds": True,
        "periods": [
            "DEV_2023_2024",
            "VAL_2025",
            "HOLDOUT_2026",
        ],
    }

    (args.output_dir / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(status, ensure_ascii=False, indent=2))
    print("\n===== TOP 20 ROBUSTNESS TABLE =====")
    cols = [
        "config_id",
        "gap_quantile",
        "confidence_quantile",
        "rank2_weight",
        "cash_fraction",
        "all_cagr",
        "all_mdd",
        "all_cagr_over_abs_mdd",
        "all_sharpe",
        "all_delta_cagr_vs_top1",
        "all_delta_mdd_vs_top1",
        "val_2025_delta_cagr_vs_top1",
        "holdout_2026_delta_cagr_vs_top1",
        "positive_years",
        "beats_top1_cagr_years",
        "robust_candidate",
    ]
    print(stability_df[cols].head(20).to_csv(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
