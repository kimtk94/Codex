from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone

SCHEMA = "kalman-r8-1-sec-corporate-event-v1"
COST = 0.001
MIN_UNIVERSE = 80
BLOCK_DAYS = 5
B_DEFAULT = 2000
RNG_SEED = 20260923
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

BASE_FEATURES = [
    "cs_ret_1b", "cs_ret_2b", "cs_ret_4b", "cs_ret_6b",
    "cs_rv_6", "cs_rv_24", "cs_ma_dist_6", "cs_ma_dist_24",
    "cs_volume_z_24", "cs_bar_range", "cs_beta24", "cs_residual_ret_6b",
    "qqq_ret_2b", "qqq_ret_6b", "qqq_rv_24", "qqq_ma_dist_24",
    "ix_trend_qqq", "ix_vol_qqq", "ix_ret1_qqq", "ix_mom6_qqq",
]
SEC_FEATURES = [
    "sec_any_decay_48h",
    "sec_event_count_120h_log1p",
    "sec_earnings_results_decay_48h",
    "sec_material_agreement_decay_48h",
    "sec_acquisition_disposition_decay_48h",
    "sec_financing_obligation_decay_48h",
    "sec_restructuring_impairment_decay_48h",
    "sec_management_board_decay_48h",
    "sec_reg_fd_decay_48h",
    "sec_other_event_decay_48h",
    "sec_delisting_compliance_decay_48h",
]
FEATURES = BASE_FEATURES + SEC_FEATURES

CONTROL = "R5C0_HGB_REFERENCE"
CHALLENGER = "R8C1_SEC_CORPORATE_EVENT"

SEC_BUCKET_FEATURE = {
    "EARNINGS_RESULTS": "sec_earnings_results_decay_48h",
    "MATERIAL_AGREEMENT": "sec_material_agreement_decay_48h",
    "ACQUISITION_DISPOSITION": "sec_acquisition_disposition_decay_48h",
    "FINANCING_OBLIGATION": "sec_financing_obligation_decay_48h",
    "RESTRUCTURING_IMPAIRMENT": "sec_restructuring_impairment_decay_48h",
    "MANAGEMENT_BOARD": "sec_management_board_decay_48h",
    "REG_FD": "sec_reg_fd_decay_48h",
    "OTHER_EVENT": "sec_other_event_decay_48h",
    "DELISTING_COMPLIANCE": "sec_delisting_compliance_decay_48h",
}
SEC_HALF_LIFE_HOURS = 48.0
SEC_MAX_AGE_HOURS = 120.0

SCORED_COLUMNS = list(dict.fromkeys([
    "expected_seq", "timestamp", "fwd_ret_4b", "target_timestamp_4b",
    "symbol", "fold", "relative_ret_4b", "rv_24", "universe_median_rv24",
    CONTROL, *BASE_FEATURES,
]))


def parse_args():
    p = argparse.ArgumentParser()
    root = Path(os.getenv("KALMAN_DATA_ROOT", "/mnt/gdrive"))
    p.add_argument("--root", default=str(root))
    p.add_argument("--events", default="/opt/kalman/state/r8_sec/events.json")
    p.add_argument("--sec-manifest", default="/opt/kalman/state/r8_sec/manifest.json")
    p.add_argument("--bootstrap", type=int, default=B_DEFAULT)
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


def profit_factor(r):
    r = np.asarray(r, float)
    pos = r[r > 0].sum()
    neg = -r[r < 0].sum()
    return float(pos / neg) if neg > 0 else np.inf


def metrics(t, ret_col="net10_return"):
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
        "profit_factor": profit_factor(r),
        "mdd": max_dd(r),
    }


def effective_names(symbols, weights):
    t = pd.DataFrame({"symbol": list(symbols), "w": list(weights)}).groupby("symbol")["w"].sum()
    x = t / t.sum()
    return float(1.0 / x.pow(2).sum()), float(x.max())


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


def build_training_rows(root, symbols):
    r1 = root / "US_ETF/directional_research/r1_directional_v1_2/primary_train"
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

    raw = pd.concat(parts, ignore_index=True).sort_values(["symbol", "expected_seq"]).reset_index(drop=True)
    q_ts = _target_timestamp_map(root)
    raw["target_timestamp_4b"] = (raw["expected_seq"] + 4).map(q_ts)

    beta = np.full(len(raw), np.nan, float)
    for _, idxs in raw.groupby("symbol", sort=False).groups.items():
        idx = np.asarray(list(idxs), dtype=int)
        z = raw.loc[idx, ["expected_seq", "ret_1b", "qqq_ret_1b"]].copy()
        lo, hi = int(z["expected_seq"].min()), int(z["expected_seq"].max())
        grid = pd.DataFrame({"expected_seq": np.arange(lo, hi + 1, dtype=np.int64)}).merge(
            z, on="expected_seq", how="left"
        )
        x = pd.to_numeric(grid["ret_1b"], errors="coerce")
        y = pd.to_numeric(grid["qqq_ret_1b"], errors="coerce")
        b = x.rolling(24, min_periods=12).cov(y) / y.rolling(24, min_periods=12).var().replace(0, np.nan)
        beta[idx] = pd.Series(b.to_numpy(), index=grid["expected_seq"]).reindex(z["expected_seq"]).to_numpy(float)

    raw["beta24"] = np.clip(beta, -3, 3)
    raw["residual_ret_6b"] = raw["ret_6b"] - raw["beta24"] * raw["qqq_ret_6b"]

    g = raw.groupby("timestamp")
    for col in [
        "ret_1b", "ret_2b", "ret_4b", "ret_6b", "rv_6", "rv_24",
        "ma_dist_6", "ma_dist_24", "volume_z_24", "bar_range",
        "beta24", "residual_ret_6b",
    ]:
        raw["cs_" + col] = g[col].rank(pct=True, method="average")

    raw["universe_median_rv24"] = g["rv_24"].transform("median")
    raw["ix_trend_qqq"] = raw["ma_dist_24"] * raw["qqq_ma_dist_24"]
    raw["ix_vol_qqq"] = raw["rv_24"] * raw["qqq_rv_24"]
    raw["ix_ret1_qqq"] = raw["ret_1b"] * raw["qqq_ret_2b"]
    raw["ix_mom6_qqq"] = raw["ret_6b"] * raw["qqq_ret_6b"]

    # Frozen R5 target.
    raw["relative_ret_4b"] = raw["fwd_ret_4b"] - g["fwd_ret_4b"].transform("median")

    valid = (
        raw["fwd_ret_4b"].notna()
        & raw["target_timestamp_4b"].notna()
        & (raw["target_timestamp_4b"] < RESEARCH_CUTOFF)
    )
    return raw.loc[valid].reset_index(drop=True)


def reconcile_target(train, frozen):
    m = train[["symbol","expected_seq","relative_ret_4b"]].merge(
        frozen[["symbol","expected_seq","relative_ret_4b"]],
        on=["symbol","expected_seq"], how="inner",
        suffixes=("_train","_frozen"), validate="one_to_one"
    )
    x=pd.to_numeric(m["relative_ret_4b_train"],errors="coerce").to_numpy(float)
    y=pd.to_numeric(m["relative_ret_4b_frozen"],errors="coerce").to_numpy(float)
    ok=np.isfinite(x)&np.isfinite(y)
    d=np.abs(x[ok]-y[ok])
    audit={
        "matched_rows":int(len(m)),
        "both_finite":int(ok.sum()),
        "median_abs_diff":float(np.median(d)) if len(d) else None,
        "max_abs_diff":float(np.max(d)) if len(d) else None,
    }
    audit["pass"]=bool(
        audit["matched_rows"]>5000
        and audit["median_abs_diff"] is not None
        and audit["median_abs_diff"]<=1e-10
    )
    return audit


def reconcile_base_features(train, frozen):
    keys = ["symbol", "expected_seq"]
    m = train[keys + BASE_FEATURES].merge(
        frozen[keys + BASE_FEATURES],
        on=keys, how="inner", suffixes=("_train", "_frozen"), validate="one_to_one"
    )
    all_abs = []
    finite_same = 0
    total = 0
    for f in BASE_FEATURES:
        x = pd.to_numeric(m[f + "_train"], errors="coerce").to_numpy(float)
        y = pd.to_numeric(m[f + "_frozen"], errors="coerce").to_numpy(float)
        fx, fy = np.isfinite(x), np.isfinite(y)
        finite_same += int((fx == fy).sum())
        total += len(x)
        d = np.abs(x[fx & fy] - y[fx & fy])
        if len(d):
            all_abs.append(d)
    vals = np.concatenate(all_abs) if all_abs else np.array([], float)
    audit = {
        "matched_rows": int(len(m)),
        "median_abs_numeric_diff": float(np.median(vals)) if len(vals) else None,
        "finite_state_agreement": float(finite_same / total) if total else None,
    }
    audit["pass"] = (
        audit["matched_rows"] > 5000
        and audit["median_abs_numeric_diff"] is not None
        and audit["median_abs_numeric_diff"] <= 1e-10
        and audit["finite_state_agreement"] >= 0.999
    )
    return audit


def load_sec_events(events_path: Path):
    rows=json.loads(events_path.read_text(encoding="utf-8"))
    out=[]
    for e in rows:
        symbol=str(e.get("symbol") or "").upper()
        accepted=nts(e.get("acceptance_at"))
        if not symbol or pd.isna(accepted):
            continue
        buckets=[
            b for b in (e.get("event_buckets") or [])
            if b in SEC_BUCKET_FEATURE
        ]
        semantic=bool(buckets)
        out.append({
            "symbol":symbol,
            "acceptance_at":accepted,
            "semantic_event":semantic,
            "event_buckets":buckets,
        })
    z=pd.DataFrame(out)
    if z.empty:
        raise RuntimeError("no SEC PIT events available")
    return z.sort_values(["symbol","acceptance_at"]).reset_index(drop=True)


def _decay(age_h):
    age=np.asarray(age_h,float)
    active=(age>=0)&(age<=SEC_MAX_AGE_HOURS)
    out=np.zeros(len(age),float)
    out[active]=np.exp(-math.log(2.0)*age[active]/SEC_HALF_LIFE_HOURS)
    return out


def _latest_decay(signal_times, event_times):
    if len(event_times)==0:
        return np.zeros(len(signal_times),float)
    s=pd.DataFrame({"signal_as_of":signal_times}).sort_values("signal_as_of")
    e=pd.DataFrame({"event_at":pd.to_datetime(event_times,utc=True)}).sort_values("event_at")
    j=pd.merge_asof(
        s,e,left_on="signal_as_of",right_on="event_at",
        direction="backward",allow_exact_matches=True
    )
    age=(j["signal_as_of"]-j["event_at"]).dt.total_seconds()/3600.0
    vals=_decay(age.fillna(1e9).to_numpy(float))
    return pd.Series(vals,index=s.index).sort_index().to_numpy(float)


def _rolling_event_count(signal_times,event_times):
    if len(event_times)==0:
        return np.zeros(len(signal_times),float)
    s=np.asarray(pd.to_datetime(signal_times,utc=True).view("int64"))
    e=np.sort(np.asarray(pd.to_datetime(event_times,utc=True).view("int64")))
    window=int(SEC_MAX_AGE_HOURS*3600*1e9)
    hi=np.searchsorted(e,s,side="right")
    lo=np.searchsorted(e,s-window,side="left")
    return np.log1p(hi-lo).astype(float)


def attach_sec_features(df: pd.DataFrame, events: pd.DataFrame):
    out=df.copy()
    out["signal_as_of"]=nts(out["timestamp"])+pd.to_timedelta(3600,unit="s")
    for f in SEC_FEATURES:
        out[f]=0.0

    event_symbols=set(events["symbol"].unique())
    active_rows=0
    symbols_with_active=set()

    for symbol,idxs in out.groupby("symbol",sort=False).groups.items():
        idx=np.asarray(list(idxs),dtype=int)
        sig=out.loc[idx,"signal_as_of"].reset_index(drop=True)
        ev=events.loc[(events["symbol"]==str(symbol).upper()) & events["semantic_event"]].copy()
        if ev.empty:
            continue

        any_decay=_latest_decay(sig,ev["acceptance_at"])
        counts=_rolling_event_count(sig,ev["acceptance_at"])
        out.loc[idx,"sec_any_decay_48h"]=any_decay
        out.loc[idx,"sec_event_count_120h_log1p"]=counts

        for bucket,col in SEC_BUCKET_FEATURE.items():
            times=[
                r.acceptance_at for r in ev.itertuples()
                if bucket in r.event_buckets
            ]
            if times:
                out.loc[idx,col]=_latest_decay(sig,times)

        active=any_decay>0
        active_rows += int(active.sum())
        if active.any():
            symbols_with_active.add(str(symbol))

    for f in SEC_FEATURES:
        out[f]=pd.to_numeric(out[f],errors="coerce").fillna(0.0)

    audit={
        "rows":int(len(out)),
        "active_rows":active_rows,
        "active_row_ratio":float(active_rows/len(out)) if len(out) else 0.0,
        "symbols_with_any_active_sec":len(symbols_with_active),
        "sec_event_symbols":int(len(event_symbols)),
        "features":SEC_FEATURES,
        "signal_as_of_contract":"timestamp + 60 minutes",
        "half_life_hours":SEC_HALF_LIFE_HOURS,
        "max_age_hours":SEC_MAX_AGE_HOURS,
        "sentiment_used":False,
        "filing_text_used":False,
        "financial_exhibits_only_used":False,
    }
    return out,audit


def simulate(scored, score_col):
    decisions = []
    for tstamp, g0 in scored.groupby("timestamp", sort=True):
        g = g0.dropna(
            subset=[score_col, "fwd_ret_4b", "rv_24", "universe_median_rv24", "target_timestamp_4b"]
        ).copy()
        if len(g) < MIN_UNIVERSE:
            continue
        top = g.sort_values([score_col, "symbol"], ascending=[False, True]).iloc[0]
        ratio = float(top["universe_median_rv24"]) / float(top["rv_24"]) if float(top["rv_24"]) != 0 else np.nan
        weight = float(np.clip(ratio, 0.25, 1.0)) if np.isfinite(ratio) else 1.0
        decisions.append({
            "timestamp": top["timestamp"],
            "target_timestamp_4b": top["target_timestamp_4b"],
            "expected_seq": int(top["expected_seq"]),
            "fold": str(top["eval_fold"]),
            "symbol": str(top["symbol"]),
            "weight": weight,
            "score": float(top[score_col]),
            "net10_return": weight * float(top["fwd_ret_4b"]) - weight * COST,
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
        vals[i] = float(arr[moving_block_indices(len(arr), rng)].mean())

    folds = []
    for fold, g in z.groupby("fold"):
        folds.append({
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
        "folds": folds,
    }


def schedule_audit(base, challenger):
    a = base[["timestamp", "fold"]].drop_duplicates()
    b = challenger[["timestamp", "fold"]].drop_duplicates()
    m = a.merge(b, on=["timestamp", "fold"], how="outer", indicator=True)
    return {
        "base_rows": int(len(a)),
        "challenger_rows": int(len(b)),
        "matched_rows": int((m["_merge"] == "both").sum()),
        "exact_match": bool(len(a) == len(b) and (m["_merge"] == "both").all()),
    }


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    a = parse_args()
    root = Path(a.root)
    us = root / "US_ETF"
    r50 = us / "model_lab_v1/results/r5_0_1_research_sandbox_all_data"
    out = us / "model_lab_v1/results/r8_1_sec_corporate_event"
    out.mkdir(parents=True, exist_ok=True)

    if os.getenv("R8_ALLOW_LIVE", "").lower() == "true":
        raise RuntimeError("R8.1 refuses LIVE mode")

    sec_manifest = json.loads(Path(a.sec_manifest).read_text())
    if sec_manifest.get("schema") != "kalman-r8-sec-corporate-events-v2":
        raise RuntimeError(f"unexpected SEC manifest schema: {sec_manifest.get('schema')}")
    if not sec_manifest.get("sec_event_ready"):
        raise RuntimeError("R8 SEC readiness gate not ready")
    if int(sec_manifest.get("frozen_universe_symbols") or 0) != 93:
        raise RuntimeError("R8 SEC manifest universe drift")

    scored_path = r50 / "r5_0_1_scored_rows.parquet"
    ledger_path = r50 / "r5_0_1_trade_ledger.parquet"
    model_path = r50 / "model_freeze/r5_hgb.joblib"
    scored = pd.read_parquet(scored_path, columns=SCORED_COLUMNS)
    frozen_ledger = pd.read_parquet(ledger_path)
    model_template = joblib.load(model_path)

    scored["timestamp"] = nts(scored["timestamp"])
    scored["target_timestamp_4b"] = nts(scored["target_timestamp_4b"])
    scored = scored.loc[
        scored["target_timestamp_4b"].notna()
        & (scored["target_timestamp_4b"] < RESEARCH_CUTOFF)
    ].copy()
    if len(scored) != EXPECTED_SCORED_ROWS:
        raise RuntimeError(f"expected {EXPECTED_SCORED_ROWS} scored rows, got {len(scored)}")
    if scored["symbol"].nunique() != 93:
        raise RuntimeError(f"expected 93 symbols, got {scored['symbol'].nunique()}")

    symbols = sorted(scored["symbol"].astype(str).unique())
    train_all = build_training_rows(root, symbols)

    base_audit = reconcile_base_features(train_all, scored)
    if not base_audit["pass"]:
        raise RuntimeError(f"base feature reconciliation failed: {base_audit}")
    target_audit = reconcile_target(train_all, scored)
    if not target_audit["pass"]:
        raise RuntimeError(f"relative target reconciliation failed: {target_audit}")

    for fold, start, _ in FOLDS:
        n = int((train_all["target_timestamp_4b"] < ts(start)).sum())
        if n != EXPECTED_TRAIN_ROWS[fold]:
            raise RuntimeError(f"{fold} train rows {n} != frozen {EXPECTED_TRAIN_ROWS[fold]}")

    sec_events = load_sec_events(Path(a.events))
    train_all, train_sec_audit = attach_sec_features(train_all, sec_events)
    scored, scored_sec_audit = attach_sec_features(scored, sec_events)

    if scored["sec_any_decay_48h"].max() <= 0:
        raise RuntimeError("SEC features are entirely inactive in scored rows")

    base = frozen_ledger.loc[
        (frozen_ledger["candidate"] == CONTROL)
        & (frozen_ledger["fold"].astype(str).isin(EVAL_FOLD_NAMES))
    ].copy()
    if base.empty:
        raise RuntimeError("frozen R5 baseline ledger missing")
    base["timestamp"] = nts(base["timestamp"])
    base["target_timestamp_4b"] = nts(base["target_timestamp_4b"])
    base["fold"] = base["fold"].astype(str)

    fold_parts = []
    fold_contract = []
    for fold, ss, ee in EVAL_FOLDS:
        start, end = ts(ss), ts(ee)
        tr = train_all.loc[train_all["target_timestamp_4b"] < start].copy()
        te = scored.loc[
            (scored["fold"].astype(str) == fold)
            & (scored["timestamp"] >= start)
            & (scored["timestamp"] < end)
        ].copy()

        if len(tr) != EXPECTED_TRAIN_ROWS[fold]:
            raise RuntimeError(f"{fold} train count drift: {len(tr)}")

        valid_ts = te.groupby("timestamp")["symbol"].nunique()
        valid_ts = set(valid_ts[valid_ts >= MIN_UNIVERSE].index)
        te = te.loc[te["timestamp"].isin(valid_ts)].copy()
        te["eval_fold"] = fold

        med = tr[FEATURES].median()
        model = clone(model_template)
        model.fit(tr[FEATURES].fillna(med), tr["relative_ret_4b"])
        te[CHALLENGER] = model.predict(te[FEATURES].fillna(med))
        fold_parts.append(te)

        fold_contract.append({
            "fold": fold,
            "train_rows": int(len(tr)),
            "test_rows": int(len(te)),
            "test_timestamps": int(te["timestamp"].nunique()),
            "train_last_target": str(tr["target_timestamp_4b"].max()),
            "active_sec_train_row_ratio": float((tr["sec_any_decay_48h"] > 0).mean()),
            "active_sec_test_row_ratio": float((te["sec_any_decay_48h"] > 0).mean()),
        })

    eval_rows = pd.concat(fold_parts, ignore_index=True)
    challenger = simulate(eval_rows, CHALLENGER)
    challenger["candidate"] = CHALLENGER
    sched = schedule_audit(base, challenger)
    if not sched["exact_match"]:
        raise RuntimeError(f"schedule mismatch vs frozen R5: {sched}")

    base_m = metrics(base)
    chal_m = metrics(challenger)
    base_eff, base_top = effective_names(base["symbol"], base["weight"])
    chal_eff, chal_top = effective_names(challenger["symbol"], challenger["weight"])
    boot = paired_bootstrap(base, challenger, a.bootstrap)
    positive_folds = int(sum(x["paired_log_diff"] > 0 for x in boot["folds"]))

    survivor = bool(
        chal_m["trades"] >= 300
        and chal_m["log_growth"] > base_m["log_growth"]
        and chal_m["profit_factor"] >= base_m["profit_factor"]
        and chal_m["mdd"] >= base_m["mdd"] - 0.02
        and positive_folds >= 5
        and boot["ci95_low"] > 0
        and boot["p_one_sided"] < 0.05
        and chal_eff >= 5
        and chal_top <= 0.35
    )

    leaderboard = pd.DataFrame([
        {
            "candidate": CONTROL,
            **base_m,
            "effective_names": base_eff,
            "top_ticker_share": base_top,
            "research_survivor": False,
        },
        {
            "candidate": CHALLENGER,
            **chal_m,
            "effective_names": chal_eff,
            "top_ticker_share": chal_top,
            "paired_rows": boot["paired_rows"],
            "paired_days": boot["days"],
            "paired_mean_daily_log_diff": boot["obs_mean_daily_paired_log_diff"],
            "ci95_low": boot["ci95_low"],
            "ci95_high": boot["ci95_high"],
            "p_one_sided": boot["p_one_sided"],
            "holm_p": boot["p_one_sided"],  # one challenger only
            "positive_paired_folds": positive_folds,
            "research_survivor": survivor,
        },
    ])

    decision = {
        "schema": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "SUCCESS",
        "research_only": True,
        "production_changed": False,
        "r5_1_untouched": True,
        "candidate": CHALLENGER,
        "candidate_admitted_by_readiness": True,
        "target": "relative_ret_4b = stock fwd_ret_4b - same-timestamp universe median fwd_ret_4b",
        "signal_as_of_contract": "R5 timestamp is 60m bar start; feature cutoff is timestamp + 60m",
        "sec_feature_contract": {
            "features": SEC_FEATURES,
            "event_timestamp": "SEC EDGAR acceptanceDateTime",
            "event_state": "symbol-specific latest semantic 8-K event by bucket",
            "half_life_hours": SEC_HALF_LIFE_HOURS,
            "max_age_hours": SEC_MAX_AGE_HOURS,
            "event_count_feature": "log1p semantic filing count over prior 120 calendar hours",
            "semantic_buckets": list(SEC_BUCKET_FEATURE.keys()),
            "sentiment_used": False,
            "filing_text_used": False,
            "financial_exhibits_only_used": False,
        },
        "readiness": {
            "sec_event_ready": bool(sec_manifest.get("sec_event_ready")),
            "mapped_symbols": sec_manifest.get("mapped_symbols"),
            "event_rows": sec_manifest.get("event_rows"),
            "acceptance_timestamp_ratio": sec_manifest.get("acceptance_timestamp_ratio"),
            "semantic_item_ratio": sec_manifest.get("semantic_item_ratio_excluding_9_01_only"),
        },
        "base_feature_reconciliation": base_audit,
        "target_reconciliation": target_audit,
        "train_sec_audit": train_sec_audit,
        "scored_sec_audit": scored_sec_audit,
        "schedule_audit": sched,
        "baseline": base_m,
        "challenger": chal_m,
        "paired_bootstrap": boot,
        "positive_paired_folds": positive_folds,
        "research_survivor": survivor,
        "promotion_eligible": survivor,
        "live_action": "NONE",
    }

    eval_keep = [
        "timestamp", "target_timestamp_4b", "expected_seq", "symbol", "eval_fold",
        "fwd_ret_4b", "rv_24", "universe_median_rv24",
        CONTROL, CHALLENGER, *SEC_FEATURES,
    ]
    eval_rows[eval_keep].to_parquet(out / "r8_1_scored_rows.parquet", index=False)
    challenger.to_parquet(out / "r8_1_trade_ledger.parquet", index=False)
    leaderboard.to_csv(out / "r8_1_leaderboard.csv", index=False)
    pd.DataFrame(fold_contract).to_csv(out / "r8_1_fold_contract.csv", index=False)
    pd.DataFrame(boot["folds"]).to_csv(out / "r8_1_paired_fold_summary.csv", index=False)
    (out / "r8_1_selection_decision.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=False, default=str) + "\n"
    )
    (out / "r8_1_manifest.json").write_text(
        json.dumps({
            "schema": SCHEMA,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "sources": {
                str(scored_path): sha256_file(scored_path),
                str(ledger_path): sha256_file(ledger_path),
                str(model_path): sha256_file(model_path),
                str(a.events): sha256_file(Path(a.events)),
                str(a.sec_manifest): sha256_file(Path(a.sec_manifest)),
            },
            "research_only": True,
            "production_changed": False,
        }, indent=2) + "\n"
    )

    print(json.dumps(decision, indent=2, default=str))
    print("\nLEADERBOARD")
    print(leaderboard.to_string(index=False))
    print("\nR8_1_COMPLETE")

if __name__ == "__main__":
    main()
