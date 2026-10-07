from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

SCHEMA = "kalman-r5-2-20h-purged-walk-forward-v1"
NY = ZoneInfo("America/New_York")
HORIZON = 20
ENTRY_LAG = 1
MIN_UNIVERSE = 80
EMPIRICAL_COST_BPS = 36.59673953005761
COST_STRESS_BPS = (36.59673953005761, 45.0, 50.0, 60.0)

FEATURES = [
    "cs_ret_1b", "cs_ret_2b", "cs_ret_4b", "cs_ret_6b",
    "cs_rv_6", "cs_rv_24", "cs_ma_dist_6", "cs_ma_dist_24",
    "cs_volume_z_24", "cs_bar_range", "cs_beta24", "cs_residual_ret_6b",
    "qqq_ret_2b", "qqq_ret_6b", "qqq_rv_24", "qqq_ma_dist_24",
    "ix_trend_qqq", "ix_vol_qqq", "ix_ret1_qqq", "ix_mom6_qqq",
]

MODEL_PARAMS = {
    "learning_rate": 0.05,
    "max_iter": 160,
    "max_leaf_nodes": 31,
    "min_samples_leaf": 100,
    "l2_regularization": 1.0,
    "early_stopping": False,
    "random_state": 42,
}

TARGETS = {
    "R52_REL20_HGB": "target_relative_20h",
    "R52_RAW20_HGB": "target_exec_20h",
    "R52_ORD20_HGB": "target_ordinal_20h",
}

BASE_SCORE = "R5C0_HGB_REFERENCE"
ALIASES = {"BNY": {"BNY", "BK"}}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_symbol(x: str) -> str:
    return str(x).strip().upper().replace("-", ".")


def panel_path(root: Path, symbol: str) -> Path:
    return root / f"{str(symbol).upper().replace('.', '-')}_1h_gap_aware.parquet"


def load_price_frame(path: Path) -> pd.DataFrame:
    z = pd.read_parquet(path, columns=["expected_seq", "open", "close"])
    z["expected_seq"] = pd.to_numeric(z["expected_seq"], errors="coerce").astype("Int64")
    z["open"] = pd.to_numeric(z["open"], errors="coerce")
    z["close"] = pd.to_numeric(z["close"], errors="coerce")
    return (
        z.dropna(subset=["expected_seq", "open", "close"])
        .drop_duplicates("expected_seq", keep="last")
        .set_index("expected_seq")
        .sort_index()
    )


def attach_execution_target(scored: pd.DataFrame, panel_root: Path) -> tuple[pd.DataFrame, dict]:
    d = scored.copy()
    d["entry_expected_seq"] = d["expected_seq"] + ENTRY_LAG
    d["exit_expected_seq_20h"] = d["expected_seq"] + HORIZON
    d["entry_open_20h"] = np.nan
    d["exit_close_20h"] = np.nan
    audit = {}

    for symbol, idx in d.groupby("symbol").groups.items():
        path = panel_path(panel_root, symbol)
        if not path.is_file():
            audit[str(symbol)] = {"status": "MISSING", "path": str(path)}
            continue
        q = load_price_frame(path)
        entry_seq = d.loc[idx, "entry_expected_seq"].astype(int).to_numpy()
        exit_seq = d.loc[idx, "exit_expected_seq_20h"].astype(int).to_numpy()
        d.loc[idx, "entry_open_20h"] = q["open"].reindex(entry_seq).to_numpy(float)
        d.loc[idx, "exit_close_20h"] = q["close"].reindex(exit_seq).to_numpy(float)
        audit[str(symbol)] = {
            "status": "READY",
            "panel_rows": int(len(q)),
            "target_rows": int(len(idx)),
        }

    entry = pd.to_numeric(d["entry_open_20h"], errors="coerce")
    exit_ = pd.to_numeric(d["exit_close_20h"], errors="coerce")
    d["target_exec_20h"] = exit_ / entry - 1.0
    d.loc[(entry <= 0) | ~np.isfinite(d["target_exec_20h"]), "target_exec_20h"] = np.nan
    med = d.groupby("timestamp")["target_exec_20h"].transform("median")
    d["target_relative_20h"] = d["target_exec_20h"] - med
    d["target_ordinal_20h"] = (
        d.groupby("timestamp")["target_exec_20h"].rank(pct=True, method="average") - 0.5
    )
    return d, audit


def load_membership(path: Path) -> tuple[list, dict]:
    z = pd.read_csv(path)
    z["date"] = pd.to_datetime(z["date"], errors="coerce").dt.date
    z = z.dropna(subset=["date"]).sort_values("date")
    dates = []
    members = {}
    for row in z.itertuples(index=False):
        ss = {norm_symbol(x) for x in str(row.tickers).split(",") if str(x).strip()}
        dates.append(row.date)
        members[row.date] = ss
    return dates, members


def is_member(symbol: str, day, dates: list, members: dict) -> bool:
    i = bisect.bisect_right(dates, day) - 1
    if i < 0:
        return False
    ss = members[dates[i]]
    sym = norm_symbol(symbol)
    return bool(ALIASES.get(sym, {sym}).intersection(ss))


def spearman_fast(a: pd.Series, b: pd.Series) -> float | None:
    z = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(z) < 3:
        return None
    ra = z["a"].rank(method="average").to_numpy(float)
    rb = z["b"].rank(method="average").to_numpy(float)
    if np.std(ra) == 0 or np.std(rb) == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def fit_walk_forward(d: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    fold_order = (
        d.groupby("fold")["timestamp"].min().sort_values().index.astype(str).tolist()
    )
    # E1 has no pre-2023 frozen feature history; E2-E8 are true expanding OOS folds.
    test_folds = fold_order[1:]
    parts = []
    fold_audit = []

    for fold in test_folds:
        te = d[d["fold"].astype(str).eq(fold)].copy()
        if te.empty:
            continue
        test_min_seq = int(te["expected_seq"].min())
        # Strict label-time purge: the 20H label must finish before the first test feature bar.
        tr = d[d["exit_expected_seq_20h"] < test_min_seq].copy()
        if tr.empty:
            raise RuntimeError(f"no safe training rows for {fold}")

        medians = tr[FEATURES].median()
        if medians.isna().any():
            bad = medians[medians.isna()].index.tolist()
            raise RuntimeError(f"training medians NaN in {fold}: {bad}")

        fold_rec = {
            "fold": fold,
            "test_start": te["timestamp"].min().isoformat(),
            "test_end": te["timestamp"].max().isoformat(),
            "test_min_seq": test_min_seq,
            "train_rows_total": int(len(tr)),
            "train_max_feature_seq": int(tr["expected_seq"].max()),
            "train_max_label_exit_seq": int(tr["exit_expected_seq_20h"].max()),
            "purge_gap_seq": int(test_min_seq - int(tr["expected_seq"].max()) - 1),
            "models": {},
        }
        if fold_rec["train_max_label_exit_seq"] >= test_min_seq:
            raise RuntimeError(f"label leakage in {fold}")

        xte = te[FEATURES].fillna(medians)
        for candidate, target in TARGETS.items():
            train = tr[tr[target].notna()].copy()
            if len(train) < 50_000:
                raise RuntimeError(f"insufficient train rows {fold}/{candidate}: {len(train)}")
            model = HistGradientBoostingRegressor(**MODEL_PARAMS)
            t0 = time.perf_counter()
            model.fit(train[FEATURES].fillna(medians), train[target].astype(float))
            fit_s = time.perf_counter() - t0
            te[candidate] = model.predict(xte)
            fold_rec["models"][candidate] = {
                "target": target,
                "train_rows": int(len(train)),
                "fit_seconds": round(fit_s, 3),
                "score_target_spearman": spearman_fast(te[candidate], te[target]),
            }
        parts.append(te)
        fold_audit.append(fold_rec)
        print(json.dumps({"fold_complete": fold, **fold_rec["models"]}, default=str), flush=True)

    if not parts:
        raise RuntimeError("no OOS predictions produced")
    return pd.concat(parts, ignore_index=True), fold_audit


def decisions_for_score(pred: pd.DataFrame, score_col: str, universe: str, membership) -> pd.DataFrame:
    z = pred.copy()
    if universe == "PIT_CONSERVATIVE":
        dates, members = membership
        local_days = z["timestamp"].dt.tz_convert(NY).dt.date
        keep = [
            is_member(sym, day, dates, members)
            for sym, day in zip(z["symbol"].astype(str), local_days)
        ]
        z = z.loc[keep].copy()

    rows = []
    for ts, g in z.groupby("timestamp", sort=True):
        g = g.dropna(subset=[score_col, "target_exec_20h"]).copy()
        if len(g) < MIN_UNIVERSE:
            continue
        g = g.sort_values([score_col, "symbol"], ascending=[False, True])
        r = g.iloc[0]
        rows.append({
            "timestamp": ts,
            "expected_seq": int(r["expected_seq"]),
            "entry_expected_seq": int(r["entry_expected_seq"]),
            "exit_expected_seq": int(r["exit_expected_seq_20h"]),
            "fold": str(r["fold"]),
            "symbol": str(r["symbol"]),
            "score": float(r[score_col]),
            "raw_return": float(r["target_exec_20h"]),
            "entry_price": float(r["entry_open_20h"]),
            "exit_price": float(r["exit_close_20h"]),
            "universe": universe,
            "candidate": score_col,
            "eligible_symbols": int(len(g)),
        })
    return pd.DataFrame(rows)


def non_overlap(decisions: pd.DataFrame, score_floor: float | None = None) -> pd.DataFrame:
    if decisions.empty:
        return decisions.copy()
    z = decisions.sort_values(["expected_seq", "timestamp"]).copy()
    if score_floor is not None:
        z = z[z["score"] >= float(score_floor)].copy()
    rows = []
    blocked_until = -10**18
    for r in z.itertuples(index=False):
        if int(r.entry_expected_seq) <= blocked_until:
            continue
        rows.append(r._asdict())
        blocked_until = int(r.exit_expected_seq)
    return pd.DataFrame(rows)


def metrics(trades: pd.DataFrame, cost_bps: float) -> dict:
    if trades.empty:
        return {"trades": 0, "total_return": None, "cagr": None, "max_drawdown": None}
    r = trades["raw_return"].astype(float) - float(cost_bps) / 10000.0
    wealth = (1.0 + r).cumprod()
    dd = wealth / wealth.cummax() - 1.0
    start = pd.Timestamp(trades.iloc[0]["timestamp"])
    # approximate exit time from 1h bars: use signal span for annualization; robust enough for multi-year OOS.
    end = pd.Timestamp(trades.iloc[-1]["timestamp"])
    years = max((end - start).total_seconds() / (365.25 * 86400), 1 / 365.25)
    total = float(wealth.iloc[-1] - 1.0)
    cagr = float((1.0 + total) ** (1.0 / years) - 1.0) if total > -1 else -1.0
    sd = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    return {
        "trades": int(len(trades)),
        "total_return": total,
        "cagr": cagr,
        "max_drawdown": float(dd.min()),
        "mean_net_return": float(r.mean()),
        "median_net_return": float(r.median()),
        "win_rate": float((r > 0).mean()),
        "trade_sharpe_ann": float(r.mean() / sd * math.sqrt(252.0)) if sd > 0 else None,
    }


def yearly_metrics(trades: pd.DataFrame, cost_bps: float) -> list[dict]:
    if trades.empty:
        return []
    z = trades.copy()
    z["year"] = z["timestamp"].dt.year
    out = []
    for year, g in z.groupby("year"):
        r = g["raw_return"].astype(float) - cost_bps / 10000.0
        wealth = (1 + r).cumprod()
        dd = wealth / wealth.cummax() - 1
        out.append({
            "year": int(year),
            "trades": int(len(g)),
            "total_return": float(wealth.iloc[-1] - 1),
            "mean_net_return": float(r.mean()),
            "median_net_return": float(r.median()),
            "win_rate": float((r > 0).mean()),
            "max_drawdown": float(dd.min()),
        })
    return out


def evaluate(pred: pd.DataFrame, membership) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    score_cols = [BASE_SCORE, *TARGETS.keys()]
    trade_parts = []
    summary_rows = []
    annual_rows = []

    for universe in ("STATIC_93", "PIT_CONSERVATIVE"):
        for score_col in score_cols:
            dec = decisions_for_score(pred, score_col, universe, membership)
            variants = [("NO_SCORE_FLOOR", None)]
            if score_col == BASE_SCORE:
                variants.append(("R5_SCORE_GE_20BP", 0.002))
            if score_col == "R52_RAW20_HGB":
                variants.append(("PREDICTED_RAW_GE_EMPIRICAL_COST", EMPIRICAL_COST_BPS / 10000.0))

            for variant, floor in variants:
                tr = non_overlap(dec, floor)
                if not tr.empty:
                    tr["variant"] = variant
                    trade_parts.append(tr)
                for cost in COST_STRESS_BPS:
                    m = metrics(tr, cost)
                    summary_rows.append({
                        "universe": universe,
                        "candidate": score_col,
                        "variant": variant,
                        "cost_bps": float(cost),
                        **m,
                    })
                    for yr in yearly_metrics(tr, cost):
                        annual_rows.append({
                            "universe": universe,
                            "candidate": score_col,
                            "variant": variant,
                            "cost_bps": float(cost),
                            **yr,
                        })

    trades = pd.concat(trade_parts, ignore_index=True) if trade_parts else pd.DataFrame()
    summary = pd.DataFrame(summary_rows)
    annual = pd.DataFrame(annual_rows)

    primary = summary[
        (summary["universe"] == "PIT_CONSERVATIVE")
        & (summary["variant"] == "NO_SCORE_FLOOR")
        & np.isclose(summary["cost_bps"], EMPIRICAL_COST_BPS)
        & summary["candidate"].isin(TARGETS.keys())
    ].sort_values(["cagr", "max_drawdown"], ascending=[False, False])

    selected = primary.iloc[0].to_dict() if not primary.empty else None
    gate = {
        "selected_research_candidate": selected,
        "research_only": True,
        "live_promotion": False,
        "promotion_block_reasons": [
            "FULL_POINT_IN_TIME_UNIVERSE_NOT_AVAILABLE",
            "NO_PROSPECTIVE_SHADOW_FOR_NEW_20H_MODEL",
            "ORIGINAL_R5_HGB_TEMPLATE_NOT_AVAILABLE_FOR_EXACT_ARCHITECTURE_CLONE",
        ],
    }
    return trades, summary, {"annual": annual, "gate": gate}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--scored", type=Path, required=True)
    p.add_argument("--panel-root", type=Path, required=True)
    p.add_argument("--membership", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    return p.parse_args()


def main() -> int:
    a = parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=True)

    cols = list(dict.fromkeys([
        "expected_seq", "timestamp", "symbol", "fold", BASE_SCORE,
        "relative_ret_4b", *FEATURES,
    ]))
    scored = pd.read_parquet(a.scored, columns=cols)
    scored["timestamp"] = pd.to_datetime(scored["timestamp"], utc=True, errors="coerce")
    scored["expected_seq"] = pd.to_numeric(scored["expected_seq"], errors="coerce").astype("Int64")
    scored = scored.dropna(subset=["timestamp", "expected_seq", "symbol", "fold"]).copy()
    scored["expected_seq"] = scored["expected_seq"].astype(int)

    target_cache = a.output_dir / "r5_2_20h_training_rows.parquet"
    target_audit_path = a.output_dir / "target_audit.json"
    if target_cache.exists() and target_audit_path.exists():
        d = pd.read_parquet(target_cache)
        d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
        target_audit = json.loads(target_audit_path.read_text())
        print("[R5.2] reused cached 20H targets", flush=True)
    else:
        d, target_audit = attach_execution_target(scored, a.panel_root)
        d.to_parquet(target_cache, index=False)
        target_audit_path.write_text(json.dumps(target_audit, indent=2, ensure_ascii=False) + "\n")
        print("[R5.2] built execution-aligned 20H targets", flush=True)

    target_coverage = float(d["target_exec_20h"].notna().mean())
    panel_ready_symbols = [sym for sym, rec in target_audit.items() if rec.get("status") == "READY"]
    ready = d[d["symbol"].astype(str).isin(panel_ready_symbols)].copy()
    ready_target_coverage = float(ready["target_exec_20h"].notna().mean())
    ts_counts = ready.groupby("timestamp")["target_exec_20h"].count()
    timestamp_min_universe_coverage = float((ts_counts >= MIN_UNIVERSE).mean())
    if ready_target_coverage < 0.975:
        raise RuntimeError(
            f"20H target coverage among panel-ready symbols too low: {ready_target_coverage:.4f}"
        )
    if timestamp_min_universe_coverage < 0.985:
        raise RuntimeError(
            "20H timestamp universe coverage too low: "
            f"{timestamp_min_universe_coverage:.4f}"
        )

    pred, fold_audit = fit_walk_forward(d)
    pred_path = a.output_dir / "r5_2_20h_oos_predictions.parquet"
    pred.to_parquet(pred_path, index=False)

    membership = load_membership(a.membership)
    trades, summary, eval_obj = evaluate(pred, membership)
    annual = eval_obj["annual"]
    gate = eval_obj["gate"]

    if not trades.empty:
        trades.to_parquet(a.output_dir / "r5_2_20h_trade_ledger.parquet", index=False)
    summary.to_csv(a.output_dir / "r5_2_20h_summary.csv", index=False)
    annual.to_csv(a.output_dir / "r5_2_20h_yearly.csv", index=False)
    (a.output_dir / "fold_audit.json").write_text(
        json.dumps(fold_audit, indent=2, ensure_ascii=False, default=str) + "\n"
    )

    status = {
        "schema_version": SCHEMA,
        "status": "COMPLETE",
        "research_only": True,
        "live_execution": False,
        "horizon_bars": HORIZON,
        "entry_lag_bars": ENTRY_LAG,
        "empirical_cost_bps": EMPIRICAL_COST_BPS,
        "cost_stress_bps": COST_STRESS_BPS,
        "features": FEATURES,
        "model_params": MODEL_PARAMS,
        "targets": TARGETS,
        "source_scored": str(a.scored),
        "source_scored_sha256": sha256_file(a.scored),
        "membership_sha256": sha256_file(a.membership),
        "input_rows": int(len(scored)),
        "target_coverage_all_rows": target_coverage,
        "panel_ready_symbols": int(len(panel_ready_symbols)),
        "panel_missing_symbols": sorted(set(scored["symbol"].astype(str).unique()) - set(panel_ready_symbols)),
        "target_coverage_panel_ready": ready_target_coverage,
        "timestamp_min_universe_coverage": timestamp_min_universe_coverage,
        "oos_rows": int(len(pred)),
        "oos_folds": [x["fold"] for x in fold_audit],
        **gate,
        "top_empirical_pit": (
            summary[
                (summary["universe"] == "PIT_CONSERVATIVE")
                & np.isclose(summary["cost_bps"], EMPIRICAL_COST_BPS)
            ]
            .sort_values("cagr", ascending=False)
            .head(10)
            .replace({np.nan: None})
            .to_dict(orient="records")
        ),
    }
    (a.output_dir / "status.json").write_text(
        json.dumps(status, indent=2, ensure_ascii=False, default=str) + "\n"
    )
    print(json.dumps(status, indent=2, ensure_ascii=False, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
