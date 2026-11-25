"""Frozen Daily20 outcome attribution, not model training or a trading rule.

Run with the original source checkout and the two independently pinned archives.
Only aggregate diagnostics leave the runner; no row-level features or prices.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import zipfile

import numpy as np
import pandas as pd

SOURCE_SHA = "06c66c0fea6de93eeb581ce856d648d24c0ff942"
RUN_ID = "45382109010"
ASOF = "2026-11-23"
ARCHIVES = {
    "data": ("1hH1qe7Ino8IOS7DEmEkeY_RpHxrdmx2p",
             "daily20_data_first_capture_2026-11-23_GH45382109010.zip",
             "e8fe9d37e3db3037280878adf63bd0e0e51dd2ca3ca71ebb2dfbdefe86897711",
             9344964, 52),
    "results": ("1ExY3SRG5UzLFSd9_j4i9vqntmKf1yLYQ",
                "daily20_results_first_capture_2026-11-23_GH45382109010.zip",
                "256467e4ed8d3979c1f8c28993f9aed1fb7f4f16135879d1809b870456c8622f",
                13130442, 135),
}
FEATURES = (
    "ret1", "ret5", "ret20", "sma20_gap", "sma50_gap", "sma200_gap",
    "volume_z20", "rsi14", "macd_hist", "adx14", "natr14", "roc10",
    "bb_pctb", "spy_mom5_lag", "spy_above200_lag", "qqq_mom5_lag",
    "smh_relative_lag", "credit_mom5_lag", "vix_lag", "tlt_mom5_lag",
    "gld_mom5_lag",
)
DIAGNOSTICS = ("vol20", "relative20_spy")
KEY = ["symbol", "signal_date", "entry_date", "exit_date"]
FAMILIES = {
    "BULL_LOGISTIC": ("LOGISTIC", 439),
    "BULL_TREND": ("TREND_RULE", 1061),
    "BEAR_LOGISTIC": ("BEAR_LOGISTIC_ONLY", 89),
    "BEAR_RULE": ("BEAR_RULE_ONLY", 152),
}
COSTS = (20, 40)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verified_members(blob, *, expected_sha, expected_count):
    if sha(blob) != expected_sha:
        raise ValueError("ARCHIVE_SHA256_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = z.namelist()
        if (len(names) != len(set(names)) or
                sum(x.file_size for x in z.infolist()) > 200 * 1024 * 1024 or
                any(not n or n.startswith("/") or "\\" in n or ".." in PurePosixPath(n).parts
                    for n in names)):
            raise ValueError("UNSAFE_ARCHIVE")
        m = json.loads(z.read("drive_manifest.json"))
        hashes = m["payload_hashes_sha256"]
        if (m.get("format") != "kalman-daily20-drive-v1" or
                m.get("research_only") is not True or m.get("production_writes") is not False or
                m.get("source_sha") != SOURCE_SHA or m.get("source_actions_run_id") != RUN_ID or
                m.get("data_expected_last_closed_xnys") != ASOF or
                m.get("source_finality_status") != "SOURCE_FINALITY_HOLD"):
            raise ValueError("ARCHIVE_LINEAGE_OR_SCOPE_MISMATCH")
        if len(hashes) != expected_count or set(hashes) != set(names) - {"drive_manifest.json"}:
            raise ValueError("ARCHIVE_MEMBER_SET_MISMATCH")
        payload = {n: z.read(n) for n in hashes}
        if any(sha(payload[n]) != h for n, h in hashes.items()):
            raise ValueError("ARCHIVE_MEMBER_HASH_MISMATCH")
    return payload


def load_archive(path, kind):
    _, _, expected, size, count = ARCHIVES[kind]
    blob = Path(path).read_bytes()
    if len(blob) != size:
        raise ValueError("ARCHIVE_SIZE_MISMATCH")
    return verified_members(blob, expected_sha=expected, expected_count=count)


def csv(payload, name):
    return pd.read_csv(io.BytesIO(payload[name]))


def normalize_keys(frame):
    frame = frame.copy()
    for name in KEY[1:]:
        frame[name] = pd.to_datetime(frame[name], format="%Y-%m-%d", errors="raise")
        if frame[name].isna().any():
            raise ValueError("MISSING_EVENT_DATE")
    if not (frame.signal_date.lt(frame.entry_date) & frame.entry_date.lt(frame.exit_date)
            & frame.exit_date.le(pd.Timestamp(ASOF))).all():
        raise ValueError("INVALID_EVENT_SEQUENCE")
    return frame


def trailing_diagnostics(close, spy):
    """Additional close-known diagnostics, not original model predictors."""
    return pd.DataFrame({
        "vol20": close.pct_change(fill_method=None).rolling(20, min_periods=20).std(),
        "relative20_spy": (close/spy).pct_change(20, fill_method=None),
    }).reindex(close.index).replace([np.inf,-np.inf],np.nan)


def join_signal_features(events, feature_frames):
    """Strict same-symbol signal-date lookup; future columns never enter predictors."""
    events = normalize_keys(events)
    if events.duplicated(["family", *KEY]).any():
        raise ValueError("DUPLICATE_CANDIDATE_KEY")
    joined = []
    for symbol, group in events.groupby("symbol", sort=True):
        frame = feature_frames[symbol]
        if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
            raise ValueError("FEATURE_INDEX_INVALID")
        if not group.signal_date.isin(frame.index).all():
            raise ValueError("MISSING_SIGNAL_FEATURE_ROW")
        selected = frame.loc[group.signal_date]
        for name in ("entry_date", "exit_date"):
            if not np.array_equal(pd.to_datetime(selected[name]).to_numpy(), group[name].to_numpy()):
                raise ValueError("ARCHIVED_HORIZON_MISMATCH")
        for name in ("gross_return", "net_return"):
            if not np.allclose(selected[name].to_numpy(float), group[name].to_numpy(float),
                               rtol=0, atol=2e-6, equal_nan=False):
                raise ValueError("ARCHIVED_LABEL_MISMATCH")
        x = selected.loc[:, [*FEATURES, *DIAGNOSTICS]].reset_index(drop=True)
        if set(x.columns) != set(FEATURES + DIAGNOSTICS):
            raise ValueError("FEATURE_SCHEMA_MISMATCH")
        joined.append(pd.concat([group.reset_index(drop=True), x], axis=1))
    out = pd.concat(joined, ignore_index=True)
    if len(out) != len(events):
        raise ValueError("JOIN_COUNT_MISMATCH")
    out["year"] = out.signal_date.dt.year
    return out


def classify(returns):
    r = pd.to_numeric(returns, errors="raise")
    if not np.isfinite(r).all():
        raise ValueError("NONFINITE_RETURN")
    return pd.Series(np.select([r.le(-.10), r.le(-.05), r.lt(0), r.eq(0)],
                               ["EXTREME_LOSS", "SEVERE_LOSS", "MILD_LOSS", "BREAKEVEN"],
                               default="WIN"), index=r.index)


def summarize(frame, return_col):
    r = frame[return_col]
    labels = classify(r)
    n = len(r)
    pnl = frame.get("net_pnl")
    loss_pnl = float(pnl[r.lt(0)].sum()) if pnl is not None else None
    severe_pnl = float(pnl[r.le(-.05)].sum()) if pnl is not None else None
    return {
        "n": n, "signal_dates": int(frame.signal_date.nunique()),
        "wins": int(r.gt(0).sum()), "losses": int(r.lt(0).sum()),
        "breakeven": int(r.eq(0).sum()),
        "severe_loss_ge_5pct": int(r.le(-.05).sum()),
        "extreme_loss_ge_10pct": int(r.le(-.10).sum()),
        "win_rate": float(r.gt(0).mean()) if n else None,
        "mean_return": float(r.mean()) if n else None,
        "median_return": float(r.median()) if n else None,
        "mean_win": float(r[r.gt(0)].mean()) if r.gt(0).any() else None,
        "mean_loss": float(r[r.lt(0)].mean()) if r.lt(0).any() else None,
        "loss_pnl": loss_pnl, "severe_loss_pnl": severe_pnl,
        "severe_share_of_total_loss_pnl": severe_pnl / loss_pnl if loss_pnl else None,
        "outcome_counts": {str(k): int(v) for k, v in labels.value_counts().items()},
    }


def distribution(x):
    x = pd.to_numeric(x, errors="raise").replace([np.inf, -np.inf], np.nan).dropna()
    return {"n": len(x), "median": float(x.median()) if len(x) else None,
            "q25": float(x.quantile(.25)) if len(x) else None,
            "q75": float(x.quantile(.75)) if len(x) else None}


def rank_auc(x, target):
    valid = x.notna() & target.notna() & np.isfinite(x)
    x, y = x[valid], target[valid].astype(bool)
    n1, n0 = int(y.sum()), int((~y).sum())
    if not n1 or not n0:
        return None, 0
    value = (x.rank(method="average")[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
    return float(value), n1 * n0


def stratified_auc(frame, feature, target, strata):
    weighted, pairs, groups = 0., 0, 0
    for _, g in frame.groupby(strata, dropna=False):
        value, count = rank_auc(g[feature], target.loc[g.index])
        if count:
            weighted += value * count
            pairs += count
            groups += 1
    return {"auc": weighted / pairs if pairs else None,
            "strata_with_both_outcomes": groups, "rank_pairs": pairs}


def profile(frame, return_col):
    # No imputation. Missing values reported explicitly; no inference or p-values.
    frame = frame.reset_index(drop=True)
    r = frame[return_col]
    rows = []
    comparisons = (
        ("WIN_VS_LOSS", r.gt(0), r.lt(0)),
        ("SEVERE_VS_MILD_LOSS", r.le(-.05), r.lt(0) & r.gt(-.05)),
    )
    for feature in [*FEATURES, *DIAGNOSTICS, "probability"]:
        x = frame[feature].replace([np.inf, -np.inf], np.nan)
        for name, positive, negative in comparisons:
            subset = frame.loc[positive | negative].copy()
            target = positive.loc[subset.index]
            a, b = x[positive].dropna(), x[negative].dropna()
            pooled = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2) if len(a)>1 and len(b)>1 else np.nan
            auc, pairs = rank_auc(x.loc[subset.index], target)
            rows.append({
                "feature": feature, "comparison": name,
                "positive": distribution(a), "negative": distribution(b),
                "positive_missing": int(positive.sum() - len(a)),
                "negative_missing": int(negative.sum() - len(b)),
                "standardized_mean_difference": float((a.mean()-b.mean())/pooled)
                    if np.isfinite(pooled) and pooled>0 else None,
                "rank_auc": auc, "rank_pairs": pairs,
                "within_symbol": stratified_auc(subset, feature, target, ["symbol"]),
                "within_symbol_year": stratified_auc(subset, feature, target, ["symbol", "year"]),
            })
    return rows


def calibration(frame, return_col):
    x = frame.loc[frame.probability.notna()]
    if x.empty:
        return {"available": False, "bins": []}
    if not x.probability.between(0, 1).all():
        raise ValueError("INVALID_PROBABILITY")
    bins = []
    for lower, upper in zip((0., .6, .65, .7, .8), (.6, .65, .7, .8, 1.)):
        mask = x.probability.ge(lower) & (x.probability.le(upper) if upper == 1 else x.probability.lt(upper))
        g = x.loc[mask]
        bins.append({"lower": lower, "upper": upper,
                     "mean_score": float(g.probability.mean()) if len(g) else None,
                     **summarize(g, return_col)})
    return {"available": True, "bins": bins,
            "brier_on_selected_trades_only": float(((x.probability-x[return_col].gt(0))**2).mean()),
            "not_full_model_calibration": True}


def match_executions(candidates, executions):
    executions = normalize_keys(executions)
    if executions.duplicated(KEY).any():
        raise ValueError("DUPLICATE_EXECUTION_KEY")
    cols = KEY + ["realized_return", "net_pnl"]
    matched = candidates.merge(executions[cols], on=KEY, how="outer",
                               validate="one_to_one", indicator=True)
    if matched["_merge"].eq("right_only").any():
        raise ValueError("EXECUTION_WITHOUT_CANDIDATE")
    return matched.loc[matched["_merge"].eq("both")].drop(columns="_merge"), matched.loc[
        matched["_merge"].eq("left_only")].drop(columns=["_merge", "net_pnl", "realized_return"])


def build_report(events, result, feature_frames):
    data = join_signal_features(events, feature_frames)
    portfolio = csv(result, "research/portfolio_executions.csv")
    regime = csv(result, "research/regime_challenger/regime_executions.csv")
    rows = []
    for family, (prefix, count) in FAMILIES.items():
        f = data.loc[data.family.eq(family)].copy()
        if len(f) != count:
            raise ValueError("UNEXPECTED_FAMILY_COUNT")
        for cost in COSTS:
            f["nominal_return"] = f.gross_return - cost / 10000.
            ledger = portfolio if family.startswith("BULL") else regime
            name = f"{prefix}__ALL_20__POS5__COST{cost}BP"
            execs = ledger.loc[ledger.scenario.eq(name)]
            if execs.empty:
                raise ValueError("MISSING_EXECUTION_SCENARIO")
            filled, unfilled = match_executions(f, execs)
            for selection, g, ret in (("ALL_CANDIDATES", f, "nominal_return"),
                                      ("FILLED", filled, "realized_return"),
                                      ("NOT_FILLED", unfilled, "nominal_return")):
                stats = summarize(g, ret)
                rows.append({
                    "family": family, "cost_bp": cost, "selection": selection, "metrics": stats,
                    "features": profile(g, ret), "calibration": calibration(g, ret),
                    "by_year": [{"year": int(y), **summarize(v, ret)}
                                for y,v in g.groupby("year")],
                    "by_symbol": [{"symbol": s, **summarize(v, ret)}
                                  for s,v in g.groupby("symbol")],
                })
    return {
        "schema": "kalman-outcome-attribution-v1", "source_commit": SOURCE_SHA,
        "source_run_id": RUN_ID, "asof": ASOF,
        "input_sha256": {k: v[2] for k,v in ARCHIVES.items()},
        "candidate_count": len(data), "model_input_feature_count": len(FEATURES),
        "feature_nonmissing": {k: int(data[k].notna().sum()) for k in FEATURES},
        "supplemental_diagnostics": list(DIAGNOSTICS),
        "diagnostic_nonmissing": {k: int(data[k].notna().sum()) for k in DIAGNOSTICS},
        "groups": rows, "research_only": True, "approved_live": False,
        "new_holdout": False, "independent_price_certification": False,
        "point_in_time_training_ready": False, "production_writes": False,
        "limitations": [
            "Previously inspected historical OOS data; associations are not causal or independent.",
            "Fixed universe, listing/factor provenance and source finality remain HOLD.",
            "NOT_FILLED means absent from the named scenario, not a known rejection reason.",
            "No complete all-session score history; selected-trade calibration only.",
            "Rank pairs and repeated signal dates are not independent statistical observations.",
            "No multiple-testing inference, rule tuning, imputation, or prospective journal change.",
        ],
    }


def load_original(source):
    source = Path(source).resolve()
    got = subprocess.check_output(["git","-C",str(source),"rev-parse","HEAD"], text=True).strip()
    if got != SOURCE_SHA:
        raise ValueError("ORIGINAL_CODE_COMMIT_MISMATCH")
    sys.path.insert(0,str(source/"research/kalman_daily20"))
    import train
    if tuple(train.COLUMNS) != FEATURES or train.HOLD != 4:
        raise ValueError("ORIGINAL_MODEL_SCHEMA_MISMATCH")
    return train


def main():
    p = argparse.ArgumentParser()
    for arg in ("data","results","original-source","out"):
        p.add_argument("--"+arg, required=True)
    a = p.parse_args()
    raw, result = load_archive(a.data,"data"), load_archive(a.results,"results")
    train = load_original(a.original_source)
    bull = csv(result,"research/oos_trades.csv")
    bull["family"] = bull.strategy.map({"LOGISTIC":"BULL_LOGISTIC","TREND_RULE":"BULL_TREND"})
    bear = csv(result,"research/regime_challenger/bear_oos_trades.csv")
    bear["family"] = bear.candidate_family
    events = pd.concat([bull,bear.drop(columns="candidate_family")],ignore_index=True)
    if len(events)!=1741 or set(events.family)!=set(FAMILIES):
        raise ValueError("UNEXPECTED_ARCHIVE_CANDIDATES")
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for name, blob in raw.items():
            dest=root/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(blob)
        context=train.context_frame(root/"market")
        spy=train.load_bars(train.market_file(root/"market","SPY"))["close"]
        frames={}
        for symbol in sorted(set(events.symbol)):
            base=train.feature_frame(symbol,root/"market",root/"features",context,20.)
            close=train.load_bars(train.market_file(root/"market",symbol))["close"]
            frames[symbol]=base.join(trailing_diagnostics(close,spy))
        report=build_report(events,result,frames)
    import sklearn, pyarrow
    report["runtime_versions"]={"python":sys.version.split()[0],"pandas":pd.__version__,
                                "numpy":np.__version__,"scikit_learn":sklearn.__version__,
                                "pyarrow":pyarrow.__version__}
    out=Path(a.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="groups"},allow_nan=False))


if __name__=="__main__":
    main()
