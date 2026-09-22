from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone

SCHEMA = "kalman-r6-1-decision-target-v4"
COST = 0.001
STOP = -0.03
TAKE = 0.20
MIN_UNIVERSE = 80
BLOCK_DAYS = 5
B_DEFAULT = 2000
RNG_SEED = 20260922
PATH_COVERAGE_MIN = 0.95
EXPECTED_SCORED_ROWS = 497504

RESEARCH_CUTOFF = pd.Timestamp("2026-09-02T13:30:00Z")
FOLDS = [
    ("E1_2023H1", "2023-01-01", "2023-07-01"),
    ("E2_2023H2", "2023-07-01", "2024-01-01"),
    ("E3_2024H1", "2024-01-01", "2024-07-01"),
    ("E4_2024H2", "2024-07-01", "2025-01-01"),
    ("E5_2025H1", "2025-01-01", "2025-07-01"),
    ("E6_2025H2", "2025-07-01", "2026-01-01"),
    ("E7_2026_JAN_APR", "2026-01-05", "2026-05-01"),
    ("E8_2026_MAY_CUTOFF", "2026-05-01", "2026-09-02T13:30:00Z"),
]
EVAL_FOLDS = FOLDS[1:]
EVAL_FOLD_NAMES = {x[0] for x in EVAL_FOLDS}
EXPECTED_TRAIN_ROWS = {
    "E1_2023H1": 333560,
    "E2_2023H2": 402199,
    "E3_2024H1": 469975,
    "E4_2024H2": 536765,
    "E5_2025H1": 604724,
    "E6_2025H2": 670525,
    "E7_2026_JAN_APR": 739716,
    "E8_2026_MAY_CUTOFF": 784713,
}

FEATURES = [
    "cs_ret_1b", "cs_ret_2b", "cs_ret_4b", "cs_ret_6b",
    "cs_rv_6", "cs_rv_24", "cs_ma_dist_6", "cs_ma_dist_24",
    "cs_volume_z_24", "cs_bar_range", "cs_beta24", "cs_residual_ret_6b",
    "qqq_ret_2b", "qqq_ret_6b", "qqq_rv_24", "qqq_ma_dist_24",
    "ix_trend_qqq", "ix_vol_qqq", "ix_ret1_qqq", "ix_mom6_qqq",
]

CONTROL = "R6T0_RELATIVE_HGB"
CHALLENGERS = {
    "R6T1_NET_HGB": "target_net",
    "R6T2_ORDINAL_NET_HGB": "target_ordinal_net",
    "R6T3_PATH_REL_HGB": "target_path_relative",
}

SCORED_COLUMNS = list(dict.fromkeys([
    "expected_seq", "timestamp", "high", "low", "close",
    "fwd_ret_4b", "target_timestamp_4b", "symbol", "fold",
    "relative_ret_4b", "rv_24", "universe_median_rv24",
    "R5C0_HGB_REFERENCE",
    *FEATURES,
]))


def parse_args():
    p = argparse.ArgumentParser()
    root = Path(os.getenv("KALMAN_DATA_ROOT", "/content/drive/MyDrive"))
    p.add_argument("--root", default=str(root))
    p.add_argument("--bootstrap", type=int, default=B_DEFAULT)
    return p.parse_args()


def nts(x):
    return pd.to_datetime(x, utc=True, errors="coerce")


def ts(x):
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def checkpoint(path, stage, **kw):
    payload = {
        "schema": SCHEMA,
        "stage": stage,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        **kw,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")
    print(f"[R6.1] {stage} {kw}", flush=True)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def max_dd(r):
    r = np.asarray(r, float)
    if len(r) == 0:
        return np.nan
    eq = np.r_[1.0, np.cumprod(1.0 + r)]
    peak = np.maximum.accumulate(eq)
    return float(np.min(eq / peak - 1.0))


def profit_factor(r):
    r = np.asarray(r, float)
    pos = r[r > 0].sum()
    neg = -r[r < 0].sum()
    return float(pos / neg) if neg > 0 else np.inf


def metrics(t, ret_col):
    if t.empty:
        return {
            "trades": 0, "cum_return": np.nan, "log_growth": np.nan,
            "avg_return": np.nan, "median_return": np.nan, "win_rate": np.nan,
            "profit_factor": np.nan, "mdd": np.nan,
        }
    r = pd.to_numeric(t[ret_col], errors="coerce").dropna().to_numpy(float)
    if len(r) == 0:
        return {
            "trades": 0, "cum_return": np.nan, "log_growth": np.nan,
            "avg_return": np.nan, "median_return": np.nan, "win_rate": np.nan,
            "profit_factor": np.nan, "mdd": np.nan,
        }
    return {
        "trades": int(len(r)),
        "cum_return": float(np.prod(1 + r) - 1),
        "log_growth": float(np.log1p(r).sum()),
        "avg_return": float(r.mean()),
        "median_return": float(np.median(r)),
        "win_rate": float((r > 0).mean()),
        "profit_factor": profit_factor(r),
        "mdd": max_dd(r),
    }


def effective_names(symbols, weights):
    t = pd.DataFrame({"symbol": list(symbols), "w": list(weights)}).groupby("symbol")["w"].sum()
    x = t / t.sum()
    return float(1.0 / x.pow(2).sum()), float(x.max())



def _read_panel_symbol(canon_panel, live_panel, sym):
    p = canon_panel / f"{sym}_1h_gap_aware.parquet"
    if not p.exists():
        raise FileNotFoundError(p)

    cols = ["expected_seq", "timestamp", "high", "low", "close"]
    q = pd.read_parquet(p)
    keep = [x for x in cols if x in q.columns]
    q = q[keep].copy()
    q["expected_seq"] = pd.to_numeric(q["expected_seq"], errors="coerce")
    q = q.loc[q["expected_seq"].notna()].copy()
    q["expected_seq"] = q["expected_seq"].astype("int64")
    if "timestamp" in q.columns:
        q["timestamp"] = nts(q["timestamp"])

    lp = live_panel / f"{sym}_1h_live.parquet"
    if lp.exists():
        z = pd.read_parquet(lp)
        if len(z):
            keep2 = [x for x in cols if x in z.columns]
            z = z[keep2].copy()
            z["expected_seq"] = pd.to_numeric(z["expected_seq"], errors="coerce")
            z = z.loc[z["expected_seq"].notna()].copy()
            z["expected_seq"] = z["expected_seq"].astype("int64")
            if "timestamp" in z.columns:
                z["timestamp"] = nts(z["timestamp"])
                z = z.loc[z["timestamp"] < RESEARCH_CUTOFF]
            q = pd.concat([q, z], ignore_index=True, sort=False)

    return (
        q.sort_values("expected_seq")
        .drop_duplicates("expected_seq", keep="last")
        .reset_index(drop=True)
    )


def attach_path_proxy(df, canon_panel, live_panel):
    out = df.copy()
    out["proxy_ret_4b"] = np.nan
    out["path_complete"] = False
    parity_abs = []

    for sym, idxs in out.groupby("symbol", sort=False).groups.items():
        q = _read_panel_symbol(canon_panel, live_panel, str(sym))
        q = q.dropna(subset=["expected_seq", "high", "low", "close"])
        q = q.set_index("expected_seq")

        idx = np.asarray(list(idxs), dtype=int)
        seq = pd.to_numeric(out.loc[idx, "expected_seq"], errors="coerce").to_numpy()
        entry = q["close"].reindex(seq).to_numpy(float)
        exit4 = q["close"].reindex(seq + 4).to_numpy(float)

        frozen_fwd = pd.to_numeric(out.loc[idx, "fwd_ret_4b"], errors="coerce").to_numpy(float)
        canonical_fwd = exit4 / entry - 1.0
        ok = np.isfinite(frozen_fwd) & np.isfinite(canonical_fwd)
        if ok.any():
            parity_abs.extend(np.abs(frozen_fwd[ok] - canonical_fwd[ok]).tolist())

        highs = []
        lows = []
        complete = np.isfinite(entry) & np.isfinite(exit4)
        for k in [1, 2, 3, 4]:
            hi = q["high"].reindex(seq + k).to_numpy(float)
            lo = q["low"].reindex(seq + k).to_numpy(float)
            highs.append(hi)
            lows.append(lo)
            complete &= np.isfinite(hi) & np.isfinite(lo)

        proxy = frozen_fwd.copy()
        active = complete & np.isfinite(proxy)
        for k in [0, 1, 2, 3]:
            stop_touch = active & ((lows[k] / entry - 1.0) <= STOP)
            take_touch = active & ((highs[k] / entry - 1.0) >= TAKE)
            # Conservative same-bar ambiguity: stop wins.
            proxy[stop_touch] = STOP
            take_only = take_touch & ~stop_touch
            proxy[take_only] = TAKE
            active[stop_touch | take_only] = False

        proxy[~complete] = np.nan
        out.loc[idx, "proxy_ret_4b"] = proxy
        out.loc[idx, "path_complete"] = complete

    pa = np.asarray(parity_abs, float)
    audit = {
        "rows": int(len(out)),
        "path_coverage": float(out["path_complete"].mean()),
        "fwd_parity_n": int(len(pa)),
        "fwd_parity_median_abs_diff": float(np.median(pa)) if len(pa) else None,
        "fwd_parity_max_abs_diff": float(np.max(pa)) if len(pa) else None,
    }
    return out, audit


def _bool_series(s):
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False)
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "yes"])


def _target_timestamp_map(root):
    qpath = (
        root / "US_ETF/directional_research/canonical_history_v1/"
        "qqq_context/history_1h/QQQ_1h_gap_aware.parquet"
    )
    q = pd.read_parquet(qpath)
    q["expected_seq"] = pd.to_numeric(q["expected_seq"], errors="coerce")
    q = q.loc[q["expected_seq"].notna()].copy()
    q["expected_seq"] = q["expected_seq"].astype("int64")
    if "timestamp" in q.columns:
        q["timestamp"] = nts(q["timestamp"])
    else:
        q["market_open_utc"] = nts(q["market_open_utc"])
        q["timestamp"] = q["market_open_utc"] + pd.to_timedelta(
            pd.to_numeric(q["session_bucket"], errors="coerce"), unit="h"
        )
    return q.drop_duplicates("expected_seq", keep="last").set_index("expected_seq")["timestamp"]


def build_r1_training_rows(root, symbols, canon_panel, live_panel):
    r1 = root / "US_ETF/directional_research/r1_directional_v1_2/primary_train"
    if not r1.exists():
        raise FileNotFoundError(r1)

    required = [
        "expected_seq", "timestamp", "feature_core_valid",
        "ret_1b", "ret_2b", "ret_4b", "ret_6b",
        "bar_range", "rv_6", "rv_24", "ma_dist_6", "ma_dist_24",
        "volume_z_24", "qqq_ret_1b", "qqq_ret_2b", "qqq_ret_6b",
        "qqq_rv_24", "qqq_ma_dist_24", "fwd_ret_4b",
    ]

    parts = []
    for sym in symbols:
        p = r1 / f"{sym}_r1.parquet"
        if not p.exists():
            raise FileNotFoundError(p)
        z = pd.read_parquet(p)
        miss = [x for x in required if x not in z.columns]
        if miss:
            raise RuntimeError(f"{p.name} missing R1 columns: {miss}")
        z = z[required].copy()
        z["symbol"] = str(sym)
        z["timestamp"] = nts(z["timestamp"])
        z["expected_seq"] = pd.to_numeric(z["expected_seq"], errors="coerce")
        z = z.loc[z["expected_seq"].notna()].copy()
        z["expected_seq"] = z["expected_seq"].astype("int64")
        z["_core_valid"] = _bool_series(z["feature_core_valid"])
        parts.append(z)

    raw = pd.concat(parts, ignore_index=True)
    raw = raw.sort_values(["symbol", "expected_seq"]).reset_index(drop=True)

    q_ts = _target_timestamp_map(root)
    raw["target_timestamp_4b"] = (raw["expected_seq"] + 4).map(q_ts)

    beta = np.full(len(raw), np.nan, float)
    for sym, idxs in raw.groupby("symbol", sort=False).groups.items():
        idx = np.asarray(list(idxs), dtype=int)
        z = raw.loc[idx, ["expected_seq", "ret_1b", "qqq_ret_1b"]].copy()
        lo = int(z["expected_seq"].min())
        hi = int(z["expected_seq"].max())
        grid = pd.DataFrame({"expected_seq": np.arange(lo, hi + 1, dtype=np.int64)})
        grid = grid.merge(z, on="expected_seq", how="left")
        x = pd.to_numeric(grid["ret_1b"], errors="coerce")
        y = pd.to_numeric(grid["qqq_ret_1b"], errors="coerce")
        b = x.rolling(24, min_periods=12).cov(y) / y.rolling(24, min_periods=12).var().replace(0, np.nan)
        bm = pd.Series(b.to_numpy(), index=grid["expected_seq"])
        beta[idx] = bm.reindex(z["expected_seq"]).to_numpy(float)

    raw["beta24"] = np.clip(beta, -3, 3)
    raw["residual_ret_6b"] = raw["ret_6b"] - raw["beta24"] * raw["qqq_ret_6b"]

    g = raw.groupby("timestamp")
    for col in [
        "ret_1b", "ret_2b", "ret_4b", "ret_6b",
        "rv_6", "rv_24", "ma_dist_6", "ma_dist_24",
        "volume_z_24", "bar_range", "beta24", "residual_ret_6b",
    ]:
        raw["cs_" + col] = g[col].rank(pct=True, method="average")

    raw["universe_median_rv24"] = g["rv_24"].transform("median")
    raw["ix_trend_qqq"] = raw["ma_dist_24"] * raw["qqq_ma_dist_24"]
    raw["ix_vol_qqq"] = raw["rv_24"] * raw["qqq_rv_24"]
    raw["ix_ret1_qqq"] = raw["ret_1b"] * raw["qqq_ret_2b"]
    raw["ix_mom6_qqq"] = raw["ret_6b"] * raw["qqq_ret_6b"]

    ratio = raw["universe_median_rv24"] / raw["rv_24"].replace(0, np.nan)
    raw["exec_weight"] = ratio.clip(0.25, 1.0).fillna(1.0)
    raw["net10_return"] = raw["exec_weight"] * raw["fwd_ret_4b"] - raw["exec_weight"] * COST
    raw["target_net"] = raw["net10_return"]

    valid = (
        raw["_core_valid"]
        & raw["fwd_ret_4b"].notna()
        & raw["target_timestamp_4b"].notna()
        & (raw["target_timestamp_4b"] < RESEARCH_CUTOFF)
    )
    train = raw.loc[valid].copy()
    train["target_ordinal_net"] = (
        train.groupby("timestamp")["target_net"].rank(pct=True, method="average") - 0.5
    )
    train, path_audit = attach_path_proxy(train, canon_panel, live_panel)
    train["proxy_net_return"] = train["exec_weight"] * train["proxy_ret_4b"] - train["exec_weight"] * COST
    train["target_path_relative"] = (
        train["proxy_net_return"]
        - train.groupby("timestamp")["proxy_net_return"].transform("median")
    )
    return train.reset_index(drop=True), path_audit


def reconcile_training_features(train, frozen):
    keys = ["symbol", "expected_seq"]
    cols = keys + FEATURES
    a = train[cols].copy()
    b = frozen[cols].copy()
    m = a.merge(b, on=keys, how="inner", suffixes=("_train", "_frozen"), validate="one_to_one")

    details = []
    all_abs = []
    finite_same = 0
    total = 0
    for f in FEATURES:
        x = pd.to_numeric(m[f + "_train"], errors="coerce").to_numpy(float)
        y = pd.to_numeric(m[f + "_frozen"], errors="coerce").to_numpy(float)
        fx = np.isfinite(x)
        fy = np.isfinite(y)
        finite_same += int((fx == fy).sum())
        total += len(x)
        both = fx & fy
        d = np.abs(x[both] - y[both])
        if len(d):
            all_abs.append(d)
        details.append({
            "feature": f,
            "n": int(len(x)),
            "both_finite": int(both.sum()),
            "median_abs_diff": float(np.median(d)) if len(d) else None,
            "max_abs_diff": float(np.max(d)) if len(d) else None,
            "finite_agreement": float((fx == fy).mean()) if len(x) else None,
        })

    vals = np.concatenate(all_abs) if all_abs else np.array([], float)
    audit = {
        "matched_rows": int(len(m)),
        "median_abs_numeric_diff": float(np.median(vals)) if len(vals) else None,
        "max_abs_numeric_diff": float(np.max(vals)) if len(vals) else None,
        "finite_state_agreement": float(finite_same / total) if total else None,
        "details": details,
    }
    audit["pass"] = (
        audit["matched_rows"] > 5000
        and audit["median_abs_numeric_diff"] is not None
        and audit["median_abs_numeric_diff"] <= 1e-10
        and audit["finite_state_agreement"] >= 0.999
    )
    return audit


def simulate(scored, score_col):
    decisions = []
    for tstamp, g0 in scored.groupby("timestamp", sort=True):
        g = g0.dropna(
            subset=[
                score_col, "fwd_ret_4b",
                "rv_24", "universe_median_rv24", "target_timestamp_4b",
            ]
        ).copy()
        if len(g) < MIN_UNIVERSE:
            continue

        top = g.sort_values([score_col, "symbol"], ascending=[False, True]).iloc[0]
        decisions.append({
            "timestamp": top["timestamp"],
            "target_timestamp_4b": top["target_timestamp_4b"],
            "expected_seq": int(top["expected_seq"]),
            "fold": str(top["eval_fold"]),
            "symbol": str(top["symbol"]),
            "weight": float(top["exec_weight"]),
            "score": float(top[score_col]),
            "stock": float(top["fwd_ret_4b"]),
            "net10_return": float(top["net10_return"]),
            "proxy_net_return": (
                float(top["proxy_net_return"])
                if pd.notna(top["proxy_net_return"])
                else np.nan
            ),
        })

    d = pd.DataFrame(decisions).sort_values("timestamp")
    out = []
    next_free = pd.Timestamp.min.tz_localize("UTC")
    for _, r in d.iterrows():
        if r["timestamp"] < next_free:
            continue
        out.append(r.to_dict())
        next_free = r["target_timestamp_4b"]

    return pd.DataFrame(out)


def moving_block_indices(n, rng, block=BLOCK_DAYS):
    if n <= 0:
        return np.array([], dtype=np.int32)
    if n <= block:
        return rng.integers(0, n, size=n, dtype=np.int32)
    starts = np.arange(n - block + 1, dtype=np.int32)
    nb = int(np.ceil(n / block))
    s = rng.choice(starts, size=nb, replace=True)
    return (s[:, None] + np.arange(block)[None, :]).ravel()[:n].astype(np.int32)


def holm_adjust(pvals):
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    out = np.empty(len(p), float)
    run = 0.0
    m = len(p)
    for rank, idx in enumerate(order):
        run = max(run, (m - rank) * p[idx])
        out[idx] = min(1.0, run)
    return out


def paired_bootstrap(base, challenger, reps):
    a = base[["timestamp", "fold", "net10_return", "symbol"]].rename(
        columns={"net10_return": "base_return", "symbol": "base_symbol"}
    )
    z = challenger.merge(a, on=["timestamp", "fold"], how="inner", validate="one_to_one")
    z["paired_log_diff"] = np.log1p(z["net10_return"]) - np.log1p(z["base_return"])
    z["day"] = nts(z["timestamp"]).dt.floor("D")

    daily = z.groupby("day")["paired_log_diff"].sum().sort_index()
    arr = daily.to_numpy(float)
    rng = np.random.default_rng(RNG_SEED)
    vals = np.empty(reps, float)
    for i in range(reps):
        ix = moving_block_indices(len(arr), rng)
        vals[i] = float(arr[ix].mean())

    fold_rows = []
    for fold, g in z.groupby("fold"):
        fold_rows.append({
            "fold": str(fold),
            "paired_log_diff": float(g["paired_log_diff"].sum()),
            "same_symbol_rate": float((g["symbol"] == g["base_symbol"]).mean()),
            "paired_rows": int(len(g)),
        })

    return {
        "paired_rows": int(len(z)),
        "days": int(len(arr)),
        "obs_mean_daily_paired_log_diff": float(arr.mean()),
        "ci95_low": float(np.quantile(vals, 0.025)),
        "ci95_high": float(np.quantile(vals, 0.975)),
        "p_one_sided": float((np.sum(vals <= 0) + 1) / (reps + 1)),
        "folds": fold_rows,
    }


def schedule_audit(base, challenger):
    a = base[["timestamp", "fold"]].drop_duplicates().sort_values(["timestamp", "fold"]).reset_index(drop=True)
    b = challenger[["timestamp", "fold"]].drop_duplicates().sort_values(["timestamp", "fold"]).reset_index(drop=True)
    merged = a.merge(b, on=["timestamp", "fold"], how="outer", indicator=True)
    return {
        "base_rows": int(len(a)),
        "challenger_rows": int(len(b)),
        "matched_rows": int((merged["_merge"] == "both").sum()),
        "exact_match": bool(len(a) == len(b) and (merged["_merge"] == "both").all()),
    }


def load_frozen_inputs(r50):
    scored_path = r50 / "r5_0_1_scored_rows.parquet"
    ledger_path = r50 / "r5_0_1_trade_ledger.parquet"
    leaderboard_path = r50 / "r5_0_1_leaderboard.csv"
    model_path = r50 / "model_freeze/r5_hgb.joblib"

    missing = [str(p) for p in [scored_path, ledger_path, leaderboard_path, model_path] if not p.exists()]
    if missing:
        raise FileNotFoundError("missing frozen R5 inputs: " + ", ".join(missing))

    scored = pd.read_parquet(scored_path, columns=SCORED_COLUMNS)
    ledger = pd.read_parquet(ledger_path)
    leaderboard = pd.read_csv(leaderboard_path)
    model = joblib.load(model_path)

    return scored, ledger, leaderboard, model


def main():
    a = parse_args()
    root = Path(a.root)
    us = root / "US_ETF"
    r50 = us / "model_lab_v1/results/r5_0_1_research_sandbox_all_data"
    r6v1_metrics_path = us / "model_lab_v1/results/r6_selective_horizon/r6_metrics.csv"

    out = us / "model_lab_v1/results/r6_1_decision_target"
    out.mkdir(parents=True, exist_ok=True)
    exec_log = out / "r6_1_execution_log.json"

    if os.getenv("R6_ALLOW_LIVE", "").lower() == "true":
        raise RuntimeError("R6.1 refuses LIVE mode")

    checkpoint(exec_log, "START", research_cutoff=RESEARCH_CUTOFF.isoformat(), source="frozen_r5_scored_rows")

    scored, frozen_ledger, frozen_leaderboard, model_template = load_frozen_inputs(r50)

    scored["timestamp"] = nts(scored["timestamp"])
    scored["target_timestamp_4b"] = nts(scored["target_timestamp_4b"])
    scored = scored.loc[
        scored["target_timestamp_4b"].notna()
        & (scored["target_timestamp_4b"] < RESEARCH_CUTOFF)
    ].copy()

    if scored["symbol"].nunique() != 93:
        raise RuntimeError(f"expected 93 symbols, got {scored['symbol'].nunique()}")

    if len(scored) != EXPECTED_SCORED_ROWS:
        raise RuntimeError(
            f"frozen scored row count changed: expected {EXPECTED_SCORED_ROWS}, got {len(scored)}"
        )

    canon_panel = us / "directional_research/canonical_history_v1/panel_1h_gap_aware"
    live_panel = us / "directional_research/r4_live_canonical_v1/panel_1h_overlay"

    scored, scored_path_audit = attach_path_proxy(scored, canon_panel, live_panel)

    ratio = scored["universe_median_rv24"] / scored["rv_24"].replace(0, np.nan)
    scored["exec_weight"] = ratio.clip(0.25, 1.0).fillna(1.0)
    scored["net10_return"] = scored["exec_weight"] * scored["fwd_ret_4b"] - scored["exec_weight"] * COST
    scored["proxy_net_return"] = scored["exec_weight"] * scored["proxy_ret_4b"] - scored["exec_weight"] * COST

    overall_path_coverage = float(scored["path_complete"].mean())
    checkpoint(
        exec_log,
        "FROZEN_ROWS_READY",
        rows=len(scored),
        symbols=int(scored["symbol"].nunique()),
        path_coverage=overall_path_coverage,
        fwd_parity_median_abs_diff=scored_path_audit["fwd_parity_median_abs_diff"],
        fwd_parity_max_abs_diff=scored_path_audit["fwd_parity_max_abs_diff"],
    )
    if overall_path_coverage < PATH_COVERAGE_MIN:
        raise RuntimeError(
            f"canonical path coverage too low: {overall_path_coverage:.6f} < {PATH_COVERAGE_MIN:.6f}"
        )
    if (
        scored_path_audit["fwd_parity_median_abs_diff"] is None
        or scored_path_audit["fwd_parity_median_abs_diff"] > 1e-10
    ):
        raise RuntimeError(f"canonical 4H parity failed: {scored_path_audit}")

    symbols = sorted(scored["symbol"].astype(str).unique())
    train_all, train_path_audit = build_r1_training_rows(
        root, symbols, canon_panel, live_panel
    )

    feature_audit = reconcile_training_features(train_all, scored)
    checkpoint(
        exec_log,
        "TRAINING_SOURCE_READY",
        rows=len(train_all),
        first_timestamp=str(train_all["timestamp"].min()),
        last_timestamp=str(train_all["timestamp"].max()),
        path_coverage=float(train_all["path_complete"].mean()),
        feature_matched_rows=feature_audit["matched_rows"],
        feature_median_abs_diff=feature_audit["median_abs_numeric_diff"],
        feature_finite_agreement=feature_audit["finite_state_agreement"],
    )
    if not feature_audit["pass"]:
        (out / "r6_1_feature_reconciliation.json").write_text(
            json.dumps(feature_audit, indent=2, ensure_ascii=False, default=str) + "\n"
        )
        raise RuntimeError(
            "R1-derived training features do not reconcile to frozen R5 scored rows; "
            f"see {out / 'r6_1_feature_reconciliation.json'}"
        )

    base = frozen_ledger.loc[
        (frozen_ledger["candidate"] == "R5C0_HGB_REFERENCE")
        & (frozen_ledger["fold"].astype(str).isin(EVAL_FOLD_NAMES))
    ].copy()
    if base.empty:
        raise RuntimeError("frozen R5 common-OOS baseline ledger missing")

    base["timestamp"] = nts(base["timestamp"])
    base["target_timestamp_4b"] = nts(base["target_timestamp_4b"])
    base["fold"] = base["fold"].astype(str)

    proxy_lookup = scored[
        ["timestamp", "symbol", "proxy_net_return", "path_complete"]
    ].drop_duplicates(["timestamp", "symbol"])
    base = base.merge(proxy_lookup, on=["timestamp", "symbol"], how="left", validate="many_to_one")

    if not r6v1_metrics_path.exists():
        raise FileNotFoundError(
            f"missing prior R6 common-OOS reference metrics: {r6v1_metrics_path}"
        )
    r6v1_metrics = pd.read_csv(r6v1_metrics_path)
    ref_rows = r6v1_metrics.loc[r6v1_metrics["arm"] == "R5_BASE_4H"]
    if ref_rows.empty:
        raise RuntimeError("R5_BASE_4H missing from prior R6 common-OOS metrics")
    frozen_row = ref_rows.iloc[0]

    base_primary = metrics(base, "net10_return")
    baseline_reconciliation = {
        "scope": "E2-E8 common OOS",
        "trades_match": int(base_primary["trades"]) == int(frozen_row["trades"]),
        "cum_return_abs_diff": abs(float(base_primary["cum_return"]) - float(frozen_row["cum_return"])),
        "log_growth_abs_diff": abs(float(base_primary["log_growth"]) - float(frozen_row["log_growth"])),
        "mdd_abs_diff": abs(float(base_primary["mdd"]) - float(frozen_row["max_drawdown"])),
    }
    baseline_reconciliation["pass"] = (
        baseline_reconciliation["trades_match"]
        and baseline_reconciliation["cum_return_abs_diff"] <= 1e-10
        and baseline_reconciliation["log_growth_abs_diff"] <= 1e-10
        and baseline_reconciliation["mdd_abs_diff"] <= 1e-10
    )
    if not baseline_reconciliation["pass"]:
        checkpoint(exec_log, "FROZEN_LEDGER_RECONCILIATION_FAIL", parity=baseline_reconciliation)
        raise RuntimeError(f"frozen R5 ledger/leaderboard mismatch: {baseline_reconciliation}")

    base_proxy_coverage = float(base["proxy_net_return"].notna().mean())
    if base_proxy_coverage < PATH_COVERAGE_MIN:
        raise RuntimeError(
            f"baseline proxy coverage too low: {base_proxy_coverage:.6f} < {PATH_COVERAGE_MIN:.6f}"
        )

    checkpoint(
        exec_log,
        "BASELINE_RECONCILED",
        trades=int(base_primary["trades"]),
        cum_return=base_primary["cum_return"],
        log_growth=base_primary["log_growth"],
        mdd=base_primary["mdd"],
        proxy_coverage=base_proxy_coverage,
    )

    scored_parts = []
    fold_contract = []

    for i, (fold, ss, ee) in enumerate(EVAL_FOLDS, 1):
        start = ts(ss)
        end = ts(ee)

        tr = train_all.loc[train_all["target_timestamp_4b"] < start].copy()
        te = scored.loc[
            (scored["fold"].astype(str) == fold)
            & (scored["timestamp"] >= start)
            & (scored["timestamp"] < end)
        ].copy()

        valid_ts = te.groupby("timestamp")["symbol"].nunique()
        valid_ts = set(valid_ts[valid_ts >= MIN_UNIVERSE].index)
        te = te.loc[te["timestamp"].isin(valid_ts)].copy()
        te["eval_fold"] = fold

        if len(tr) == 0 or len(te) == 0:
            raise RuntimeError(f"empty fold {fold}: train={len(tr)} test={len(te)}")

        expected_train = EXPECTED_TRAIN_ROWS[fold]
        if len(tr) != expected_train:
            checkpoint(
                exec_log,
                "TRAIN_ROW_COUNT_MISMATCH",
                fold=fold,
                expected=expected_train,
                observed=len(tr),
                train_last_target=str(tr["target_timestamp_4b"].max()),
            )
            raise RuntimeError(
                f"{fold} training rows mismatch: expected {expected_train}, got {len(tr)}"
            )

        # Freeze the actual R5 control scores rather than recreating the baseline.
        te[CONTROL] = te["R5C0_HGB_REFERENCE"]
        if te[CONTROL].notna().mean() < 0.99:
            raise RuntimeError(f"frozen R5 scores unexpectedly sparse in {fold}")

        med = tr[FEATURES].median()

        for cand, target in CHALLENGERS.items():
            train = tr.loc[tr[target].notna()].copy()
            model = clone(model_template)
            model.fit(train[FEATURES].fillna(med), train[target])
            te[cand] = model.predict(te[FEATURES].fillna(med))

        scored_parts.append(te)

        fold_contract.append({
            "fold": fold,
            "train_rows": int(len(tr)),
            "test_rows": int(len(te)),
            "common_test_timestamps": int(te["timestamp"].nunique()),
            "train_last_target": str(tr["target_timestamp_4b"].max()),
            "test_first": str(te["timestamp"].min()),
            "test_last": str(te["timestamp"].max()),
            "expected_train_rows": int(EXPECTED_TRAIN_ROWS[fold]),
            "train_path_target_rows": int(tr["target_path_relative"].notna().sum()),
            "train_path_coverage": float(tr["path_complete"].mean()),
            "test_path_coverage": float(te["path_complete"].mean()),
        })
        checkpoint(
            exec_log,
            "FOLD_COMPLETE",
            fold=fold,
            index=i,
            train_rows=len(tr),
            test_rows=len(te),
        )

    eval_rows = pd.concat(scored_parts, ignore_index=True)

    ledgers = [base.assign(candidate=CONTROL)]
    summary_rows = []
    fold_rows = []
    schedule_rows = []

    base_eff, base_top = effective_names(base["symbol"], base["weight"])
    base_proxy = metrics(base, "proxy_net_return")
    summary_rows.append({
        "candidate": CONTROL,
        **{f"primary_{k}": v for k, v in base_primary.items()},
        **{f"proxy_{k}": v for k, v in base_proxy.items()},
        "proxy_coverage": base_proxy_coverage,
        "effective_names": base_eff,
        "top_ticker_share": base_top,
    })

    for fold, z in base.groupby("fold"):
        pm = metrics(z, "net10_return")
        xm = metrics(z, "proxy_net_return")
        fold_rows.append({
            "candidate": CONTROL,
            "fold": str(fold),
            **{f"primary_{k}": v for k, v in pm.items()},
            **{f"proxy_{k}": v for k, v in xm.items()},
            "proxy_coverage": float(z["proxy_net_return"].notna().mean()),
        })

    for cand in CHALLENGERS:
        t = simulate(eval_rows, cand)
        t["candidate"] = cand

        sched = schedule_audit(base, t)
        schedule_rows.append({"candidate": cand, **sched})
        if not sched["exact_match"]:
            checkpoint(exec_log, "SCHEDULE_MISMATCH", candidate=cand, audit=sched)
            raise RuntimeError(f"{cand} non-overlap schedule does not match frozen R5 schedule: {sched}")

        ledgers.append(t)

        primary = metrics(t, "net10_return")
        proxy = metrics(t, "proxy_net_return")
        proxy_cov = float(t["proxy_net_return"].notna().mean())
        eff, top_share = effective_names(t["symbol"], t["weight"])

        summary_rows.append({
            "candidate": cand,
            **{f"primary_{k}": v for k, v in primary.items()},
            **{f"proxy_{k}": v for k, v in proxy.items()},
            "proxy_coverage": proxy_cov,
            "effective_names": eff,
            "top_ticker_share": top_share,
        })

        for fold, z in t.groupby("fold"):
            pm = metrics(z, "net10_return")
            xm = metrics(z, "proxy_net_return")
            fold_rows.append({
                "candidate": cand,
                "fold": str(fold),
                **{f"primary_{k}": v for k, v in pm.items()},
                **{f"proxy_{k}": v for k, v in xm.items()},
                "proxy_coverage": float(z["proxy_net_return"].notna().mean()),
            })

    ledger = pd.concat(ledgers, ignore_index=True)
    leaderboard = pd.DataFrame(summary_rows)
    folds = pd.DataFrame(fold_rows)
    schedule_df = pd.DataFrame(schedule_rows)

    boot_rows = []
    paired_fold_rows = []
    for cand in CHALLENGERS:
        t = ledger.loc[ledger["candidate"] == cand].copy()
        b = paired_bootstrap(base, t, a.bootstrap)
        boot_rows.append({
            "candidate": cand,
            "paired_rows": b["paired_rows"],
            "days": b["days"],
            "obs_mean_daily_paired_log_diff": b["obs_mean_daily_paired_log_diff"],
            "ci95_low": b["ci95_low"],
            "ci95_high": b["ci95_high"],
            "p_one_sided": b["p_one_sided"],
        })
        for x in b["folds"]:
            paired_fold_rows.append({"candidate": cand, **x})

    boot = pd.DataFrame(boot_rows)
    boot["holm_p"] = holm_adjust(boot["p_one_sided"].to_numpy(float))
    paired_folds = pd.DataFrame(paired_fold_rows)

    pos = (
        paired_folds.assign(pos=paired_folds["paired_log_diff"] > 0)
        .groupby("candidate")["pos"]
        .sum()
    )

    leaderboard = leaderboard.merge(boot, on="candidate", how="left")
    leaderboard["positive_paired_folds"] = leaderboard["candidate"].map(pos)

    base_row = leaderboard.loc[leaderboard["candidate"] == CONTROL].iloc[0]
    base_primary_growth = float(base_row["primary_log_growth"])
    base_primary_pf = float(base_row["primary_profit_factor"])
    base_primary_mdd = float(base_row["primary_mdd"])
    base_proxy_growth = float(base_row["proxy_log_growth"])

    leaderboard["research_survivor"] = False
    m = leaderboard["candidate"] != CONTROL
    leaderboard.loc[m, "research_survivor"] = (
        (leaderboard.loc[m, "primary_log_growth"] > base_primary_growth)
        & (leaderboard.loc[m, "primary_profit_factor"] >= base_primary_pf)
        & (leaderboard.loc[m, "primary_mdd"] >= base_primary_mdd - 0.02)
        & (leaderboard.loc[m, "proxy_log_growth"] >= base_proxy_growth)
        & (leaderboard.loc[m, "proxy_coverage"] >= PATH_COVERAGE_MIN)
        & (leaderboard.loc[m, "positive_paired_folds"].fillna(0) >= 5)
        & (leaderboard.loc[m, "ci95_low"] > 0)
        & (leaderboard.loc[m, "holm_p"] < 0.05)
        & (leaderboard.loc[m, "primary_trades"] >= 300)
        & (leaderboard.loc[m, "effective_names"] >= 5)
        & (leaderboard.loc[m, "top_ticker_share"] <= 0.35)
    )

    surv = leaderboard.loc[leaderboard["research_survivor"]].copy()
    selected = None
    if len(surv):
        surv = surv.sort_values(
            ["primary_log_growth", "primary_mdd", "proxy_log_growth", "effective_names", "candidate"],
            ascending=[False, False, False, False, True],
        )
        selected = str(surv.iloc[0]["candidate"])

    decision = {
        "schema": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "SUCCESS",
        "research_cutoff": RESEARCH_CUTOFF.isoformat(),
        "research_only": True,
        "production_changed": False,
        "r5_1_untouched": True,
        "source_contract": "R1 frozen historical rows for challenger training; frozen R5 scored rows for E2-E8 evaluation",
        "baseline_reconciliation": baseline_reconciliation,
        "feature_reconciliation": feature_audit,
        "scored_path_audit": scored_path_audit,
        "training_path_audit": train_path_audit,
        "overall_path_coverage": overall_path_coverage,
        "baseline_proxy_coverage": base_proxy_coverage,
        "expected_train_rows": EXPECTED_TRAIN_ROWS,
        "schedule_audit": schedule_df.to_dict(orient="records"),
        "evaluation_folds": [x[0] for x in EVAL_FOLDS],
        "warmup_fold": FOLDS[0][0],
        "candidates": [CONTROL, *CHALLENGERS.keys()],
        "research_survivors": surv["candidate"].tolist() if len(surv) else [],
        "selected_r6_1_candidate": selected,
        "promotion_eligible": selected is not None,
        "live_action": "NONE",
    }

    pd.DataFrame(fold_contract).to_csv(out / "r6_1_fold_contract.csv", index=False)
    (out / "r6_1_feature_reconciliation.json").write_text(
        json.dumps(feature_audit, indent=2, ensure_ascii=False, default=str) + "\n"
    )
    (out / "r6_1_path_audit.json").write_text(
        json.dumps(
            {"scored": scored_path_audit, "training": train_path_audit},
            indent=2,
            ensure_ascii=False,
            default=str,
        ) + "\n"
    )
    keep = [
        "timestamp", "target_timestamp_4b", "expected_seq", "symbol", "eval_fold",
        "exec_weight", "fwd_ret_4b", "proxy_ret_4b", "net10_return", "proxy_net_return",
        "R5C0_HGB_REFERENCE", CONTROL, *CHALLENGERS.keys(),
    ]
    eval_rows[keep].to_parquet(out / "r6_1_scored_rows.parquet", index=False)
    ledger.to_parquet(out / "r6_1_trade_ledger.parquet", index=False)
    folds.to_csv(out / "r6_1_fold_summary.csv", index=False)
    paired_folds.to_csv(out / "r6_1_paired_fold_summary.csv", index=False)
    boot.to_csv(out / "r6_1_paired_bootstrap.csv", index=False)
    schedule_df.to_csv(out / "r6_1_schedule_audit.csv", index=False)
    leaderboard.to_csv(out / "r6_1_leaderboard.csv", index=False)
    (out / "r6_1_selection_decision.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=False, default=str) + "\n"
    )

    (out / "r6_1_target_contract.json").write_text(
        json.dumps({
            "schema": SCHEMA,
            "research_cutoff": RESEARCH_CUTOFF.isoformat(),
            "training_source": "r1_directional_v1_2/primary_train for 93 frozen R5 symbols",
            "evaluation_source": "frozen r5_0_1_scored_rows.parquet (497,504 OOS rows)",
            "training_protocol": "original R5 expanding fold counts enforced; E2-E8 paired common-OOS evaluation",
            "baseline": "frozen R5C0_HGB_REFERENCE trade ledger restricted to E2-E8",
            "features": FEATURES,
            "challengers": CHALLENGERS,
            "cost": COST,
            "stop": STOP,
            "take": TAKE,
            "horizon_buckets": 4,
            "same_bar_stop_take_rule": "STOP_FIRST_CONSERVATIVE",
            "path_coverage_min": PATH_COVERAGE_MIN,
            "model_template": "clone(model_freeze/r5_hgb.joblib)",
        }, indent=2, ensure_ascii=False) + "\n"
    )

    sources = [
        r50 / "r5_0_1_scored_rows.parquet",
        r50 / "r5_0_1_trade_ledger.parquet",
        r50 / "r5_0_1_leaderboard.csv",
        r50 / "model_freeze/r5_hgb.joblib",
        root / "US_ETF/directional_research/r1_directional_v1_2/r1_dataset_manifest.json",
        r6v1_metrics_path,
    ]
    (out / "r6_1_manifest.json").write_text(
        json.dumps({
            "schema": SCHEMA,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "research_only": True,
            "sources": {str(p): sha256_file(p) for p in sources},
        }, indent=2, ensure_ascii=False) + "\n"
    )

    checkpoint(
        exec_log,
        "SUCCESS",
        baseline_reconciliation=baseline_reconciliation,
        survivors=decision["research_survivors"],
        selected=selected,
    )

    print("\n=== R6.1 LEADERBOARD ===")
    print(leaderboard.to_string(index=False))
    print("\n=== R6.1 DECISION ===")
    print(json.dumps(decision, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
