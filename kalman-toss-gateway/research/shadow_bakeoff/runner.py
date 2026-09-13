from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.quant_stack.contracts import BacktestConfig
from research.quant_stack.historical_v2_candidate import _load_prices
from research.quant_stack.historical_v3_2_portfolio_validation import (
    build_pypfopt_targets_v32,
    corrected_portfolio_metrics,
    portfolio_equity_with_costs,
)
from research.quant_stack.historical_v3_3_robustness_hybrid import (
    _build_source_set_returns,
)
from research.quant_stack.historical_v3_4_allocator_regime_gate import (
    build_gate_targets,
)
from research.quant_stack.native_ledger import run_backtest
from research.shadow_bakeoff.forward_scorer import (
    append_signal_history,
    safe_signal_payload,
    score_v2_forward,
    score_v3_forward,
)


HYBRID_SOURCE = "HYBRID_USV2_KRV3_BTCV2"
MARKET_MODEL = {"US": "V2", "KR": "V3", "BTC": "V2"}
STRATEGIES = {
    "A_EQUAL_WEIGHT": "static_equal_weight",
    "B_STATIC_MAX_SHARPE": "static_max_sharpe",
    "C_RISK_CAP_110": "risk_cap_110",
}
LOOKBACK_DAYS = 180
MIN_OBSERVATIONS = 90
REBALANCE_FREQUENCY = "M"
PORTFOLIO_COST_BPS = 10.0
ANNUALIZATION_DAYS = 365
INITIAL_EQUITY = 1_000_000.0


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_research_only_v34(v34_summary: dict[str, Any]) -> None:
    if v34_summary.get("status") != "COMPLETE":
        raise RuntimeError("V3.4 summary is not COMPLETE")
    if v34_summary.get("selected_gate") != "risk_cap_110":
        raise RuntimeError("V3.4 selected gate is not risk_cap_110")
    if v34_summary.get("live_execution") is not False:
        raise RuntimeError("V3.4 live_execution invariant violated")
    if v34_summary.get("toss_execution") is not False:
        raise RuntimeError("V3.4 toss_execution invariant violated")
    if v34_summary.get("neon_write") is not False:
        raise RuntimeError("V3.4 neon_write invariant violated")


def _signal_frame(history: pd.DataFrame) -> pd.DataFrame:
    return history[
        ["symbol", "signal_ts", "signal", "entry_allowed"]
    ].copy()


def _forward_sleeve_equity(
    *,
    matrix_dir: Path,
    market: str,
    history: pd.DataFrame,
    v2_spec: dict[str, Any],
    v3_spec: dict[str, Any],
) -> pd.DataFrame:
    if history.empty:
        raise RuntimeError(f"{market}: empty forward signal history")
    if market in ("US", "BTC"):
        spec = v2_spec
        market_spec = spec["markets"][market]
        max_hold_bars = int(spec.get("max_hold_bars", 20))
    else:
        spec = v3_spec
        market_spec = spec["markets"][market]
        max_hold_bars = int(market_spec.get("max_hold_bars", 20))

    symbol = str(market_spec["symbol"])
    prices = _load_prices(matrix_dir, market, symbol)
    start = pd.to_datetime(
        history["signal_ts"],
        utc=True,
        errors="raise",
    ).min()
    prices = prices.loc[prices["ts"] >= start].copy()
    if prices.empty:
        raise RuntimeError(f"{market}: no prices after first shadow signal")

    result = run_backtest(
        _signal_frame(history),
        prices,
        BacktestConfig(
            initial_cash=INITIAL_EQUITY,
            position_fraction=1.0,
            max_open_positions=1,
            commission_bps=float(spec.get("commission_bps", 5.0)),
            slippage_bps=float(spec.get("slippage_bps", 5.0)),
            max_hold_bars=max_hold_bars,
            allow_fractional=True,
        ),
    )
    equity = result.equity.copy()
    equity["ts"] = pd.to_datetime(
        equity["ts"],
        utc=True,
        errors="raise",
    )
    return equity


def _equity_return_series(
    equity: pd.DataFrame,
    *,
    name: str,
) -> pd.Series:
    if equity.empty:
        return pd.Series(dtype=float, name=name)
    values = pd.Series(
        pd.to_numeric(equity["equity"], errors="coerce").to_numpy(dtype=float),
        index=pd.DatetimeIndex(equity["ts"]),
        name=name,
    )
    daily = (
        values.dropna()
        .sort_index()
        .groupby(level=0)
        .last()
        .resample("1D")
        .last()
        .ffill()
    )
    return daily.pct_change().rename(name)


def _stitch_returns(
    *,
    historical: pd.DataFrame,
    forward: dict[str, pd.Series],
    seed_end: pd.Timestamp,
) -> pd.DataFrame:
    pieces: dict[str, pd.Series] = {}
    for market in ("US", "KR", "BTC"):
        hist = pd.to_numeric(
            historical[market],
            errors="coerce",
        ).loc[historical.index <= seed_end]
        fwd = forward[market].loc[forward[market].index > seed_end]
        combined = pd.concat([hist, fwd]).sort_index()
        combined = combined[~combined.index.duplicated(keep="last")]
        pieces[market] = combined.rename(market)

    panel = pd.concat(pieces, axis=1).sort_index()
    panel = panel.dropna(how="any")
    if panel.empty:
        raise RuntimeError("stitched hybrid return panel is empty")
    return panel


def _latest_target(targets: pd.DataFrame) -> dict[str, float]:
    latest_ts = pd.to_datetime(
        targets["effective_ts"],
        utc=True,
        errors="raise",
    ).max()
    latest = targets.loc[
        pd.to_datetime(
            targets["effective_ts"],
            utc=True,
            errors="raise",
        )
        == latest_ts
    ]
    return {
        str(row.sleeve): float(row.target_weight)
        for row in latest.itertuples(index=False)
    }


def _forward_metrics(
    equity: pd.DataFrame,
    *,
    seed_end: pd.Timestamp,
) -> dict[str, Any] | None:
    frame = equity.copy()
    frame["ts"] = pd.to_datetime(
        frame["ts"],
        utc=True,
        errors="raise",
    )
    frame = frame.loc[frame["ts"] > seed_end].copy()
    if len(frame) < 2:
        return None

    net = pd.to_numeric(
        frame["net_portfolio_return"],
        errors="coerce",
    ).fillna(0.0)
    frame["equity"] = INITIAL_EQUITY * (1.0 + net).cumprod()
    return corrected_portfolio_metrics(
        frame,
        initial_equity=INITIAL_EQUITY,
        annualization_days=ANNUALIZATION_DAYS,
    )


def _strategy_outputs(
    *,
    returns: pd.DataFrame,
    output_root: Path,
) -> dict[str, Any]:
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
    gate_targets, gate_audit = build_gate_targets(
        returns,
        ew_targets,
        ms_targets,
        gate_name="risk_cap_110",
    )

    target_map = {
        "A_EQUAL_WEIGHT": ew_targets,
        "B_STATIC_MAX_SHARPE": ms_targets,
        "C_RISK_CAP_110": gate_targets,
    }
    out: dict[str, Any] = {}
    for name, targets in target_map.items():
        equity = portfolio_equity_with_costs(
            returns,
            targets,
            initial_equity=INITIAL_EQUITY,
            rebalance_cost_bps=PORTFOLIO_COST_BPS,
            charge_initial_allocation=True,
        )
        root = output_root / "strategies" / name.lower()
        root.mkdir(parents=True, exist_ok=True)
        targets.to_parquet(
            root / "portfolio_target.parquet",
            index=False,
        )
        equity.to_parquet(
            root / "portfolio_equity.parquet",
            index=False,
        )
        out[name] = {
            "latest_target": _latest_target(targets),
            "equity": equity,
        }

    gate_audit.to_csv(
        output_root / "strategies" / "c_risk_cap_110" / "gate_audit.csv",
        index=False,
    )
    return out


def _rank_forward(
    strategy_results: dict[str, dict[str, Any]],
    *,
    seed_end: pd.Timestamp,
) -> tuple[list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    for name, item in strategy_results.items():
        metrics = _forward_metrics(
            item["equity"],
            seed_end=seed_end,
        )
        if metrics is None:
            rows.append(
                {
                    "strategy": name,
                    "status": "WAITING_FOR_FORWARD_DATA",
                    "latest_target": item["latest_target"],
                }
            )
        else:
            rows.append(
                {
                    "strategy": name,
                    "status": "READY",
                    "latest_target": item["latest_target"],
                    **metrics,
                }
            )

    ready = [row for row in rows if row["status"] == "READY"]
    if not ready:
        return rows, "WAITING_FOR_FORWARD_DATA"

    ready.sort(
        key=lambda row: (
            float(row.get("sharpe") or -999.0),
            float(row.get("max_drawdown") or -999.0),
            float(row.get("total_return") or -999.0),
        ),
        reverse=True,
    )
    order = {row["strategy"]: i for i, row in enumerate(ready)}
    for row in rows:
        row["forward_rank"] = order.get(row["strategy"])
    return rows, "TRACKING"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Kalman file-only forward shadow bakeoff"
    )
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--v2-root", required=True)
    p.add_argument("--v3-root", required=True)
    p.add_argument("--v2-spec", required=True)
    p.add_argument("--v3-spec", required=True)
    p.add_argument("--v3-4-summary", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--code-sha", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    matrix_dir = Path(args.matrix_dir).expanduser()
    v2_root = Path(args.v2_root).expanduser()
    v3_root = Path(args.v3_root).expanduser()
    output_root = Path(args.output_dir).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)

    v2_spec = _load_json(Path(args.v2_spec).expanduser())
    v3_spec = _load_json(Path(args.v3_spec).expanduser())
    v34 = _load_json(Path(args.v3_4_summary).expanduser())
    _assert_research_only_v34(v34)

    hist_sets, hist_meta = _build_source_set_returns(
        v2_root=v2_root,
        v3_root=v3_root,
    )
    historical = hist_sets[HYBRID_SOURCE]
    seed_end = pd.Timestamp(hist_meta["shared_return_end"])
    if seed_end.tzinfo is None:
        seed_end = seed_end.tz_localize("UTC")
    else:
        seed_end = seed_end.tz_convert("UTC")

    score_payloads: dict[str, dict[str, Any]] = {}
    histories: dict[str, pd.DataFrame] = {}
    forward_equities: dict[str, pd.DataFrame] = {}
    forward_returns: dict[str, pd.Series] = {}

    latest_root = output_root / "latest"
    signal_root = output_root / "signals"
    sleeve_root = output_root / "sleeves"
    latest_root.mkdir(parents=True, exist_ok=True)

    for market in ("US", "KR", "BTC"):
        if MARKET_MODEL[market] == "V2":
            payload = score_v2_forward(
                matrix_dir=matrix_dir,
                market=market,
                spec=v2_spec,
            )
        else:
            payload = score_v3_forward(
                matrix_dir=matrix_dir,
                market=market,
                spec=v3_spec,
            )
        score_payloads[market] = payload

        diagnostic_date = pd.Timestamp(payload["as_of"]).strftime("%Y-%m-%d")
        _write_json(
            output_root
            / "diagnostics"
            / market.lower()
            / diagnostic_date
            / "forward_model.json",
            payload,
        )

        history_path = signal_root / market.lower() / "signal_history.parquet"
        history = append_signal_history(
            history_path,
            payload,
        )
        histories[market] = history

        _write_json(
            latest_root / f"{market.lower()}_signal.json",
            safe_signal_payload(payload),
        )

        equity = _forward_sleeve_equity(
            matrix_dir=matrix_dir,
            market=market,
            history=history,
            v2_spec=v2_spec,
            v3_spec=v3_spec,
        )
        forward_equities[market] = equity
        forward_returns[market] = _equity_return_series(
            equity,
            name=market,
        )
        sleeve_dir = sleeve_root / market.lower()
        sleeve_dir.mkdir(parents=True, exist_ok=True)
        equity.to_parquet(
            sleeve_dir / "forward_equity.parquet",
            index=False,
        )

    stitched = _stitch_returns(
        historical=historical,
        forward=forward_returns,
        seed_end=seed_end,
    )
    stitched.to_parquet(
        output_root / "hybrid_stitched_returns.parquet"
    )

    strategy_results = _strategy_outputs(
        returns=stitched,
        output_root=output_root,
    )
    ranking, tracking_status = _rank_forward(
        strategy_results,
        seed_end=seed_end,
    )

    latest_as_of = max(
        pd.Timestamp(payload["as_of"])
        for payload in score_payloads.values()
    )
    has_post_seed_signal = any(
        pd.Timestamp(payload["as_of"]) > seed_end
        for payload in score_payloads.values()
    )
    post_seed_return_rows = int(
        (stitched.index > seed_end).sum()
    )

    run_status = {
        "status": "READY",
        "tracking_status": tracking_status,
        "experiment": "FORWARD_SHADOW_BAKEOFF_V1",
        "code_sha": args.code_sha,
        "seed_end": seed_end,
        "latest_as_of": latest_as_of,
        "has_post_seed_signal": has_post_seed_signal,
        "post_seed_return_rows": post_seed_return_rows,
        "source_set": HYBRID_SOURCE,
        "market_models": MARKET_MODEL,
        "strategies": STRATEGIES,
        "forward_ranking": ranking,
        "signal_status": {
            market: safe_signal_payload(payload)
            for market, payload in score_payloads.items()
        },
        "invariants": {
            "file_only": True,
            "native_ledger_authoritative": True,
            "entry_allowed_for_real_orders": False,
            "dashboard_snapshot_created": False,
            "auto_trade_visible": False,
            "production_write": False,
            "neon_write": False,
            "toss_execution": False,
            "live_execution": False,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    _write_json(
        latest_root / "bakeoff_status.json",
        run_status,
    )
    date_key = latest_as_of.strftime("%Y-%m-%d")
    _write_json(
        output_root / "history" / date_key / "bakeoff_status.json",
        run_status,
    )

    print(json.dumps(run_status, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
