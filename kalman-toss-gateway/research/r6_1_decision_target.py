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

SCHEMA = "kalman-r6-1-decision-target-v3"
COST = 0.001
STOP = -0.03
TAKE = 0.20
MIN_UNIVERSE = 80
BLOCK_DAYS = 5
B_DEFAULT = 2000
RNG_SEED = 20260922
PATH_COVERAGE_MIN = 0.99\nEXPECTED_SCORED_ROWS = 497504

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


def add_path_proxy(df):
    if df.duplicated(["symbol", "expected_seq"]).any():
        raise RuntimeError("duplicate symbol/expected_seq in frozen scored rows")

    out = df.copy()
    for k in [1, 2, 3, 4]:
        fut = out[["symbol", "expected_seq", "high", "low"]].copy()
        fut["expected_seq"] = fut["expected_seq"] - k
        fut = fut.rename(columns={"high": f"high_p{k}", "low": f"low_p{k}"})
        out = out.merge(fut, on=["symbol", "expected_seq"], how="left", validate="one_to_one")

    complete_cols = [f"{x}_p{k}" for k in [1, 2, 3, 4] for x in ["high", "low"]]
    out["path_complete"] = out[complete_cols].notna().all(axis=1)

    c = pd.to_numeric(out["close"], errors="coerce").to_numpy(float)
    proxy = pd.to_numeric(out["fwd_ret_4b"], errors="coerce").to_numpy(float)
    active = out["path_complete"].to_numpy(bool) & np.isfinite(c) & np.isfinite(proxy)

    for k in [1, 2, 3, 4]:
        hi = pd.to_numeric(out[f"high_p{k}"], errors="coerce").to_numpy(float)
        lo = pd.to_numeric(out[f"low_p{k}"], errors="coerce").to_numpy(float)
        stop_touch = active & ((lo / c - 1.0) <= STOP)
        take_touch = active & ((hi / c - 1.0) >= TAKE)

        # Conservative same-bar ambiguity rule: stop wins.
        stop_first = stop_touch
        take_only = take_touch & ~stop_touch

        proxy[stop_first] = STOP
        proxy[take_only] = TAKE
        active[stop_first | take_only] = False

    proxy[~out["path_complete"].to_numpy(bool)] = np.nan
    out["proxy_ret_4b"] = proxy
    return out


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

    scored = add_path_proxy(scored)

    ratio = scored["universe_median_rv24"] / scored["rv_24"].replace(0, np.nan)
    scored["exec_weight"] = ratio.clip(0.25, 1.0).fillna(1.0)
    scored["net10_return"] = scored["exec_weight"] * scored["fwd_ret_4b"] - scored["exec_weight"] * COST
    scored["proxy_net_return"] = scored["exec_weight"] * scored["proxy_ret_4b"] - scored["exec_weight"] * COST

    scored["target_net"] = scored["net10_return"]
    scored["target_ordinal_net"] = (
        scored.groupby("timestamp")["target_net"].rank(pct=True, method="average") - 0.5
    )
    scored["target_path_relative"] = (
        scored["proxy_net_return"]
        - scored.groupby("timestamp")["proxy_net_return"].transform("median")
    )

    overall_path_coverage = float(scored["path_complete"].mean())
    checkpoint(
        exec_log,
        "FROZEN_ROWS_READY",
        rows=len(scored),
        symbols=int(scored["symbol"].nunique()),
        path_coverage=overall_path_coverage,
    )
    if overall_path_coverage < PATH_COVERAGE_MIN:
        raise RuntimeError(
            f"path coverage too low: {overall_path_coverage:.6f} < {PATH_COVERAGE_MIN:.6f}"
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

        tr = scored.loc[scored["target_timestamp_4b"] < start].copy()
        te = scored.loc[(scored["timestamp"] >= start) & (scored["timestamp"] < end)].copy()

        valid_ts = te.groupby("timestamp")["symbol"].nunique()
        valid_ts = set(valid_ts[valid_ts >= MIN_UNIVERSE].index)
        te = te.loc[te["timestamp"].isin(valid_ts)].copy()
        te["eval_fold"] = fold

        if len(tr) == 0 or len(te) == 0:
            raise RuntimeError(f"empty fold {fold}: train={len(tr)} test={len(te)}")

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
            "train_path_target_rows": int(tr["target_path_relative"].notna().sum()),
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
        "source_contract": "frozen r5_0_1_scored_rows; E1 warm-up; E2-E8 paired common OOS",
        "baseline_reconciliation": baseline_reconciliation,
        "overall_path_coverage": overall_path_coverage,
        "baseline_proxy_coverage": base_proxy_coverage,
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
            "source": "frozen r5_0_1_scored_rows.parquet (497,504 OOS rows)",
            "training_protocol": "E1 warm-up; E2-E8 expanding common-OOS evaluation",
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
