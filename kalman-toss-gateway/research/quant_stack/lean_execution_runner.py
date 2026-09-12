from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from .contracts import Mode
from .lean_execution import (
    ExecutionPolicy,
    ExecutionState,
    PortfolioTargetContract,
    mark_to_market_equity,
    run_shadow_rebalance,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run LEAN-inspired Kalman execution contract in SHADOW mode"
    )
    p.add_argument("--output-dir", required=True)
    p.add_argument("--initial-cash", type=float, default=1_000_000.0)
    p.add_argument("--max-symbol-weight", type=float, default=0.75)
    p.add_argument("--max-gross-weight", type=float, default=1.0)
    p.add_argument("--min-order-notional", type=float, default=10.0)
    p.add_argument("--max-single-order-fraction", type=float, default=0.80)
    p.add_argument("--max-total-turnover-fraction", type=float, default=2.0)
    p.add_argument("--slippage-bps", type=float, default=0.0)
    p.add_argument("--commission-bps", type=float, default=0.0)
    return p.parse_args()


def _daily_equity(path: Path, sleeve: str) -> pd.Series:
    frame = pd.read_parquet(path)
    required = {"ts", "equity"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} missing columns: {sorted(missing)}")
    out = frame.copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True, errors="raise")
    out["equity"] = pd.to_numeric(out["equity"], errors="coerce")
    series = (
        out.dropna(subset=["ts", "equity"])
        .sort_values("ts")
        .drop_duplicates("ts", keep="last")
        .set_index("ts")["equity"]
        .resample("1D")
        .last()
        .ffill()
    )
    series.name = sleeve
    return series


def load_normalized_sleeve_navs(
    output_root: Path,
    sleeves: list[str],
) -> pd.DataFrame:
    series = []
    for sleeve in sleeves:
        path = output_root / sleeve.lower() / "historical_equity.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        series.append(_daily_equity(path, sleeve))

    panel = pd.concat(series, axis=1).sort_index().ffill().dropna(how="any")
    if panel.empty:
        raise RuntimeError("no overlapping sleeve equity history")
    first = panel.iloc[0]
    if (first <= 0).any():
        raise RuntimeError("sleeve equity must be positive for NAV normalization")
    return panel.divide(first, axis=1) * 100.0


def execution_price_points(
    navs: pd.DataFrame,
    effective_ts: pd.Timestamp,
) -> tuple[pd.Timestamp, dict[str, float], pd.Timestamp, dict[str, float]]:
    effective_ts = pd.Timestamp(effective_ts)
    if effective_ts.tzinfo is None:
        effective_ts = effective_ts.tz_localize("UTC")
    else:
        effective_ts = effective_ts.tz_convert("UTC")

    before = navs.loc[navs.index < effective_ts]
    after = navs.loc[navs.index >= effective_ts]
    if before.empty:
        raise RuntimeError(f"no planning NAV strictly before {effective_ts}")
    if after.empty:
        raise RuntimeError(f"no fill NAV on/after {effective_ts}")

    planning_ts = pd.Timestamp(before.index[-1])
    fill_ts = pd.Timestamp(after.index[0])
    planning_prices = {
        str(symbol): float(value)
        for symbol, value in before.iloc[-1].items()
    }
    fill_prices = {
        str(symbol): float(value)
        for symbol, value in after.iloc[0].items()
    }
    return planning_ts, planning_prices, fill_ts, fill_prices


def _flatten_gated(item) -> dict[str, Any]:
    row = asdict(item.intent)
    row["status"] = item.status
    row["risk_reason"] = item.risk_reason
    return row


def run_execution_contract(
    output_root: Path,
    *,
    initial_cash: float,
    policy: ExecutionPolicy,
) -> dict[str, Any]:
    target_path = output_root / "portfolio" / "portfolio_target.parquet"
    if not target_path.exists():
        raise FileNotFoundError(target_path)

    targets = pd.read_parquet(target_path)
    required = {
        "decision_ts",
        "effective_ts",
        "sleeve",
        "target_weight",
        "method",
        "source",
    }
    missing = required.difference(targets.columns)
    if missing:
        raise ValueError(f"portfolio_target missing columns: {sorted(missing)}")

    targets = targets.copy()
    targets["decision_ts"] = pd.to_datetime(
        targets["decision_ts"], utc=True, errors="raise"
    )
    targets["effective_ts"] = pd.to_datetime(
        targets["effective_ts"], utc=True, errors="raise"
    )
    sleeves = sorted(str(x) for x in targets["sleeve"].dropna().unique())
    if len(sleeves) < 2:
        raise RuntimeError("execution contract requires at least two sleeves")

    navs = load_normalized_sleeve_navs(output_root, sleeves)
    state = ExecutionState(cash=float(initial_cash), positions={})

    adjusted_rows: list[dict[str, Any]] = []
    intent_rows: list[dict[str, Any]] = []
    order_rows: list[dict[str, Any]] = []
    fill_rows: list[dict[str, Any]] = []
    ledger_rows: list[dict[str, Any]] = []

    for effective_ts, group in targets.sort_values(
        ["effective_ts", "sleeve"]
    ).groupby("effective_ts"):
        planning_ts, planning_prices, fill_ts, fill_prices = execution_price_points(
            navs,
            pd.Timestamp(effective_ts),
        )

        method = str(group["method"].iloc[0])
        run_id = f"portfolio-rebalance-{pd.Timestamp(effective_ts).isoformat()}"
        contracts = [
            PortfolioTargetContract.build(
                run_id=run_id,
                strategy_version=f"portfolio-{method}",
                symbol=str(row.sleeve),
                decision_ts=pd.Timestamp(row.decision_ts).isoformat(),
                effective_ts=pd.Timestamp(row.effective_ts).isoformat(),
                target_weight=float(row.target_weight),
                source=str(row.source),
            )
            for row in group.itertuples(index=False)
        ]

        cycle = run_shadow_rebalance(
            contracts,
            state=state,
            planning_prices=planning_prices,
            fill_prices=fill_prices,
            fill_ts=fill_ts.isoformat(),
            policy=policy,
            mode=Mode.SHADOW,
        )

        adjusted_rows.extend(asdict(row) for row in cycle.adjusted_targets)
        intent_rows.extend(_flatten_gated(row) for row in cycle.gated_intents)
        order_rows.extend(asdict(row) for row in cycle.broker_orders)
        fill_rows.extend(asdict(row) for row in cycle.fills)

        state = cycle.state
        equity = mark_to_market_equity(state, fill_prices)
        ledger_rows.append(
            {
                "effective_ts": pd.Timestamp(effective_ts),
                "planning_price_ts": planning_ts,
                "fill_ts": fill_ts,
                "cash": float(state.cash),
                "equity": float(equity),
                "positions_json": json.dumps(
                    state.positions,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "broker": "SHADOW",
                "mode": "SHADOW",
            }
        )

    execution_dir = output_root / "execution"
    execution_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(adjusted_rows).to_parquet(
        execution_dir / "portfolio_target_risk_adjusted.parquet",
        index=False,
    )
    pd.DataFrame(intent_rows).to_parquet(
        execution_dir / "order_intent.parquet",
        index=False,
    )
    pd.DataFrame(order_rows).to_parquet(
        execution_dir / "broker_order.parquet",
        index=False,
    )
    pd.DataFrame(fill_rows).to_parquet(
        execution_dir / "execution_fill.parquet",
        index=False,
    )
    pd.DataFrame(ledger_rows).to_parquet(
        execution_dir / "execution_ledger.parquet",
        index=False,
    )

    status = {
        "status": "READY",
        "architecture_reference": "QUANTCONNECT_LEAN_ALGORITHM_FRAMEWORK",
        "mode": "SHADOW",
        "broker": "SHADOW",
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
        "sleeves": sleeves,
        "risk_adjusted_target_rows": len(adjusted_rows),
        "order_intent_rows": len(intent_rows),
        "approved_intent_rows": sum(
            1 for row in intent_rows if row.get("status") == "APPROVED"
        ),
        "broker_order_rows": len(order_rows),
        "execution_fill_rows": len(fill_rows),
        "ledger_snapshots": len(ledger_rows),
        "final_cash": float(state.cash),
        "final_positions": state.positions,
    }
    (execution_dir / "execution_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return status


def main() -> int:
    args = parse_args()
    policy = ExecutionPolicy(
        max_symbol_weight=args.max_symbol_weight,
        max_gross_weight=args.max_gross_weight,
        min_order_notional=args.min_order_notional,
        max_single_order_fraction=args.max_single_order_fraction,
        max_total_turnover_fraction=args.max_total_turnover_fraction,
        broker="SHADOW",
        slippage_bps=args.slippage_bps,
        commission_bps=args.commission_bps,
        allow_live_execution=False,
    )
    status = run_execution_contract(
        Path(args.output_dir).expanduser(),
        initial_cash=args.initial_cash,
        policy=policy,
    )
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
