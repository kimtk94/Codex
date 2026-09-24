from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from research.quant_stack.open_revalidation_backtest import (
    _bootstrap_daily_delta,
    _fold_summary,
    _metrics,
    _write_json,
)


KEYS = ["symbol", "entry_timestamp", "exit_timestamp", "fold"]


def _load(path: Path, label: str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    z = pd.read_parquet(path).copy()
    required = {
        *KEYS,
        "candidate_net_return",
        "candidate_exit_reason",
        "candidate_exit_triggered",
        "replay_data_ready",
    }
    missing = required.difference(z.columns)
    if missing:
        raise RuntimeError(f"{label} audit missing columns: {sorted(missing)}")
    z["entry_timestamp"] = pd.to_datetime(z["entry_timestamp"], utc=True, errors="coerce")
    z["exit_timestamp"] = pd.to_datetime(z["exit_timestamp"], utc=True, errors="coerce")
    z = z.sort_values(KEYS).reset_index(drop=True)
    if not z["replay_data_ready"].fillna(False).astype(bool).all():
        raise RuntimeError(f"{label} audit contains non-ready rows")
    return z


def _reason(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "NO_EARLY_EXIT"
    text = str(value).strip()
    return text or "NO_EARLY_EXIT"


def compare(full: pd.DataFrame, noflip: pd.DataFrame, *, n_boot: int) -> dict[str, Any]:
    if len(full) != len(noflip):
        raise RuntimeError(f"row count mismatch: full={len(full)} noflip={len(noflip)}")

    for key in KEYS:
        left = full[key].astype(str).tolist()
        right = noflip[key].astype(str).tolist()
        if left != right:
            raise RuntimeError(f"trade identity mismatch in key={key}")

    frame = full[KEYS].copy()
    frame["net_return"] = pd.to_numeric(full["candidate_net_return"], errors="coerce")
    frame["candidate_net_return"] = pd.to_numeric(
        noflip["candidate_net_return"], errors="coerce"
    )
    frame["paired_delta_noflip_minus_full"] = (
        frame["candidate_net_return"] - frame["net_return"]
    )
    frame["full_exit_reason"] = [
        _reason(x) for x in full["candidate_exit_reason"].tolist()
    ]
    frame["noflip_exit_reason"] = [
        _reason(x) for x in noflip["candidate_exit_reason"].tolist()
    ]

    if frame[["net_return", "candidate_net_return"]].isna().any().any():
        raise RuntimeError("non-finite candidate returns found")

    full_metrics = _metrics(frame, "net_return")
    noflip_metrics = _metrics(frame, "candidate_net_return")
    boot = _bootstrap_daily_delta(
        frame,
        "candidate_net_return",
        n_boot=n_boot,
        seed=43,
    )
    folds = _fold_summary(frame, "candidate_net_return")

    delta_log = float(
        noflip_metrics["log_growth"] - full_metrics["log_growth"]
    )
    mdd_delta = float(noflip_metrics["mdd"] - full_metrics["mdd"])

    trade_delta = frame["paired_delta_noflip_minus_full"].astype(float)
    attribution: list[dict[str, Any]] = []
    for reason, part in frame.groupby("full_exit_reason", dropna=False):
        d = part["paired_delta_noflip_minus_full"].astype(float)
        attribution.append(
            {
                "full_policy_exit_reason": str(reason),
                "trades": int(len(part)),
                "noflip_minus_full_delta_sum": float(d.sum()),
                "mean_delta": float(d.mean()),
                "median_delta": float(d.median()),
                "noflip_better_rate": float((d > 0).mean()),
                "full_better_rate": float((d < 0).mean()),
                "equal_rate": float((d == 0).mean()),
            }
        )
    attribution.sort(
        key=lambda x: x["noflip_minus_full_delta_sum"],
        reverse=True,
    )

    transitions = (
        frame.groupby(["full_exit_reason", "noflip_exit_reason"], dropna=False)
        .size()
        .reset_index(name="trades")
        .sort_values("trades", ascending=False)
    )

    flip_rows = frame.loc[
        frame["full_exit_reason"].eq("PROFIT_TO_LOSS_FLIP")
    ].copy()
    flip_transitions = (
        flip_rows.groupby("noflip_exit_reason", dropna=False)
        .agg(
            trades=("symbol", "size"),
            delta_sum=("paired_delta_noflip_minus_full", "sum"),
            mean_delta=("paired_delta_noflip_minus_full", "mean"),
        )
        .reset_index()
        .sort_values("trades", ascending=False)
        .to_dict(orient="records")
    )

    result = {
        "schema": "kalman-live-policy-ablation-compare-v1",
        "research_only": True,
        "diagnostic_only": True,
        "production_changed": False,
        "automation_changed": False,
        "comparison": "NO_PROFIT_FLIP minus FULL_POLICY",
        "rows": int(len(frame)),
        "full_policy_metrics": full_metrics,
        "no_profit_flip_metrics": noflip_metrics,
        "delta_log_growth_noflip_minus_full": delta_log,
        "mdd_delta_noflip_minus_full": mdd_delta,
        "paired_bootstrap": boot,
        "folds": folds,
        "positive_folds": int(
            sum(
                1
                for row in folds
                if row.get("paired_log_delta") is not None
                and float(row["paired_log_delta"]) > 0
            )
        ),
        "trade_level": {
            "delta_sum": float(trade_delta.sum()),
            "mean_delta": float(trade_delta.mean()),
            "median_delta": float(trade_delta.median()),
            "noflip_better_rate": float((trade_delta > 0).mean()),
            "full_better_rate": float((trade_delta < 0).mean()),
            "equal_rate": float((trade_delta == 0).mean()),
        },
        "attribution_by_full_exit_reason": attribution,
        "transition_matrix": transitions.to_dict(orient="records"),
        "profit_flip_counterfactual_transitions": flip_transitions,
        "interpretation_guardrail": (
            "This is a post-hoc mechanism ablation on the same 2025 sample. "
            "It may identify which mechanism drove historical results, but it "
            "must not be treated as independent evidence for live promotion."
        ),
    }
    return result


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Direct paired comparison of SIP+BOATS full-policy and no-profit-flip audits."
    )
    root = Path("/mnt/gdrive/US_ETF/model_lab_v1/results")
    p.add_argument(
        "--full-audit",
        default=str(
            root
            / "live_policy_replay_v1_2025_sip_full"
            / "live_policy_replay_trade_audit.parquet"
        ),
    )
    p.add_argument(
        "--noflip-audit",
        default=str(
            root
            / "live_policy_replay_v1_2025_sip_no_profit_flip"
            / "live_policy_replay_trade_audit.parquet"
        ),
    )
    p.add_argument(
        "--output",
        default=str(
            root
            / "live_policy_replay_v1_2025_sip_no_profit_flip"
            / "noflip_vs_full_direct_comparison.json"
        ),
    )
    p.add_argument("--n-boot", type=int, default=20000)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.n_boot < 100 or args.n_boot > 100_000:
        raise RuntimeError("--n-boot must be between 100 and 100000")

    full = _load(Path(args.full_audit), "full")
    noflip = _load(Path(args.noflip_audit), "noflip")
    result = compare(full, noflip, n_boot=int(args.n_boot))
    _write_json(Path(args.output), result)

    boot = result["paired_bootstrap"]
    t = result["trade_level"]
    print("====================================================")
    print("NO PROFIT-FLIP vs FULL POLICY — DIRECT PAIRED COMPARISON")
    print("====================================================")
    print(f"rows={result['rows']}")
    print(
        "delta_log_growth_noflip_minus_full="
        f"{result['delta_log_growth_noflip_minus_full']}"
    )
    print(
        "mdd_delta_noflip_minus_full="
        f"{result['mdd_delta_noflip_minus_full']}"
    )
    print(
        f"positive_folds={result['positive_folds']}/{len(result['folds'])}"
    )
    print(f"bootstrap_ci95_low={boot.get('ci95_low')}")
    print(f"bootstrap_ci95_high={boot.get('ci95_high')}")
    print(f"bootstrap_p_one_sided={boot.get('p_one_sided')}")
    print(f"trade_delta_sum={t.get('delta_sum')}")
    print(f"noflip_better_rate={t.get('noflip_better_rate')}")
    print(f"full_better_rate={t.get('full_better_rate')}")
    print(f"equal_rate={t.get('equal_rate')}")

    print()
    print("ATTRIBUTION_BY_FULL_EXIT_REASON")
    for row in result["attribution_by_full_exit_reason"]:
        print(
            f"{row['full_policy_exit_reason']}: "
            f"trades={row['trades']} "
            f"delta_sum={row['noflip_minus_full_delta_sum']} "
            f"mean_delta={row['mean_delta']} "
            f"noflip_better_rate={row['noflip_better_rate']}"
        )

    print()
    print("PROFIT_FLIP_COUNTERFACTUAL_TRANSITIONS")
    for row in result["profit_flip_counterfactual_transitions"]:
        print(
            f"{row['noflip_exit_reason']}: "
            f"trades={row['trades']} "
            f"delta_sum={row['delta_sum']} "
            f"mean_delta={row['mean_delta']}"
        )

    print()
    print(f"output={args.output}")
    print("diagnostic_only=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
