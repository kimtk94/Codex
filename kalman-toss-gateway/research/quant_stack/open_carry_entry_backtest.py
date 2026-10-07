from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NY = ZoneInfo("America/New_York")
SCORE_COL = "R5C0_HGB_REFERENCE"
DEFAULT_THRESHOLD = 0.00041106678948450823


@dataclass
class PricePack:
    open_0930: float | None
    p0935: float | None
    p0940: float | None
    p0945: float | None
    p1035: float | None
    p1435: float | None


class MinuteCache:
    def __init__(self, root: Path):
        self.root = root
        self._symbol_cache: dict[str, pd.DataFrame] = {}

    def _load_symbol(self, symbol: str) -> pd.DataFrame:
        symbol = symbol.upper().replace(".", "-")
        if symbol in self._symbol_cache:
            return self._symbol_cache[symbol]
        folder = self.root / symbol
        frames = []
        if folder.is_dir():
            for path in sorted(folder.glob("*.parquet")):
                try:
                    d = pd.read_parquet(path, columns=["timestamp", "open", "close"])
                except Exception:
                    continue
                d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True, errors="coerce")
                d["open"] = pd.to_numeric(d["open"], errors="coerce")
                d["close"] = pd.to_numeric(d["close"], errors="coerce")
                d = d.dropna(subset=["timestamp", "open", "close"])
                if not d.empty:
                    frames.append(d)
        if frames:
            z = pd.concat(frames, ignore_index=True)
            z = z.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
        else:
            z = pd.DataFrame(columns=["timestamp", "open", "close"])
        self._symbol_cache[symbol] = z
        return z

    @staticmethod
    def _price_at(frame: pd.DataFrame, target_et: pd.Timestamp, tolerance_min: int = 2) -> float | None:
        if frame.empty:
            return None
        t0 = target_et.tz_convert("UTC")
        t1 = t0 + pd.Timedelta(minutes=tolerance_min)
        z = frame.loc[(frame["timestamp"] >= t0) & (frame["timestamp"] <= t1)]
        if z.empty:
            return None
        x = float(z.iloc[0]["open"])
        return x if math.isfinite(x) and x > 0 else None

    def prices_for_day(self, symbol: str, day) -> PricePack:
        f = self._load_symbol(symbol)
        def t(h, m):
            return pd.Timestamp(datetime.combine(day, dt_time(h, m), tzinfo=NY))
        return PricePack(
            self._price_at(f, t(9, 30)),
            self._price_at(f, t(9, 35)),
            self._price_at(f, t(9, 40)),
            self._price_at(f, t(9, 45)),
            self._price_at(f, t(10, 35)),
            self._price_at(f, t(14, 35)),
        )


def build_candidates(scored: pd.DataFrame, threshold: float) -> pd.DataFrame:
    d = scored[["expected_seq", "timestamp", "session_bucket", "symbol", SCORE_COL, "fold"]].copy()
    d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True, errors="coerce")
    d[SCORE_COL] = pd.to_numeric(d[SCORE_COL], errors="coerce")
    d["symbol"] = d["symbol"].astype(str).str.upper().str.replace(".", "-", regex=False)
    d = d.dropna(subset=["expected_seq", "timestamp", "session_bucket", SCORE_COL])

    # Live R5.1 model cycles consume completed buckets 0..5; the final live
    # signal before the next open is the 14:30 ET bucket (session_bucket=5).
    last = d.loc[d["session_bucket"].eq(5)].copy()
    last = last.sort_values(["expected_seq", SCORE_COL, "symbol"], ascending=[True, False, True])
    top1 = last.groupby("expected_seq", as_index=False).first()
    top1["signal_et"] = top1["timestamp"].dt.tz_convert(NY)
    top1["signal_day"] = top1["signal_et"].dt.date

    # Map to next observed US session's bucket-0 date.
    bars = d[["expected_seq", "timestamp", "session_bucket"]].drop_duplicates("expected_seq")
    opens = bars.loc[bars["session_bucket"].eq(0), ["expected_seq", "timestamp"]].sort_values("expected_seq")
    open_rows = list(opens.itertuples(index=False))
    seqs = np.asarray([r.expected_seq for r in open_rows], dtype=np.int64)
    ts = [r.timestamp for r in open_rows]

    next_ts = []
    for seq in top1["expected_seq"].astype(int):
        i = int(np.searchsorted(seqs, seq, side="right"))
        next_ts.append(ts[i] if i < len(ts) else pd.NaT)
    top1["open_session_ts"] = pd.to_datetime(next_ts, utc=True)
    top1["open_day"] = top1["open_session_ts"].dt.tz_convert(NY).dt.date
    top1["score"] = top1[SCORE_COL].astype(float)
    top1["score_pass"] = top1["score"] > float(threshold)
    return top1.dropna(subset=["open_session_ts"]).reset_index(drop=True)


def equity_metrics(returns: pd.Series) -> dict:
    r = pd.to_numeric(returns, errors="coerce").dropna().astype(float)
    if r.empty:
        return {"n": 0}
    equity = (1.0 + r).cumprod()
    peak = equity.cummax()
    dd = equity / peak - 1.0
    total = float(equity.iloc[-1] - 1.0)
    mdd = float(dd.min())
    return {
        "n": int(len(r)),
        "total_return": total,
        "log_growth": float(np.log1p(r).sum()),
        "mean": float(r.mean()),
        "median": float(r.median()),
        "win_rate": float((r > 0).mean()),
        "mdd": mdd,
        "return_over_abs_mdd": (total / abs(mdd)) if mdd < 0 else None,
    }


def bootstrap_mean_ci(values: pd.Series, n: int = 10000, seed: int = 20261008) -> dict:
    x = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if len(x) == 0:
        return {"n": 0}
    rng = np.random.default_rng(seed)
    means = np.empty(n, dtype=float)
    # Chunk to avoid large n x rows allocation.
    for i in range(n):
        means[i] = rng.choice(x, size=len(x), replace=True).mean()
    return {
        "n": int(len(x)),
        "bootstrap_n": int(n),
        "mean": float(x.mean()),
        "ci95_low": float(np.quantile(means, 0.025)),
        "ci95_high": float(np.quantile(means, 0.975)),
        "p_mean_le_zero": float((means <= 0).mean()),
    }


def run(args) -> tuple[pd.DataFrame, dict]:
    scored = pd.read_parquet(args.scored_rows)
    candidates = build_candidates(scored, args.confidence_threshold)
    eligible = candidates.loc[candidates["score_pass"]].copy()

    cache = MinuteCache(args.minute_cache)
    rows = []
    for r in eligible.itertuples(index=False):
        pp = cache.prices_for_day(r.symbol, r.open_day)
        complete_core = all(x is not None for x in (pp.open_0930, pp.p0935, pp.p1435))
        if not complete_core:
            rows.append({
                "fold": r.fold,
                "prior_signal_ts": r.timestamp,
                "open_day": r.open_day,
                "symbol": r.symbol,
                "score": r.score,
                "data_ready": False,
                "missing": ",".join(
                    name for name, value in [
                        ("0930", pp.open_0930), ("0935", pp.p0935), ("1435", pp.p1435)
                    ] if value is None
                ),
            })
            continue

        momentum_5m = pp.p0935 / pp.open_0930 - 1.0
        leg1 = momentum_5m > 0
        leg2 = False
        leg2_time = None
        leg2_price = None
        leg2_cont = None
        if leg1:
            if pp.p0940 is not None:
                leg2_cont = pp.p0940 / pp.p0935 - 1.0
                if leg2_cont >= 0:
                    leg2 = True
                    leg2_time = "09:40"
                    leg2_price = pp.p0940
            elif pp.p0945 is not None:
                leg2_cont = pp.p0945 / pp.p0935 - 1.0
                if leg2_cont >= 0:
                    leg2 = True
                    leg2_time = "09:45_FALLBACK"
                    leg2_price = pp.p0945

        # Budget accounting: OPEN_CARRY has a fixed KRW 10K envelope.
        # Each 5K leg is 50% budget weight; unused half remains cash.
        gross_budget = 0.0
        deployed_weight = 0.0
        if leg1:
            gross_budget += 0.5 * (pp.p1435 / pp.p0935 - 1.0)
            deployed_weight += 0.5
        if leg2:
            gross_budget += 0.5 * (pp.p1435 / leg2_price - 1.0)
            deployed_weight += 0.5
        cost_budget = deployed_weight * (args.cost_bps / 10000.0)
        net_budget = gross_budget - cost_budget if leg1 else 0.0

        delayed_ready = pp.p1035 is not None
        delayed_net = (
            (pp.p1435 / pp.p1035 - 1.0) - args.cost_bps / 10000.0
            if delayed_ready else np.nan
        )

        rows.append({
            "fold": r.fold,
            "prior_signal_ts": r.timestamp,
            "open_day": r.open_day,
            "symbol": r.symbol,
            "score": r.score,
            "data_ready": True,
            "open_0930": pp.open_0930,
            "entry_0935": pp.p0935,
            "entry_0940": pp.p0940,
            "entry_0945": pp.p0945,
            "delayed_1035": pp.p1035,
            "exit_1435": pp.p1435,
            "momentum_5m": momentum_5m,
            "leg1": leg1,
            "leg2": leg2,
            "leg2_time": leg2_time,
            "leg2_continuation": leg2_cont,
            "deployed_weight": deployed_weight,
            "gross_budget_return": gross_budget,
            "cost_budget_return": cost_budget,
            "open_carry_net_return": net_budget,
            "delayed_same_symbol_net_return": delayed_net,
            "incremental_vs_delayed": net_budget - delayed_net if delayed_ready else np.nan,
        })

    out = pd.DataFrame(rows)
    ready = out.loc[out["data_ready"].eq(True)].copy()
    triggered = ready.loc[ready["leg1"].eq(True)].copy()
    paired = triggered.dropna(subset=["delayed_same_symbol_net_return", "incremental_vs_delayed"])

    fold = (
        triggered.groupby("fold", dropna=False)["open_carry_net_return"]
        .agg(["count", "mean", "median"])
        .reset_index()
    ) if not triggered.empty else pd.DataFrame(columns=["fold", "count", "mean", "median"])

    coverage = len(ready) / len(eligible) if len(eligible) else 0.0
    trigger_rate = len(triggered) / len(ready) if len(ready) else 0.0
    leg2_rate = triggered["leg2"].mean() if len(triggered) else 0.0

    open_metrics = equity_metrics(triggered["open_carry_net_return"])
    delayed_metrics = equity_metrics(paired["delayed_same_symbol_net_return"])
    incr_boot = bootstrap_mean_ci(paired["incremental_vs_delayed"]) if len(paired) else {"n": 0}
    open_boot = bootstrap_mean_ci(triggered["open_carry_net_return"]) if len(triggered) else {"n": 0}

    positive_folds = int((fold["mean"] > 0).sum()) if not fold.empty else 0
    fold_count = int(len(fold))
    gates = {
        "coverage_ge_80pct": coverage >= 0.80,
        "open_mean_positive": open_metrics.get("mean", -1) > 0,
        "open_bootstrap_ci_low_positive": open_boot.get("ci95_low", -1) > 0,
        "positive_folds_ge_5_of_6": positive_folds >= 5 and fold_count >= 6,
        "incremental_vs_delayed_mean_positive": (
            incr_boot.get("mean", -1) > 0 if incr_boot.get("n", 0) else False
        ),
    }
    gates["promotion_pass"] = all(gates.values())

    summary = {
        "schema": "kalman-open-carry-entry-backtest-v1",
        "definition": {
            "prior_signal": "R5.1 HGB Top1 at session_bucket=5 (14:30 ET)",
            "confidence_threshold_strict_gt": args.confidence_threshold,
            "leg1": "09:35 ET if 09:35/open09:30 - 1 > 0",
            "leg2": "09:40 ET if price>=09:35; 09:45 only as missing-09:40 fallback",
            "budget_krw": 10000,
            "leg_krw": 5000,
            "exit": "14:35 ET proxy for fourth post-open canonical model bucket",
            "cost_bps_roundtrip_per_deployed_leg": args.cost_bps,
            "delayed_comparator": "same prior Top1, KRW 10K-equivalent at 10:35 ET to 14:35 ET",
        },
        "candidate_counts": {
            "prior_final_top1_sessions": int(len(candidates)),
            "confidence_pass": int(len(eligible)),
            "minute_data_ready": int(len(ready)),
            "leg1_triggered": int(len(triggered)),
            "leg2_triggered": int(triggered["leg2"].sum()) if len(triggered) else 0,
            "paired_delayed_ready": int(len(paired)),
        },
        "coverage": coverage,
        "leg1_trigger_rate_ready": trigger_rate,
        "leg2_rate_given_leg1": float(leg2_rate),
        "open_carry": open_metrics,
        "open_carry_bootstrap": open_boot,
        "delayed_same_symbol": delayed_metrics,
        "incremental_vs_delayed_bootstrap": incr_boot,
        "folds": fold.to_dict(orient="records"),
        "gates": gates,
        "recommendation": "PROMOTE_CANDIDATE" if gates["promotion_pass"] else "DO_NOT_PROMOTE",
    }
    return out, summary


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--scored-rows",
        type=Path,
        default=Path.home() / ".cache/kalman-open-carry/model/r5_0_1_scored_rows.parquet",
    )
    ap.add_argument(
        "--minute-cache",
        type=Path,
        default=Path.home() / ".cache/kalman-open-carry/iex",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=Path.home() / ".cache/kalman-open-carry/results/open_carry_entry_v1",
    )
    ap.add_argument("--confidence-threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--cost-bps", type=float, default=10.0)
    return ap.parse_args()


def main():
    args = parse_args()
    detail, summary = run(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    detail.to_parquet(args.output_dir / "open_carry_entry_detail.parquet", index=False)
    (args.output_dir / "open_carry_entry_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
