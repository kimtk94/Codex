from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

SCHEMA = "kalman-r6-1-decision-target-v1"
COST = 0.001
STOP = -0.03
TAKE = 0.20
MIN_UNIVERSE = 80
BLOCK_DAYS = 5
B_DEFAULT = 2000
RNG_SEED = 20260922

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

FEATURES = [
    "cs_ret_1b", "cs_ret_2b", "cs_ret_4b", "cs_ret_6b",
    "cs_rv_6", "cs_rv_24", "cs_ma_dist_6", "cs_ma_dist_24",
    "cs_volume_z_24", "cs_bar_range", "cs_beta24", "cs_residual_ret_6b",
    "qqq_ret_2b", "qqq_ret_6b", "qqq_rv_24", "qqq_ma_dist_24",
    "ix_trend_qqq", "ix_vol_qqq", "ix_ret1_qqq", "ix_mom6_qqq",
]

CANDIDATES = {
    "R6T0_RELATIVE_HGB": "target_relative",
    "R6T1_NET_HGB": "target_net",
    "R6T2_ORDINAL_NET_HGB": "target_ordinal_net",
    "R6T3_PATH_REL_HGB": "target_path_relative",
}


def parse_args():
    p = argparse.ArgumentParser()
    root = Path(os.getenv("KALMAN_DATA_ROOT", "/content/drive/MyDrive"))
    p.add_argument("--root", default=str(root))
    p.add_argument("--bootstrap", type=int, default=B_DEFAULT)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def nts(x):
    return pd.to_datetime(x, utc=True, errors="coerce")


def ts(x):
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def max_dd(r):
    r = np.asarray(r, float)
    if len(r) == 0:
        return np.nan
    eq = np.r_[1.0, np.cumprod(1.0 + r)]
    peak = np.maximum.accumulate(eq)
    return float(np.min(eq / peak - 1.0))


def pf(r):
    r = np.asarray(r, float)
    pos = r[r > 0].sum()
    neg = -r[r < 0].sum()
    return float(pos / neg) if neg > 0 else np.inf


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


def load_locked(path, sym):
    p = path / f"{sym}_1h_gap_aware.parquet"
    if not p.exists():
        raise FileNotFoundError(p)
    z = pd.read_parquet(p)
    if "timestamp" in z.columns:
        z["timestamp"] = nts(z["timestamp"])
    else:
        z["market_open_utc"] = nts(z["market_open_utc"])
        z["timestamp"] = z["market_open_utc"] + pd.to_timedelta(
            pd.to_numeric(z["session_bucket"], errors="coerce"), unit="h"
        )
    z["expected_seq"] = pd.to_numeric(z["expected_seq"], errors="raise").astype("int64")
    z["symbol"] = sym
    return z


def combine_symbol(canon_panel, live_panel, sym):
    a = load_locked(canon_panel, sym)
    p = live_panel / f"{sym}_1h_live.parquet"
    if p.exists():
        b = pd.read_parquet(p)
        if len(b):
            b["timestamp"] = nts(b["timestamp"])
            b["expected_seq"] = pd.to_numeric(b["expected_seq"], errors="raise").astype("int64")
            b["symbol"] = sym
            b = b.loc[b["timestamp"] > a["timestamp"].max()]
            a = pd.concat([a, b], ignore_index=True)
    return (
        a.sort_values("expected_seq")
        .drop_duplicates("expected_seq", keep="first")
        .reset_index(drop=True)
    )


def gap_features(obs, q_ts):
    obs = obs.copy().sort_values("expected_seq")
    lo = int(obs["expected_seq"].min())
    hi = int(obs["expected_seq"].max())
    g = pd.DataFrame({"expected_seq": np.arange(lo, hi + 1, dtype=np.int64)})
    cols = [
        c for c in ["expected_seq", "timestamp", "open", "high", "low", "close", "volume"]
        if c in obs.columns
    ]
    g = g.merge(obs[cols], on="expected_seq", how="left")

    c = pd.to_numeric(g["close"], errors="coerce")
    h = pd.to_numeric(g["high"], errors="coerce")
    l = pd.to_numeric(g["low"], errors="coerce")
    v = pd.to_numeric(g["volume"], errors="coerce")

    for k in [1, 2, 4, 6]:
        g[f"ret_{k}b"] = c / c.shift(k) - 1.0

    g["bar_range"] = (h - l) / c
    g["rv_6"] = g["ret_1b"].rolling(6, min_periods=4).std()
    g["rv_24"] = g["ret_1b"].rolling(24, min_periods=18).std()
    g["ma_dist_6"] = c / c.rolling(6, min_periods=5).mean() - 1.0
    g["ma_dist_24"] = c / c.rolling(24, min_periods=18).mean() - 1.0

    lv = np.log1p(v)
    mu = lv.rolling(24, min_periods=18).mean()
    sd = lv.rolling(24, min_periods=18).std()
    g["volume_z_24"] = (lv - mu) / sd.replace(0, np.nan)

    g["fwd_ret_4b"] = c.shift(-4) / c - 1.0
    g["target_expected_seq"] = g["expected_seq"] + 4
    g["target_timestamp_4b"] = g["target_expected_seq"].map(q_ts)

    proxy = g["fwd_ret_4b"].to_numpy(float)
    unresolved = np.isfinite(proxy)
    for k in [1, 2, 3, 4]:
        stop_touch = (l.shift(-k) / c - 1.0).to_numpy(float) <= STOP
        take_touch = (h.shift(-k) / c - 1.0).to_numpy(float) >= TAKE
        both = unresolved & stop_touch & take_touch
        stop_only = unresolved & stop_touch & ~take_touch
        take_only = unresolved & take_touch & ~stop_touch
        proxy[both | stop_only] = STOP
        proxy[take_only] = TAKE
        unresolved[both | stop_only | take_only] = False

    g["proxy_ret_4b"] = proxy
    return g.loc[g["close"].notna()].copy()


def hgb():
    return HistGradientBoostingRegressor(
        learning_rate=0.05,
        max_iter=100,
        max_leaf_nodes=15,
        min_samples_leaf=100,
        l2_regularization=1.0,
        random_state=42,
    )


def effective_names(symbols, weights):
    t = pd.DataFrame({"symbol": list(symbols), "w": list(weights)}).groupby("symbol")["w"].sum()
    x = t / t.sum()
    return float(1.0 / x.pow(2).sum()), float(x.max())


def simulate(scored, candidate):
    decisions = []
    for tstamp, g0 in scored.groupby("timestamp", sort=True):
        g = g0.dropna(
            subset=[
                candidate, "fwd_ret_4b", "proxy_net_return",
                "rv_24", "universe_median_rv24", "target_timestamp_4b",
            ]
        ).copy()
        if len(g) < MIN_UNIVERSE:
            continue
        top = g.sort_values([candidate, "symbol"], ascending=[False, True]).iloc[0]
        w = float(top["exec_weight"])
        decisions.append({
            "timestamp": top["timestamp"],
            "target_timestamp_4b": top["target_timestamp_4b"],
            "expected_seq": int(top["expected_seq"]),
            "fold": str(top["fold"]),
            "symbol": str(top["symbol"]),
            "weight": w,
            "score": float(top[candidate]),
            "stock": float(top["fwd_ret_4b"]),
            "net10_return": float(top["net10_return"]),
            "proxy_net_return": float(top["proxy_net_return"]),
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


def metrics(t, ret_col):
    if t.empty:
        return {
            "trades": 0, "cum_return": np.nan, "log_growth": np.nan,
            "avg_return": np.nan, "median_return": np.nan, "win_rate": np.nan,
            "profit_factor": np.nan, "mdd": np.nan,
        }
    r = pd.to_numeric(t[ret_col], errors="coerce").dropna().to_numpy(float)
    return {
        "trades": int(len(r)),
        "cum_return": float(np.prod(1 + r) - 1),
        "log_growth": float(np.log1p(r).sum()),
        "avg_return": float(r.mean()),
        "median_return": float(np.median(r)),
        "win_rate": float((r > 0).mean()),
        "profit_factor": pf(r),
        "mdd": max_dd(r),
    }


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


def load_r5_reference(path):
    z = pd.read_csv(path)
    r = z.loc[z["candidate"] == "R5C0_HGB_REFERENCE"]
    if r.empty:
        raise RuntimeError("R5C0_HGB_REFERENCE missing from frozen leaderboard")
    return r.iloc[0]


def main():
    a = parse_args()
    root = Path(a.root)
    us = root / "US_ETF"

    canon = us / "directional_research/canonical_history_v1"
    canon_panel = canon / "panel_1h_gap_aware"
    canon_qqq = canon / "qqq_context/history_1h/QQQ_1h_gap_aware.parquet"

    live = us / "directional_research/r4_live_canonical_v1"
    live_panel = live / "panel_1h_overlay"
    live_qqq = live / "qqq_context/QQQ_1h_live.parquet"

    r291 = us / "model_lab_v1/results/r2_9_1_dual_engine"
    r50 = us / "model_lab_v1/results/r5_0_1_research_sandbox_all_data"
    r5_leaderboard = r50 / "r5_0_1_leaderboard.csv"

    out = us / "model_lab_v1/results/r6_1_decision_target"
    out.mkdir(parents=True, exist_ok=True)
    exec_log = out / "r6_1_execution_log.json"

    if os.getenv("R6_ALLOW_LIVE", "").lower() == "true":
        raise RuntimeError("R6.1 refuses LIVE mode")

    checkpoint(exec_log, "START", research_cutoff=RESEARCH_CUTOFF.isoformat())

    contract = pd.read_csv(r291 / "r2_9_1_model_contract.csv")
    symbols = sorted(contract["symbol"].astype(str).unique())
    if len(symbols) != 93:
        raise RuntimeError(f"expected 93 symbols, got {len(symbols)}")

    q0 = pd.read_parquet(canon_qqq)
    if "timestamp" in q0.columns:
        q0["timestamp"] = nts(q0["timestamp"])
    else:
        q0["market_open_utc"] = nts(q0["market_open_utc"])
        q0["timestamp"] = q0["market_open_utc"] + pd.to_timedelta(
            pd.to_numeric(q0["session_bucket"], errors="coerce"), unit="h"
        )
    q0["expected_seq"] = pd.to_numeric(q0["expected_seq"], errors="raise").astype("int64")

    q1 = pd.read_parquet(live_qqq) if live_qqq.exists() else pd.DataFrame()
    if len(q1):
        q1["timestamp"] = nts(q1["timestamp"])
        q1["expected_seq"] = pd.to_numeric(q1["expected_seq"], errors="raise").astype("int64")
        q1 = q1.loc[q1["timestamp"] > q0["timestamp"].max()]

    qqq = (
        pd.concat([q0, q1], ignore_index=True)
        .sort_values("expected_seq")
        .drop_duplicates("expected_seq", keep="first")
    )
    q_ts = qqq.set_index("expected_seq")["timestamp"]

    qb = gap_features(qqq, q_ts)
    qcols = {
        "ret_1b": "qqq_ret_1b",
        "ret_2b": "qqq_ret_2b",
        "ret_4b": "qqq_ret_4b",
        "ret_6b": "qqq_ret_6b",
        "rv_24": "qqq_rv_24",
        "ma_dist_24": "qqq_ma_dist_24",
    }
    qctx = qb[["expected_seq"] + list(qcols)].rename(columns=qcols)

    parts = []
    for i, sym in enumerate(symbols, 1):
        b = gap_features(combine_symbol(canon_panel, live_panel, sym), q_ts)
        b["symbol"] = sym
        b = b.merge(qctx, on="expected_seq", how="left", validate="one_to_one")
        b["timestamp"] = nts(b["timestamp"])
        parts.append(b)
        if i % 10 == 0 or i == len(symbols):
            checkpoint(exec_log, "BASE_FEATURE_PROGRESS", done=i, total=len(symbols))

    df = pd.concat(parts, ignore_index=True)
    df = df.loc[
        df["target_timestamp_4b"].notna()
        & df["fwd_ret_4b"].notna()
        & df["proxy_ret_4b"].notna()
        & (df["target_timestamp_4b"] < RESEARCH_CUTOFF)
    ].copy()

    df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

    beta = np.full(len(df), np.nan, float)
    for sym, idxs in df.groupby("symbol", sort=False).groups.items():
        idx = np.asarray(list(idxs), dtype=int)
        x = df.loc[idx, "ret_1b"]
        y = df.loc[idx, "qqq_ret_1b"]
        cov = x.rolling(24, min_periods=12).cov(y)
        var = y.rolling(24, min_periods=12).var()
        beta[idx] = (cov / var.replace(0, np.nan)).to_numpy()

    df["beta24"] = np.clip(beta, -3, 3)
    df["residual_ret_6b"] = df["ret_6b"] - df["beta24"] * df["qqq_ret_6b"]

    g = df.groupby("timestamp")
    df["universe_median_ret"] = g["fwd_ret_4b"].transform("median")
    df["universe_median_rv24"] = g["rv_24"].transform("median")
    df["target_relative"] = df["fwd_ret_4b"] - df["universe_median_ret"]

    for c in [
        "ret_1b", "ret_2b", "ret_4b", "ret_6b", "rv_6", "rv_24",
        "ma_dist_6", "ma_dist_24", "volume_z_24", "bar_range",
        "beta24", "residual_ret_6b",
    ]:
        df["cs_" + c] = g[c].rank(pct=True, method="average")

    df["ix_trend_qqq"] = df["ma_dist_24"] * df["qqq_ma_dist_24"]
    df["ix_vol_qqq"] = df["rv_24"] * df["qqq_rv_24"]
    df["ix_ret1_qqq"] = df["ret_1b"] * df["qqq_ret_2b"]
    df["ix_mom6_qqq"] = df["ret_6b"] * df["qqq_ret_6b"]

    ratio = df["universe_median_rv24"] / df["rv_24"].replace(0, np.nan)
    df["exec_weight"] = ratio.clip(0.25, 1.0).fillna(1.0)
    df["net10_return"] = df["exec_weight"] * df["fwd_ret_4b"] - df["exec_weight"] * COST
    df["proxy_net_return"] = df["exec_weight"] * df["proxy_ret_4b"] - df["exec_weight"] * COST

    df["target_net"] = df["net10_return"]
    df["target_ordinal_net"] = (
        df.groupby("timestamp")["target_net"].rank(pct=True, method="average") - 0.5
    )
    df["target_path_relative"] = (
        df["proxy_net_return"]
        - df.groupby("timestamp")["proxy_net_return"].transform("median")
    )

    df = df.replace([np.inf, -np.inf], np.nan)

    checkpoint(
        exec_log, "DATA_READY",
        rows=len(df),
        first_timestamp=str(df["timestamp"].min()),
        last_timestamp=str(df["timestamp"].max()),
        last_target=str(df["target_timestamp_4b"].max()),
    )

    scored_parts = []
    fold_contract = []

    for i, (fold, ss, ee) in enumerate(FOLDS, 1):
        start = ts(ss)
        end = ts(ee)

        tr = df.loc[df["target_timestamp_4b"] < start].copy()
        te = df.loc[(df["timestamp"] >= start) & (df["timestamp"] < end)].copy()

        valid_ts = te.groupby("timestamp")["symbol"].nunique()
        valid_ts = set(valid_ts[valid_ts >= MIN_UNIVERSE].index)
        te = te.loc[te["timestamp"].isin(valid_ts)].copy()

        if len(tr) == 0 or len(te) == 0:
            raise RuntimeError(f"empty fold {fold}: train={len(tr)} test={len(te)}")

        for cand, target in CANDIDATES.items():
            train = tr.loc[tr[target].notna()].copy()
            med = train[FEATURES].median()
            model = hgb()
            model.fit(train[FEATURES].fillna(med), train[target])
            te[cand] = model.predict(te[FEATURES].fillna(med))

        te["fold"] = fold
        scored_parts.append(te)

        fold_contract.append({
            "fold": fold,
            "train_rows": int(len(tr)),
            "test_rows": int(len(te)),
            "common_test_timestamps": int(te["timestamp"].nunique()),
            "train_last_target": str(tr["target_timestamp_4b"].max()),
            "test_first": str(te["timestamp"].min()),
            "test_last": str(te["timestamp"].max()),
        })
        checkpoint(exec_log, "FOLD_COMPLETE", fold=fold, index=i, train_rows=len(tr), test_rows=len(te))

    scored = pd.concat(scored_parts, ignore_index=True)

    ledgers = []
    summary_rows = []
    fold_rows = []

    for cand in CANDIDATES:
        t = simulate(scored, cand)
        t["candidate"] = cand
        ledgers.append(t)

        primary = metrics(t, "net10_return")
        proxy = metrics(t, "proxy_net_return")
        eff, top_share = effective_names(t["symbol"], t["weight"])

        summary_rows.append({
            "candidate": cand,
            **{f"primary_{k}": v for k, v in primary.items()},
            **{f"proxy_{k}": v for k, v in proxy.items()},
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
            })

    ledger = pd.concat(ledgers, ignore_index=True)
    leaderboard = pd.DataFrame(summary_rows)
    folds = pd.DataFrame(fold_rows)

    base = ledger.loc[ledger["candidate"] == "R6T0_RELATIVE_HGB"].copy()
    base_row = leaderboard.loc[leaderboard["candidate"] == "R6T0_RELATIVE_HGB"].iloc[0]

    frozen = load_r5_reference(r5_leaderboard)
    parity = {
        "trades": int(base_row["primary_trades"]) == int(frozen["trades"]),
        "cum_return_abs_diff": abs(float(base_row["primary_cum_return"]) - float(frozen["net10_cum_return"])),
        "log_growth_abs_diff": abs(float(base_row["primary_log_growth"]) - float(frozen["net10_log_growth"])),
        "mdd_abs_diff": abs(float(base_row["primary_mdd"]) - float(frozen["net10_mdd"])),
    }
    parity["pass"] = (
        parity["trades"]
        and parity["cum_return_abs_diff"] <= 1e-8
        and parity["log_growth_abs_diff"] <= 1e-8
        and parity["mdd_abs_diff"] <= 1e-8
    )

    if not parity["pass"]:
        checkpoint(exec_log, "BASELINE_RECONCILIATION_FAIL", parity=parity)
        raise RuntimeError(f"R6T0 failed R5 baseline reconciliation: {parity}")

    boot_rows = []
    fold_pair_rows = []
    for cand in [c for c in CANDIDATES if c != "R6T0_RELATIVE_HGB"]:
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
            fold_pair_rows.append({"candidate": cand, **x})

    boot = pd.DataFrame(boot_rows)
    boot["holm_p"] = holm_adjust(boot["p_one_sided"].to_numpy(float))
    paired_folds = pd.DataFrame(fold_pair_rows)

    pos = paired_folds.assign(pos=paired_folds["paired_log_diff"] > 0).groupby("candidate")["pos"].sum()
    leaderboard = leaderboard.merge(boot, on="candidate", how="left")
    leaderboard["positive_paired_folds"] = leaderboard["candidate"].map(pos)

    base_primary_growth = float(base_row["primary_log_growth"])
    base_primary_pf = float(base_row["primary_profit_factor"])
    base_primary_mdd = float(base_row["primary_mdd"])
    base_proxy_growth = float(base_row["proxy_log_growth"])

    leaderboard["research_survivor"] = False
    challenger_mask = leaderboard["candidate"] != "R6T0_RELATIVE_HGB"
    m = challenger_mask
    leaderboard.loc[m, "research_survivor"] = (
        (leaderboard.loc[m, "primary_log_growth"] > base_primary_growth)
        & (leaderboard.loc[m, "primary_profit_factor"] >= base_primary_pf)
        & (leaderboard.loc[m, "primary_mdd"] >= base_primary_mdd - 0.02)
        & (leaderboard.loc[m, "proxy_log_growth"] >= base_proxy_growth)
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
        "r6_v1_selective_result": "NOT_PROMOTED",
        "baseline_reconciliation": parity,
        "candidates": list(CANDIDATES),
        "research_survivors": surv["candidate"].tolist() if len(surv) else [],
        "selected_r6_1_candidate": selected,
        "promotion_eligible": selected is not None,
        "live_action": "NONE",
    }

    if not a.dry_run:
        pd.DataFrame(fold_contract).to_csv(out / "r6_1_fold_contract.csv", index=False)
        keep = [
            "timestamp", "target_timestamp_4b", "expected_seq", "symbol", "fold",
            "exec_weight", "fwd_ret_4b", "proxy_ret_4b", "net10_return", "proxy_net_return",
            *CANDIDATES.keys(),
        ]
        scored[keep].to_parquet(out / "r6_1_scored_rows.parquet", index=False)
        ledger.to_parquet(out / "r6_1_trade_ledger.parquet", index=False)
        folds.to_csv(out / "r6_1_fold_summary.csv", index=False)
        paired_folds.to_csv(out / "r6_1_paired_fold_summary.csv", index=False)
        boot.to_csv(out / "r6_1_paired_bootstrap.csv", index=False)
        leaderboard.to_csv(out / "r6_1_leaderboard.csv", index=False)
        (out / "r6_1_selection_decision.json").write_text(
            json.dumps(decision, indent=2, ensure_ascii=False, default=str) + "\n"
        )
        (out / "r6_1_target_contract.json").write_text(
            json.dumps({
                "schema": SCHEMA,
                "research_cutoff": RESEARCH_CUTOFF.isoformat(),
                "features": FEATURES,
                "candidates": CANDIDATES,
                "cost": COST,
                "stop": STOP,
                "take": TAKE,
                "horizon_buckets": 4,
                "same_bar_stop_take_rule": "STOP_FIRST_CONSERVATIVE",
                "model": {
                    "class": "HistGradientBoostingRegressor",
                    "learning_rate": 0.05,
                    "max_iter": 100,
                    "max_leaf_nodes": 15,
                    "min_samples_leaf": 100,
                    "l2_regularization": 1.0,
                    "random_state": 42,
                },
            }, indent=2, ensure_ascii=False) + "\n"
        )
        sources = [
            r291 / "r2_9_1_model_contract.csv",
            r5_leaderboard,
            canon_qqq,
        ]
        (out / "r6_1_manifest.json").write_text(
            json.dumps({
                "schema": SCHEMA,
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "research_only": True,
                "sources": {str(p): sha256_file(p) for p in sources if p.exists()},
            }, indent=2, ensure_ascii=False) + "\n"
        )

    checkpoint(
        exec_log, "SUCCESS",
        baseline_reconciliation=parity,
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
