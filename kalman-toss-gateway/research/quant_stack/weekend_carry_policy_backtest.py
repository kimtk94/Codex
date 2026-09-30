from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NY = ZoneInfo("America/New_York")
POLICIES = ("DAILY_FLAT", "WEEKDAY_CARRY_FRIDAY_FLAT", "CARRY_ALL")


@dataclass(frozen=True)
class ReconstructionSpec:
    name: str
    left_closed: bool
    right_closed: bool
    method: str


def _select_bars(
    bars: pd.DataFrame,
    entry_seq: int,
    exit_seq: int,
    *,
    left_closed: bool,
    right_closed: bool,
) -> pd.DataFrame:
    left = bars["expected_seq"].ge(entry_seq) if left_closed else bars["expected_seq"].gt(entry_seq)
    right = bars["expected_seq"].le(exit_seq) if right_closed else bars["expected_seq"].lt(exit_seq)
    return bars.loc[left & right].sort_values(["expected_seq", "timestamp"])


def _aggregate_return(values: pd.Series, method: str) -> float:
    arr = pd.to_numeric(values, errors="coerce").dropna().astype(float).to_numpy()
    if arr.size == 0:
        return 0.0
    if method == "sum":
        return float(arr.sum())
    if method == "compound":
        return float(np.prod(1.0 + arr) - 1.0)
    raise ValueError(method)


def _reconstruct_paths(ledger: pd.DataFrame, bars: pd.DataFrame):
    specs = [
        ReconstructionSpec("gt_le_sum", False, True, "sum"),
        ReconstructionSpec("gt_le_compound", False, True, "compound"),
        ReconstructionSpec("ge_lt_sum", True, False, "sum"),
        ReconstructionSpec("ge_lt_compound", True, False, "compound"),
        ReconstructionSpec("ge_le_sum", True, True, "sum"),
        ReconstructionSpec("ge_le_compound", True, True, "compound"),
        ReconstructionSpec("gt_lt_sum", False, False, "sum"),
        ReconstructionSpec("gt_lt_compound", False, False, "compound"),
    ]

    bar_groups = {
        key: g.copy()
        for key, g in bars.groupby(["fold", "symbol"], sort=False)
    }

    diagnostics = []
    cached = {}

    for spec in specs:
        errs = []
        coverage = 0
        bar_counts = []
        paths = []
        for idx, row in ledger.iterrows():
            key = (row["fold"], row["symbol"])
            g = bar_groups.get(key)
            if g is None:
                paths.append(None)
                continue
            p = _select_bars(
                g,
                int(row["entry_seq"]),
                int(row["exit_seq"]),
                left_closed=spec.left_closed,
                right_closed=spec.right_closed,
            )
            paths.append(p)
            if len(p):
                coverage += 1
                bar_counts.append(len(p))
                pred = _aggregate_return(p["gross_bar_return"], spec.method)
                errs.append(abs(pred - float(row["gross_return"])))
        diagnostics.append(
            {
                "spec": spec.name,
                "coverage": coverage / max(1, len(ledger)),
                "median_abs_recon_error": float(np.median(errs)) if errs else math.inf,
                "mean_abs_recon_error": float(np.mean(errs)) if errs else math.inf,
                "median_bar_count": float(np.median(bar_counts)) if bar_counts else 0.0,
            }
        )
        cached[spec.name] = paths

    diagnostics.sort(key=lambda x: (-x["coverage"], x["median_abs_recon_error"], x["mean_abs_recon_error"]))
    best_diag = diagnostics[0]
    best = next(s for s in specs if s.name == best_diag["spec"])
    if best_diag["coverage"] < 0.95:
        raise RuntimeError(f"Bar-path coverage too low: {best_diag}")
    return best, cached[best.name], diagnostics


def _trade_path_for_policy(path: pd.DataFrame, entry_ts: pd.Timestamp, policy: str) -> pd.DataFrame:
    if path is None or path.empty or policy == "CARRY_ALL":
        return path

    p = path.copy()
    ts = pd.to_datetime(p["timestamp"], utc=True).dt.tz_convert(NY)
    entry_local = pd.Timestamp(entry_ts).tz_convert(NY)
    dates = ts.dt.date

    if policy == "DAILY_FLAT":
        keep = dates == entry_local.date()
        selected = p.loc[keep]
        if selected.empty:
            # No full canonical bar before the session ends. Treat the trade as
            # flat-at-entry for the structural comparison rather than borrowing
            # a next-session return.
            return p.iloc[0:0]
        return selected

    if policy == "WEEKDAY_CARRY_FRIDAY_FLAT":
        rows = list(zip(p.index, ts))
        cut_pos = None
        for i in range(len(rows) - 1):
            _, cur = rows[i]
            _, nxt = rows[i + 1]
            gap_days = (nxt.date() - cur.date()).days
            crosses_weekend = cur.weekday() == 4 and nxt.date() > cur.date()
            long_nontrading_gap = gap_days >= 3
            if crosses_weekend or long_nontrading_gap:
                cut_pos = i
                break
        if cut_pos is None:
            return p
        return p.iloc[: cut_pos + 1]

    raise ValueError(policy)


def _max_drawdown(returns: np.ndarray) -> float:
    if len(returns) == 0:
        return 0.0
    eq = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(np.r_[1.0, eq])[1:]
    dd = eq / peak - 1.0
    return float(dd.min())


def _paired_bootstrap(delta: np.ndarray, seed: int = 20261001, n_boot: int = 10000):
    delta = np.asarray(delta, dtype=float)
    delta = delta[np.isfinite(delta)]
    if len(delta) == 0:
        return {"mean": None, "ci95_low": None, "ci95_high": None, "p_le_zero": None}
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot, dtype=float)
    n = len(delta)
    for i in range(n_boot):
        sample = delta[rng.integers(0, n, n)]
        means[i] = sample.mean()
    return {
        "mean": float(delta.mean()),
        "ci95_low": float(np.quantile(means, 0.025)),
        "ci95_high": float(np.quantile(means, 0.975)),
        "p_le_zero": float((means <= 0).mean()),
    }


def _metrics(df: pd.DataFrame) -> dict:
    r = df["net_return"].astype(float).to_numpy()
    log_growth = float(np.log1p(np.clip(r, -0.999999999, None)).sum())
    cum_return = float(np.exp(log_growth) - 1.0)
    return {
        "trades": int(len(df)),
        "cum_return": cum_return,
        "log_growth": log_growth,
        "mdd_trade_path": _max_drawdown(r),
        "hit_rate": float((r > 0).mean()) if len(r) else None,
        "mean_trade_return": float(r.mean()) if len(r) else None,
        "median_trade_return": float(np.median(r)) if len(r) else None,
        "overnight_exposure_trades": int(df["spans_overnight"].sum()),
        "weekend_exposure_trades": int(df["spans_weekend"].sum()),
        "zero_bar_flat_trades": int((df["selected_bar_count"] == 0).sum()),
        "truncated_trades": int((df["selected_bar_count"] < df["full_bar_count"]).sum()),
        "mean_selected_bars": float(df["selected_bar_count"].mean()) if len(df) else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--ledger",
        default="/mnt/gdrive/US_ETF/model_lab_v1/results/exit_policy_v1_0_pre2026/exit_policy_v1_0_1_trade_ledger.parquet",
    )
    ap.add_argument(
        "--bars",
        default="/mnt/gdrive/US_ETF/model_lab_v1/results/exit_policy_v1_0_pre2026/exit_policy_v1_0_1_bar_returns.parquet",
    )
    ap.add_argument(
        "--outdir",
        default="/mnt/gdrive/US_ETF/model_lab_v1/results/weekend_carry_policy_v1",
    )
    ap.add_argument("--baseline-policy", default="FIXED_4")
    args = ap.parse_args()

    ledger = pd.read_parquet(args.ledger)
    bars = pd.read_parquet(args.bars)
    baseline = str(args.baseline_policy).upper()

    ledger = ledger.loc[ledger["policy"].astype(str).str.upper() == baseline].copy()
    bars = bars.loc[bars["policy"].astype(str).str.upper() == baseline].copy()
    if ledger.empty or bars.empty:
        raise RuntimeError("FIXED_4 baseline rows are missing")

    ledger["entry_timestamp"] = pd.to_datetime(ledger["entry_timestamp"], utc=True)
    ledger["exit_timestamp"] = pd.to_datetime(ledger["exit_timestamp"], utc=True)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)

    spec, paths, diagnostics = _reconstruct_paths(ledger, bars)

    rows = []
    for pos, (_, trade) in enumerate(ledger.iterrows()):
        full = paths[pos]
        if full is None:
            continue
        full_ts = pd.to_datetime(full["timestamp"], utc=True).dt.tz_convert(NY) if len(full) else pd.Series([], dtype="datetime64[ns, America/New_York]")
        spans_overnight = bool(len(full_ts) and full_ts.dt.date.nunique() > 1)
        spans_weekend = False
        if len(full_ts) > 1:
            dates = list(full_ts.dt.date)
            for a, b in zip(dates, dates[1:]):
                if (b - a).days >= 3 or (pd.Timestamp(a).weekday() == 4 and b > a):
                    spans_weekend = True
                    break

        baseline_gross = float(trade["gross_return"])
        baseline_net = float(trade["net_return"])
        cost = baseline_gross - baseline_net
        for policy in POLICIES:
            selected = _trade_path_for_policy(full, trade["entry_timestamp"], policy)
            if len(selected) == len(full):
                selected_gross = baseline_gross
                selected_net = baseline_net
            else:
                selected_gross = _aggregate_return(selected["gross_bar_return"], spec.method)
                selected_net = selected_gross - cost
            rows.append(
                {
                    "trade_id": pos,
                    "policy": policy,
                    "fold": trade["fold"],
                    "symbol": trade["symbol"],
                    "entry_timestamp": trade["entry_timestamp"],
                    "fixed4_exit_timestamp": trade["exit_timestamp"],
                    "entry_seq": int(trade["entry_seq"]),
                    "exit_seq": int(trade["exit_seq"]),
                    "weight": float(trade["weight"]),
                    "entry_score": float(trade["entry_score"]),
                    "baseline_gross_return": baseline_gross,
                    "baseline_net_return": baseline_net,
                    "cost_proxy": cost,
                    "full_bar_count": int(len(full)),
                    "selected_bar_count": int(len(selected)),
                    "spans_overnight": spans_overnight,
                    "spans_weekend": spans_weekend,
                    "gross_return": selected_gross,
                    "net_return": selected_net,
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError("No policy replay rows created")

    metrics = {p: _metrics(out.loc[out["policy"] == p]) for p in POLICIES}
    wide = out.pivot(index="trade_id", columns="policy", values="net_return")
    paired = {}
    for a in POLICIES:
        paired[a] = {}
        for b in POLICIES:
            if a == b:
                continue
            common = wide[[a, b]].dropna()
            paired[a][f"vs_{b}"] = _paired_bootstrap((common[a] - common[b]).to_numpy())

    weekend = out.loc[out["spans_weekend"]].copy()
    weekend_summary = {}
    if not weekend.empty:
        wwide = weekend.pivot(index="trade_id", columns="policy", values="net_return")
        for a in POLICIES:
            weekend_summary[a] = {
                "trades": int(wwide[a].notna().sum()),
                "mean_return": float(wwide[a].mean()),
                "sum_return": float(wwide[a].sum()),
            }
        if "CARRY_ALL" in wwide and "WEEKDAY_CARRY_FRIDAY_FLAT" in wwide:
            d = (wwide["WEEKDAY_CARRY_FRIDAY_FLAT"] - wwide["CARRY_ALL"]).dropna()
            weekend_summary["FRIDAY_FLAT_MINUS_CARRY_ALL"] = {
                **_paired_bootstrap(d.to_numpy()),
                "positive_trade_share": float((d > 0).mean()) if len(d) else None,
                "worst_delta": float(d.min()) if len(d) else None,
                "best_delta": float(d.max()) if len(d) else None,
            }

    baseline_recon = out.loc[out["policy"] == "CARRY_ALL"].copy()
    recon_err = baseline_recon["gross_return"].to_numpy() - baseline_recon["baseline_gross_return"].to_numpy()

    result = {
        "schema": "kalman-weekend-carry-policy-v1",
        "scope": "PRE_2026_FIXED4_ENTRY_SET",
        "baseline_policy": baseline,
        "trade_count": int(len(ledger)),
        "reconstruction": {
            "selected_spec": spec.name,
            "method": spec.method,
            "coverage": float(len(baseline_recon) / len(ledger)),
            "median_abs_gross_recon_error": float(np.median(np.abs(recon_err))),
            "mean_abs_gross_recon_error": float(np.mean(np.abs(recon_err))),
            "candidates": diagnostics,
        },
        "policy_definitions": {
            "DAILY_FLAT": "Never borrow a next-session canonical return; truncate at the last same-NY-date bar.",
            "WEEKDAY_CARRY_FRIDAY_FLAT": "Allow ordinary weekday overnight carry, but truncate before a Friday-to-next-session or >=3-day non-trading gap.",
            "CARRY_ALL": "Original FIXED_4 path; overnight and weekend gaps remain in the four canonical bars.",
        },
        "metrics": metrics,
        "paired_bootstrap": paired,
        "weekend_only": weekend_summary,
        "limitations": [
            "Entry set, symbol choice, and position weights are held fixed to the pre-2026 FIXED_4 ledger.",
            "This isolates carry/exit timing; it does not retrain R5.1 or synthesize new add-on entries.",
            "Per-trade baseline gross-minus-net cost is reused unchanged across policies.",
            "DAILY_FLAT uses canonical hourly bars, so an intra-hour 15-minute safe-deadline fill is approximated structurally.",
        ],
    }

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_parquet(outdir / "weekend_carry_policy_trade_audit.parquet", index=False)
    pd.DataFrame(
        [{"policy": p, **metrics[p]} for p in POLICIES]
    ).to_csv(outdir / "weekend_carry_policy_summary.csv", index=False)
    (outdir / "weekend_carry_policy_decision.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    print("============================================================")
    print("KALMAN WEEKEND CARRY POLICY BACKTEST")
    print("============================================================")
    print("trade_count =", len(ledger))
    print("reconstruction_spec =", spec.name)
    print("reconstruction_coverage =", result["reconstruction"]["coverage"])
    print("median_abs_recon_error =", result["reconstruction"]["median_abs_gross_recon_error"])
    print()
    print(pd.DataFrame([{"policy": p, **metrics[p]} for p in POLICIES]).to_string(index=False))
    print()
    print("WEEKEND_ONLY")
    print(json.dumps(weekend_summary, indent=2, ensure_ascii=False))
    print()
    print("PAIRED")
    print(json.dumps(paired, indent=2, ensure_ascii=False))
    print()
    print("outdir =", outdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
