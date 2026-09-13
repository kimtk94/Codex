from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .historical_v3_2_portfolio_validation import (
    build_pypfopt_targets_v32,
    corrected_portfolio_metrics,
    portfolio_equity_with_costs,
)
from .historical_v3_3_robustness_hybrid import (
    SOURCE_SETS,
    _build_source_set_returns,
)

HYBRID_SOURCE = "HYBRID_USV2_KRV3_BTCV2"
LOOKBACK_DAYS = 180
MIN_OBSERVATIONS = 90
REBALANCE_FREQUENCY = "M"
REBALANCE_COST_BPS = 10.0
ANNUALIZATION_DAYS = 365
INITIAL_EQUITY = 1_000_000.0

RISK_CAPS = (1.10, 1.20, 1.30, 1.50)
CANDIDATE_GATES = (
    "static_equal_weight",
    "static_max_sharpe",
    "fallback_to_equal_weight",
    "risk_cap_110",
    "risk_cap_120",
    "risk_cap_130",
    "risk_cap_150",
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(weights: pd.Series, columns: list[str]) -> pd.Series:
    out = (
        pd.to_numeric(weights, errors="coerce")
        .reindex(columns)
        .fillna(0.0)
        .clip(lower=0.0)
    )
    total = float(out.sum())
    if total <= 0:
        raise RuntimeError("weights sum to zero")
    return out / total


def _covariance(history: pd.DataFrame) -> pd.DataFrame:
    clean = (
        history.copy()
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )
    cov = clean.cov() * ANNUALIZATION_DAYS
    cov = cov.reindex(index=clean.columns, columns=clean.columns).fillna(0.0)
    return cov


def _portfolio_vol(weights: pd.Series, cov: pd.DataFrame) -> float:
    w = weights.reindex(cov.columns).fillna(0.0).to_numpy(dtype=float)
    matrix = cov.to_numpy(dtype=float)
    variance = float(w @ matrix @ w)
    return math.sqrt(max(variance, 0.0))


def _blend_alpha_for_risk_cap(
    ew_weights: pd.Series,
    ms_weights: pd.Series,
    cov: pd.DataFrame,
    *,
    risk_cap_ratio: float,
    fallback: bool,
) -> tuple[float, float, float, float]:
    ew = _normalize(ew_weights, [str(x) for x in cov.columns])
    ms = _normalize(ms_weights, [str(x) for x in cov.columns])

    ew_vol = _portfolio_vol(ew, cov)
    ms_vol = _portfolio_vol(ms, cov)
    if ew_vol <= 0:
        return 0.0 if fallback else 1.0, ew_vol, ms_vol, ms_vol

    if fallback:
        return 0.0, ew_vol, ms_vol, ew_vol

    cap = ew_vol * float(risk_cap_ratio)
    if ms_vol <= cap:
        return 1.0, ew_vol, ms_vol, ms_vol

    best_alpha = 0.0
    best_vol = ew_vol
    for alpha in np.linspace(0.0, 1.0, 1001):
        blended = (1.0 - alpha) * ew + alpha * ms
        vol = _portfolio_vol(blended, cov)
        if vol <= cap + 1e-12:
            best_alpha = float(alpha)
            best_vol = float(vol)
    return best_alpha, ew_vol, ms_vol, best_vol


def _target_map(targets: pd.DataFrame) -> dict[pd.Timestamp, dict[str, Any]]:
    result: dict[pd.Timestamp, dict[str, Any]] = {}
    for ts, group in targets.groupby("effective_ts"):
        weights = pd.Series(
            {
                str(row.sleeve): float(row.target_weight)
                for row in group.itertuples(index=False)
            },
            dtype=float,
        )
        first = group.iloc[0]
        result[pd.Timestamp(ts)] = {
            "weights": weights,
            "optimization_status": str(first["optimization_status"]),
            "fallback_reason": first.get("fallback_reason"),
            "decision_ts": pd.Timestamp(first["decision_ts"]),
            "lookback_start": pd.Timestamp(first["lookback_start"]),
            "lookback_end": pd.Timestamp(first["lookback_end"]),
            "observations": int(first["observations"]),
        }
    return result


def _gate_name_from_cap(cap: float) -> str:
    return f"risk_cap_{int(round(cap * 100)):03d}"


def build_gate_targets(
    returns: pd.DataFrame,
    ew_targets: pd.DataFrame,
    ms_targets: pd.DataFrame,
    *,
    gate_name: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = [str(x) for x in returns.columns]
    ew_map = _target_map(ew_targets)
    ms_map = _target_map(ms_targets)
    common_dates = sorted(set(ew_map).intersection(ms_map))
    if not common_dates:
        raise RuntimeError("EW and Max-Sharpe targets have no common dates")

    cap_map = {
        _gate_name_from_cap(cap): cap
        for cap in RISK_CAPS
    }

    rows: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []

    for effective_ts in common_dates:
        ew_info = ew_map[effective_ts]
        ms_info = ms_map[effective_ts]
        ew = _normalize(ew_info["weights"], columns)
        ms = _normalize(ms_info["weights"], columns)

        history = returns.loc[
            (returns.index >= ms_info["lookback_start"])
            & (returns.index <= ms_info["lookback_end"])
        ].tail(LOOKBACK_DAYS)
        if len(history) < MIN_OBSERVATIONS:
            continue

        cov = _covariance(history)
        ms_status = str(ms_info["optimization_status"])
        fallback = ms_status != "READY"

        if gate_name == "static_equal_weight":
            alpha = 0.0
            ew_vol = _portfolio_vol(ew, cov)
            ms_vol = _portfolio_vol(ms, cov)
            blend_vol = ew_vol
        elif gate_name == "static_max_sharpe":
            alpha = 1.0
            ew_vol = _portfolio_vol(ew, cov)
            ms_vol = _portfolio_vol(ms, cov)
            blend_vol = ms_vol
        elif gate_name == "fallback_to_equal_weight":
            alpha = 0.0 if fallback else 1.0
            ew_vol = _portfolio_vol(ew, cov)
            ms_vol = _portfolio_vol(ms, cov)
            blend = (1.0 - alpha) * ew + alpha * ms
            blend_vol = _portfolio_vol(blend, cov)
        elif gate_name in cap_map:
            alpha, ew_vol, ms_vol, blend_vol = _blend_alpha_for_risk_cap(
                ew,
                ms,
                cov,
                risk_cap_ratio=cap_map[gate_name],
                fallback=fallback,
            )
        else:
            raise ValueError(f"unsupported gate: {gate_name}")

        blended = _normalize(
            (1.0 - alpha) * ew + alpha * ms,
            columns,
        )
        risk_ratio = ms_vol / ew_vol if ew_vol > 0 else math.nan
        blend_ratio = blend_vol / ew_vol if ew_vol > 0 else math.nan

        for sleeve, weight in blended.items():
            rows.append(
                {
                    "decision_ts": ms_info["decision_ts"],
                    "effective_ts": effective_ts,
                    "sleeve": sleeve,
                    "target_weight": float(weight),
                    "method": gate_name,
                    "lookback_start": ms_info["lookback_start"],
                    "lookback_end": ms_info["lookback_end"],
                    "observations": int(ms_info["observations"]),
                    "source": "KALMAN_V3_4_GATE",
                    "optimization_status": ms_status,
                    "fallback_reason": ms_info["fallback_reason"],
                    "annualization_days": ANNUALIZATION_DAYS,
                    "alpha_max_sharpe": float(alpha),
                    "predicted_vol_ratio": float(blend_ratio),
                }
            )

        audit.append(
            {
                "decision_ts": ms_info["decision_ts"],
                "effective_ts": effective_ts,
                "gate_name": gate_name,
                "alpha_max_sharpe": float(alpha),
                "fallback": bool(fallback),
                "max_sharpe_status": ms_status,
                "predicted_vol_equal_weight": float(ew_vol),
                "predicted_vol_max_sharpe": float(ms_vol),
                "predicted_vol_blend": float(blend_vol),
                "max_sharpe_to_equal_vol_ratio": float(risk_ratio),
                "blend_to_equal_vol_ratio": float(blend_ratio),
                "max_weight_max_sharpe": float(ms.max()),
                "hhi_max_sharpe": float((ms ** 2).sum()),
            }
        )

    target_frame = pd.DataFrame(rows)
    audit_frame = pd.DataFrame(audit)
    if target_frame.empty or audit_frame.empty:
        raise RuntimeError(f"{gate_name}: no gate targets generated")
    return target_frame, audit_frame


def _slice_and_rebase(
    equity: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    frame = equity.copy()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="raise")
    frame = frame.loc[(frame["ts"] >= start) & (frame["ts"] <= end)].copy()
    if frame.empty:
        return frame
    returns = pd.to_numeric(
        frame["net_portfolio_return"],
        errors="coerce",
    ).fillna(0.0)
    frame["equity"] = INITIAL_EQUITY * (1.0 + returns).cumprod()
    return frame.reset_index(drop=True)


def _metrics_for_window(
    equity: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    frame = _slice_and_rebase(equity, start=start, end=end)
    if len(frame) < 20:
        raise RuntimeError(f"window too short: {start} to {end}")
    return corrected_portfolio_metrics(
        frame,
        initial_equity=INITIAL_EQUITY,
        annualization_days=ANNUALIZATION_DAYS,
    )


def _rank_dev(rows: pd.DataFrame) -> pd.DataFrame:
    frame = rows.copy()
    dynamic = frame.loc[
        ~frame["gate_name"].isin(
            ["static_equal_weight", "static_max_sharpe"]
        )
    ].copy()
    if dynamic.empty:
        raise RuntimeError("no dynamic gate candidates")
    return dynamic.sort_values(
        [
            "sharpe",
            "max_drawdown",
            "total_return",
            "traded_notional_ratio_total",
        ],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)


def _compare_selected_to_benchmarks(
    recent: pd.DataFrame,
    selected_gate: str,
) -> dict[str, Any]:
    lookup = recent.set_index("gate_name")
    selected = lookup.loc[selected_gate]
    ew = lookup.loc["static_equal_weight"]
    ms = lookup.loc["static_max_sharpe"]

    selected_sharpe = float(selected["sharpe"])
    ew_sharpe = float(ew["sharpe"])
    ms_sharpe = float(ms["sharpe"])
    selected_return = float(selected["total_return"])
    best_return = max(float(ew["total_return"]), float(ms["total_return"]))

    sharpe_pass = (
        selected_sharpe >= ms_sharpe
        and selected_sharpe >= 0.95 * ew_sharpe
    )
    drawdown_pass = (
        float(selected["max_drawdown"])
        >= float(ms["max_drawdown"])
    )
    return_retention = (
        selected_return / best_return
        if best_return > 0
        else 1.0
    )
    return_pass = return_retention >= 0.85

    return {
        "selected_gate": selected_gate,
        "selected_recent_sharpe": selected_sharpe,
        "equal_weight_recent_sharpe": ew_sharpe,
        "max_sharpe_recent_sharpe": ms_sharpe,
        "selected_recent_return": selected_return,
        "best_static_recent_return": best_return,
        "return_retention": return_retention,
        "selected_recent_mdd": float(selected["max_drawdown"]),
        "max_sharpe_recent_mdd": float(ms["max_drawdown"]),
        "sharpe_pass": bool(sharpe_pass),
        "drawdown_pass": bool(drawdown_pass),
        "return_pass": bool(return_pass),
        "recent_gate_pass": bool(
            sharpe_pass and drawdown_pass and return_pass
        ),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Kalman V3.4 allocator regime gate"
    )
    p.add_argument("--v2-root", required=True)
    p.add_argument("--v3-root", required=True)
    p.add_argument("--v3-3-summary", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--code-sha", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    v2_root = Path(args.v2_root).expanduser()
    v3_root = Path(args.v3_root).expanduser()
    v33_summary_path = Path(args.v3_3_summary).expanduser()
    output_root = Path(args.output_dir).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)

    v33 = _load_json(v33_summary_path)
    if v33.get("status") != "COMPLETE":
        raise RuntimeError("V3.3 is not COMPLETE")
    if v33.get("experiment_status") != "READY":
        raise RuntimeError("V3.3 experiment is not READY")
    if (
        v33.get("recommendation", {})
        .get("recommended_source_set")
        != HYBRID_SOURCE
    ):
        raise RuntimeError("V3.3 winner is not the expected hybrid source")

    source_returns, source_metadata = _build_source_set_returns(
        v2_root=v2_root,
        v3_root=v3_root,
    )
    returns = source_returns[HYBRID_SOURCE]

    ew_targets = build_pypfopt_targets_v32(
        returns,
        method="equal_weight",
        lookback_days=LOOKBACK_DAYS,
        min_observations=MIN_OBSERVATIONS,
        rebalance_frequency=REBALANCE_FREQUENCY,
        annualization_days=ANNUALIZATION_DAYS,
    )
    ms_targets = build_pypfopt_targets_v32(
        returns,
        method="max_sharpe",
        lookback_days=LOOKBACK_DAYS,
        min_observations=MIN_OBSERVATIONS,
        rebalance_frequency=REBALANCE_FREQUENCY,
        annualization_days=ANNUALIZATION_DAYS,
    )

    recent_start = pd.Timestamp(
        v33["period_windows"]["RECENT"]["start"]
    )
    if recent_start.tzinfo is None:
        recent_start = recent_start.tz_localize("UTC")
    else:
        recent_start = recent_start.tz_convert("UTC")

    eval_start = max(
        pd.Timestamp(ew_targets["effective_ts"].min()),
        pd.Timestamp(ms_targets["effective_ts"].min()),
    )
    eval_end = pd.Timestamp(returns.index.max())
    dev_end = recent_start - pd.Timedelta(nanoseconds=1)

    all_rows: list[dict[str, Any]] = []
    audit_frames: list[pd.DataFrame] = []
    equity_by_gate: dict[str, pd.DataFrame] = {}

    for gate_name in CANDIDATE_GATES:
        targets, audit = build_gate_targets(
            returns,
            ew_targets,
            ms_targets,
            gate_name=gate_name,
        )
        equity = portfolio_equity_with_costs(
            returns,
            targets,
            initial_equity=INITIAL_EQUITY,
            rebalance_cost_bps=REBALANCE_COST_BPS,
            charge_initial_allocation=True,
        )
        equity_by_gate[gate_name] = equity
        audit_frames.append(audit)

        for period, start, end in [
            ("FULL", eval_start, eval_end),
            ("DEV", eval_start, dev_end),
            ("RECENT_HOLDOUT", recent_start, eval_end),
        ]:
            metrics = _metrics_for_window(
                equity,
                start=start,
                end=end,
            )
            all_rows.append(
                {
                    "gate_name": gate_name,
                    "period": period,
                    **metrics,
                }
            )

        gate_root = output_root / "gates" / gate_name
        gate_root.mkdir(parents=True, exist_ok=True)
        targets.to_parquet(
            gate_root / "portfolio_target.parquet",
            index=False,
        )
        audit.to_csv(
            gate_root / "gate_audit.csv",
            index=False,
        )
        equity.to_parquet(
            gate_root / "portfolio_equity.parquet",
            index=False,
        )

    metrics = pd.DataFrame(all_rows)
    audit_all = pd.concat(audit_frames, ignore_index=True)
    metrics.to_csv(
        output_root / "v3_4_gate_metrics.csv",
        index=False,
    )
    audit_all.to_csv(
        output_root / "v3_4_gate_audit.csv",
        index=False,
    )

    dev = metrics.loc[metrics["period"] == "DEV"].copy()
    recent = metrics.loc[
        metrics["period"] == "RECENT_HOLDOUT"
    ].copy()
    full = metrics.loc[metrics["period"] == "FULL"].copy()

    dev_ranking = _rank_dev(dev)
    dev_ranking.to_csv(
        output_root / "v3_4_dev_ranking.csv",
        index=False,
    )
    selected_gate = str(dev_ranking.iloc[0]["gate_name"])

    recent_comparison = _compare_selected_to_benchmarks(
        recent,
        selected_gate,
    )

    selected_audit = audit_all.loc[
        audit_all["gate_name"] == selected_gate
    ].copy()
    selected_recent_audit = selected_audit.loc[
        pd.to_datetime(
            selected_audit["effective_ts"],
            utc=True,
            errors="raise",
        )
        >= recent_start
    ]
    selected_dev_audit = selected_audit.loc[
        pd.to_datetime(
            selected_audit["effective_ts"],
            utc=True,
            errors="raise",
        )
        < recent_start
    ]

    alpha_summary = {
        "dev_mean_alpha_max_sharpe": float(
            selected_dev_audit["alpha_max_sharpe"].mean()
        ),
        "recent_mean_alpha_max_sharpe": float(
            selected_recent_audit["alpha_max_sharpe"].mean()
        ),
        "dev_gate_rebalance_count": int(len(selected_dev_audit)),
        "recent_gate_rebalance_count": int(len(selected_recent_audit)),
        "recent_equal_weight_dominant_count": int(
            (selected_recent_audit["alpha_max_sharpe"] < 0.5).sum()
        ),
        "recent_full_max_sharpe_count": int(
            np.isclose(
                selected_recent_audit["alpha_max_sharpe"],
                1.0,
            ).sum()
        ),
    }

    selected_full = full.loc[
        full["gate_name"] == selected_gate
    ].iloc[0].to_dict()
    ew_full = full.loc[
        full["gate_name"] == "static_equal_weight"
    ].iloc[0].to_dict()
    ms_full = full.loc[
        full["gate_name"] == "static_max_sharpe"
    ].iloc[0].to_dict()

    full_pass = (
        float(selected_full["sharpe"])
        >= min(
            float(ew_full["sharpe"]),
            float(ms_full["sharpe"]),
        )
        and float(selected_full["max_drawdown"])
        >= float(ms_full["max_drawdown"]) - 0.02
    )

    shadow_gate = (
        "PASS"
        if recent_comparison["recent_gate_pass"]
        and full_pass
        else "HOLD"
    )

    summary = {
        "status": "COMPLETE",
        "experiment_status": "READY",
        "experiment": "V3_4_ALLOCATOR_REGIME_GATE",
        "code_sha": args.code_sha,
        "source_set": HYBRID_SOURCE,
        "source_metadata": source_metadata,
        "configuration": {
            "lookback_days": LOOKBACK_DAYS,
            "min_observations": MIN_OBSERVATIONS,
            "rebalance_frequency": REBALANCE_FREQUENCY,
            "rebalance_cost_bps": REBALANCE_COST_BPS,
            "annualization_days": ANNUALIZATION_DAYS,
            "risk_caps": RISK_CAPS,
            "candidate_gates": CANDIDATE_GATES,
        },
        "selection_policy": {
            "selection_window": "DEV_ONLY",
            "dev_start": eval_start,
            "dev_end": dev_end,
            "recent_holdout_start": recent_start,
            "recent_holdout_end": eval_end,
            "ranking": (
                "Sharpe desc, max drawdown desc, total return desc, "
                "traded notional asc"
            ),
            "recent_not_used_for_gate_selection": True,
        },
        "selected_gate": selected_gate,
        "dev_ranking": dev_ranking.to_dict(orient="records"),
        "recent_comparison": recent_comparison,
        "alpha_summary": alpha_summary,
        "selected_full_metrics": selected_full,
        "static_equal_full_metrics": ew_full,
        "static_max_sharpe_full_metrics": ms_full,
        "full_gate_pass": bool(full_pass),
        "shadow_gate": shadow_gate,
        "promotion_recommendation": (
            "SHADOW_CANDIDATE"
            if shadow_gate == "PASS"
            else "RESEARCH_ONLY"
        ),
        "caveat": (
            "The gate family was motivated by the V3.3 recent-period "
            "failure, so a RECENT_HOLDOUT pass is diagnostic rather than "
            "a pristine untouched external holdout. SHADOW remains the "
            "next independent validation layer."
        ),
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _write_json(
        output_root / "v3_4_summary.json",
        summary,
    )

    print("\n" + "=" * 92)
    print("KALMAN V3.4 ALLOCATOR REGIME GATE COMPLETE")
    print("=" * 92)
    print("selected_gate:", selected_gate)
    print("shadow_gate:", shadow_gate)
    print("promotion_recommendation:", summary["promotion_recommendation"])
    print("\nDEV RANKING")
    print(dev_ranking.to_string(index=False))
    print("\nRECENT COMPARISON")
    print(json.dumps(recent_comparison, ensure_ascii=False, indent=2))
    print("\nALPHA SUMMARY")
    print(json.dumps(alpha_summary, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
