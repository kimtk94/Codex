"""Frozen close-to-close relative-return discovery; no trading or source writes."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SHA = "256467e4ed8d3979c1f8c28993f9aed1fb7f4f16135879d1809b870456c8622f"
ASOF = "2026-11-23"
CORE = "QQQ QLD IWM AAPL MSFT AMZN GOOGL META NVDA AMD AVGO MU TSLA PLTR IONQ COIN MSTR JPM XOM".split()
HIGH_RISK = {"QLD", "COIN", "MSTR", "IONQ"}
SEMI = {"NVDA", "AMD", "AVGO", "MU"}
BASE = ["ret5", "ret20", "rel5", "rel20", "vol20", "gap20", "spy5_lag", "spy20_lag",
        "smh_rel10_lag", "qqq_rel10_lag", "credit5_lag", "gld5_lag", "semi"]
INTER = ["pullback_market", "rel20_market", "semi_strength", "rel20_sector", "vol_market"]
METHODS = ["ZERO", "SYMBOL_PRIOR", "REL20", "NEG_REL5", "ABS_BASE", "REL_BASE", "REL_INTER", "ABS_INTER"]


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def read_inputs(path):
    blob = Path(path).read_bytes()
    if len(blob) != 13130442 or digest(blob) != SHA:
        raise ValueError("FROZEN_SHA_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        manifest = json.loads(z.read("drive_manifest.json"))
        hashes = manifest["payload_hashes_sha256"]
        if (len(hashes) != 135 or len(z.namelist()) != 136
                or set(hashes) != set(z.namelist()) - {"drive_manifest.json"}
                or manifest.get("research_only") is not True
                or manifest.get("production_writes") is not False
                or manifest.get("source_finality_status") != "SOURCE_FINALITY_HOLD"
                or manifest.get("data_expected_last_closed_xnys") != ASOF
                or any(digest(z.read(n)) != v for n, v in hashes.items())):
            raise ValueError("ARCHIVE_SCOPE_OR_HASH_MISMATCH")
        prices = {}
        for s in CORE + ["SPY", "SMH", "HYG", "LQD", "GLD"]:
            f = pd.read_csv(io.BytesIO(z.read("research/factor_lineage/" + s.lower() + ".csv.gz")),
                            compression="gzip")
            x = pd.Series(f.daily20_adjusted_close.to_numpy(float),
                          index=pd.to_datetime(f.session, format="%Y-%m-%d", errors="raise"), name=s)
            if not x.index.is_unique or not x.index.is_monotonic_increasing or not np.isfinite(x).all() or not x.gt(0).all():
                raise ValueError("INVALID_CLOSE_HISTORY")
            prices[s] = x
        trades = pd.read_csv(io.BytesIO(z.read("research/oos_trades.csv")))
        bear = pd.read_csv(io.BytesIO(z.read("research/regime_challenger/bear_oos_trades.csv")))
    return prices, trades, bear


def feature_panel(prices):
    spy = prices["SPY"]
    cal = spy.index
    ctx = pd.DataFrame({
        "spy5_lag": spy.pct_change(5, fill_method=None).shift(1),
        "spy20_lag": spy.pct_change(20, fill_method=None).shift(1),
        "smh_rel10_lag": (prices["SMH"]/spy).pct_change(10, fill_method=None).shift(1),
        "qqq_rel10_lag": (prices["QQQ"]/spy).pct_change(10, fill_method=None).shift(1),
        "credit5_lag": (prices["HYG"]/prices["LQD"]).pct_change(5, fill_method=None).shift(1),
        "gld5_lag": prices["GLD"].pct_change(5, fill_method=None).shift(1),
    })
    ctx["momentum_regime"] = np.select([ctx.spy20_lag > .02, ctx.spy20_lag < -.02],
                                        ["UP", "DOWN"], default="SIDEWAYS")
    ctx["sector_regime"] = np.where(ctx.smh_rel10_lag >= 0, "SMH_LEADS", "SMH_LAGS")
    fs = []
    for s in CORE:
        c = prices[s].reindex(cal)
        relative = c/spy
        f = pd.DataFrame({
            "ret5": c.pct_change(5, fill_method=None),
            "ret20": c.pct_change(20, fill_method=None),
            "rel5": relative.pct_change(5, fill_method=None),
            "rel20": relative.pct_change(20, fill_method=None),
            "vol20": c.pct_change(fill_method=None).rolling(20, min_periods=20).std(),
            "gap20": c/c.rolling(20, min_periods=20).mean()-1,
            "abs_return": c.shift(-4)/c-1,
            "relative_return": relative.shift(-4)/relative-1,
            "exit_date": pd.Series(cal, index=cal).shift(-4),
        }).join(ctx)
        f["symbol"] = s
        f["semi"] = int(s in SEMI)
        f["signal_date"] = cal
        f["pullback_market"] = f.ret5*f.spy5_lag
        f["rel20_market"] = f.rel20*f.spy20_lag
        f["semi_strength"] = f.semi*f.smh_rel10_lag
        f["rel20_sector"] = f.rel20*f.smh_rel10_lag
        f["vol_market"] = f.vol20*f.spy20_lag.abs()
        fs.append(f)
    p = pd.concat(fs, ignore_index=True)
    p = p.loc[p.signal_date.ge("2022-01-03") & p.exit_date.notna()].copy()
    p = p.loc[np.isfinite(p[BASE+INTER+["abs_return", "relative_return"]]).all(axis=1)].copy()
    p["year"] = p.signal_date.dt.year
    if p.duplicated(["signal_date", "symbol"]).any():
        raise ValueError("DUPLICATE_PANEL_KEY")
    return p, cal


def split(p, cal, year):
    start = cal[cal >= pd.Timestamp(year, 1, 1)][0]
    cutoff = cal[cal.get_loc(start)-4]
    return p.loc[p.exit_date.lt(cutoff)].copy(), p.loc[p.year.eq(year)].copy(), cutoff


def fit_predict(tr, te, cols, target):
    pipeline = make_pipeline(ColumnTransformer([
        ("numeric", StandardScaler(), cols),
        ("symbol", OneHotEncoder(handle_unknown="ignore"), ["symbol"]),
    ]), Ridge(alpha=20., solver="lsqr"))
    pipeline.fit(tr[cols+["symbol"]], tr[target])
    return pipeline.predict(te[cols+["symbol"]])


def fold(tr, te):
    r = te.copy()
    r["ZERO"] = 0.
    r["SYMBOL_PRIOR"] = r.symbol.map(tr.groupby("symbol").relative_return.mean()).fillna(tr.relative_return.mean())
    r["REL20"] = r.rel20
    r["NEG_REL5"] = -r.rel5
    for m, cols, target in [
        ("ABS_BASE", BASE, "abs_return"), ("REL_BASE", BASE, "relative_return"),
        ("REL_INTER", BASE+INTER, "relative_return"), ("ABS_INTER", BASE+INTER, "abs_return"),
    ]:
        r[m] = fit_predict(tr, r, cols, target)
    return r


def daily_scores(p, methods):
    rows = []
    for dt, g in p.groupby("signal_date", sort=True):
        y = g.relative_return
        rank_y = y.rank()
        n = len(g)
        if n < 6:
            raise ValueError("INSUFFICIENT_CROSS_SECTION")
        for m in methods:
            x = g[m]
            rank_x = x.rank()
            ic = rank_x.corr(rank_y) if rank_x.nunique() > 1 and rank_y.nunique() > 1 else None
            # Equal fractional allocation at tied score boundaries, not alphabetical selection.
            a, b, v = np.zeros(n), np.zeros(n), x.to_numpy()
            for weight, ordered in [(a, np.sort(v)[::-1]), (b, np.sort(v))]:
                remaining = 3.
                for val in dict.fromkeys(ordered):
                    mask = v == val
                    take = min(remaining, int(mask.sum()))
                    weight[mask] = take/mask.sum()
                    remaining -= take
                    if remaining <= 0:
                        break
            rows.append({"date": dt, "year": dt.year, "regime": g.momentum_regime.iloc[0],
                         "method": m, "rank_ic": ic, "spread": float(np.dot(a-b, y)/3.), "n": n})
    return pd.DataFrame(rows)


def metrics(x):
    return {m: {"dates": len(g), "rank_ic_mean": float(g.rank_ic.mean()) if g.rank_ic.notna().any() else None,
                "ic_dates": int(g.rank_ic.notna().sum()), "top3_minus_bottom3_mean": float(g.spread.mean()),
                "positive_spread_rate": float(g.spread.gt(0).mean())} for m, g in x.groupby("method")}


def block_compare(daily, cal):
    q = daily.pivot(index="date", columns="method", values="spread")
    cal = cal[(cal >= q.index.min()) & (cal <= q.index.max())]
    q = q.reindex(cal)
    rng = np.random.default_rng(42)
    res = []
    for block in (5, 20, 60):
        n = len(q)
        starts = rng.integers(0, n, size=(10000, int(np.ceil(n/block))))
        idx = ((starts[:, :, None]+np.arange(block)) % n).reshape(10000, -1)[:, :n]
        rr = {}
        for a, b in [("REL_INTER", "REL_BASE"), ("REL_INTER", "ABS_INTER"), ("REL_INTER", "SYMBOL_PRIOR")]:
            v = (q[a]-q[b]).to_numpy()[idx]
            den = np.isfinite(v).sum(axis=1)
            num = np.nansum(v, axis=1)
            valid = den > 0
            rr[a+"-"+b] = {"valid": int(valid.sum()),
                           "range_2p5_97p5": np.quantile(num[valid]/den[valid], [.025, .975]).tolist()}
        res.append({"block": block, "comparisons": rr})
    return res


def subgroup_results(p):
    out = []
    for (reg, sec, semi), g in p.groupby(["momentum_regime", "sector_regime", "semi"]):
        d = g.groupby("signal_date").relative_return.mean()
        out.append({"momentum_regime": reg, "sector_regime": sec,
                    "group": "SEMICONDUCTOR_4" if semi else "OTHER", "rows": len(g), "dates": len(d),
                    "mean_equal_date_relative": float(d.mean()), "beat_spy_fraction": float(g.relative_return.gt(0).mean())})
    return out


def candidate_outcomes(trades, bear, p):
    a = trades.copy()
    a["family"] = a.strategy.map({"LOGISTIC": "BULL_LOGISTIC", "TREND_RULE": "BULL_TREND"})
    b = bear.copy()
    b["family"] = b.candidate_family
    e = pd.concat([a, b], ignore_index=True)
    e.signal_date = pd.to_datetime(e.signal_date)
    e = e.loc[e.symbol.ne("SPY")]
    q = e.merge(p[["symbol", "signal_date", "momentum_regime", "sector_regime", "semi"]],
                on=["symbol", "signal_date"], how="left", validate="many_to_one")
    if q.momentum_regime.isna().any():
        raise ValueError("CANDIDATE_CONTEXT_JOIN_MISMATCH")
    return [{"family": f, "momentum_regime": reg, "n": len(g), "dates": g.signal_date.nunique(),
             "win_rate": float(g.net_return.gt(0).mean()), "mean_nominal_net": float(g.net_return.mean()),
             "severe_rate": float(g.net_return.le(-.05).mean())} for (f, reg), g in q.groupby(["family", "momentum_regime"])]


def run(path):
    prices, trades, bear = read_inputs(path)
    p, cal = feature_panel(prices)
    output = {}
    for name, universe in [("OTHER_15", set(CORE)-HIGH_RISK), ("ALL_19", set(CORE))]:
        f = p.loc[p.symbol.isin(universe)]
        parts, folds = [], []
        for y in (2024, 2025, 2026):
            tr, te, cut = split(f, cal, y)
            r = fold(tr, te)
            parts.append(r)
            folds.append({"year": y, "train_rows": len(tr), "test_rows": len(te),
                          "test_dates": te.signal_date.nunique(), "cutoff": str(cut.date())})
        pred = pd.concat(parts, ignore_index=True)
        if len(pred) != pred.signal_date.nunique()*len(universe):
            raise ValueError("UNBALANCED_EVALUATION_PANEL")
        ds = daily_scores(pred, METHODS)
        output[name] = {"rows": len(pred), "dates": pred.signal_date.nunique(), "folds": folds,
                        "metrics": metrics(ds),
                        "annual": {str(y): metrics(g) for y, g in ds.groupby("year")},
                        "regime": {k: metrics(g) for k, g in ds.groupby("regime")},
                        "sector_groups": subgroup_results(pred), "bootstrap": block_compare(ds, cal)}
    return {"schema": "kalman-market-relative-discovery-v1", "input_sha256": SHA, "asof": ASOF,
            "research_only": True, "approved_live": False, "new_holdout": False,
            "production_writes": False, "portfolio_resimulated": False,
            "target": "ratio of adjusted close returns, signal close to fourth subsequent close relative to SPY; diagnostic, not execution",
            "train_start": "2022-01-03",
            "regime": "prior session SPY 20-session return >2%, <-2%, otherwise sideways; not original BULL/BEAR gate",
            "sector": "four semiconductor stocks; lagged SMH/SPY 10-session relative return; no full sector coverage",
            "cohorts": output, "archived_candidates_by_momentum_regime": candidate_outcomes(trades, bear, p),
            "limitations": [
                "Fixed historical universe and adjusted-price lineage not independently PIT-certified.",
                "Close-to-close excess return is not next-open trade PnL or realizable ranking spread.",
                "Inspected years and overlapping labels; resampling descriptive only.",
                "Primary OTHER_15 excludes fixed shadow-only four as sensitivity; ALL_19 includes unresolved historical IONQ lineage.",
                "No tuning, new policy, strategy approval or live change.",
            ]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    result = run(a.results)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print("RELATIVE_RESEARCH_ONLY", [(k, v["rows"], v["dates"]) for k, v in result["cohorts"].items()])
