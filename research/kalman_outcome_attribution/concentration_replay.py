"""Frozen discovery-gate concentration and leave-group-out cash sensitivity.

The original cash simulator is called from scratch for every omission.
The resulting comparisons are retrospective, not independent validation.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
from outcome_profile import ARCHIVES, ASOF, KEY, load_archive, load_original
from regime_cash_replay import CORE, HIGH_RISK, candidates, masks

SEMI = {"AVGO", "AMD", "NVDA", "MU"}
EXPECTED_EPISODES = [
    ("2025-03-11", "2025-03-24", 10),
    ("2025-03-27", "2025-05-12", 32),
    ("2026-03-23", "2026-04-08", 12),
    ("2026-11-20", "2026-11-23", 2),
]


def bear_episodes(state, sessions):
    # This is the original lagged long-SMA state, not the separate +/-2% momentum rule.
    bear = state.bull.reindex(sessions).eq(False).fillna(False)
    ids = bear.ne(bear.shift(1)).cumsum()
    return [(g.index[0], g.index[-1], len(g))
            for _,g in bear.loc[bear].groupby(ids.loc[bear])]


def summarize(curve, fills):
    if curve.active_positions.iloc[-1] != 0 or (curve.cash < -1e-6).any():
        raise ValueError("CASH_OR_UNCLOSED_POSITION")
    pnl = float(fills.net_pnl.sum()) if len(fills) else 0.
    if abs(pnl - float(curve.equity.iloc[-1]-100000.)) >= 1e-6:
        raise ValueError("CASH_PNL_CONSERVATION_MISMATCH")
    return {"total_return":float(curve.equity.iloc[-1]/100000.-1),
            "max_close_drawdown":float(curve.drawdown.min()),
            "fills":len(fills),"pnl":pnl,
            "average_exposure":float(curve.gross_exposure.mean()),
            "win_rate":float(fills.realized_return.gt(0).mean()) if len(fills) else None,
            "severe_losses":int(fills.realized_return.le(-.05).sum()) if len(fills) else 0}


def contribution(fills, field):
    result={}
    for k,g in fills.groupby(field):
        result[str(k)]={"fills":len(g),"pnl":float(g.net_pnl.sum()),
            "win_rate":float(g.realized_return.gt(0).mean()),
            "severe_losses":int(g.realized_return.le(-.05).sum())}
    return result


def positive_concentration(by_symbol):
    # Positive symbol-level net PnL is the denominator, not total net PnL.
    gains=np.array([max(0.,v["pnl"]) for v in by_symbol.values()])
    if gains.sum() <= 0:
        return {"top3_positive_symbol_pnl_share":None,"positive_symbol_pnl_hhi":None}
    weights=gains/gains.sum()
    return {"top3_positive_symbol_pnl_share":float(np.sort(weights)[-3:].sum()),
            "positive_symbol_pnl_hhi":float((weights**2).sum())}


def cohort_report(frame, event_map, prices, sessions, episodes, portfolio, cohort):
    def execute(f, cap=5, cost=20):
        events=[event_map[(r.family,*(getattr(r,k) for k in KEY))]
                for r in f.itertuples(index=False)]
        curve, fills, _=portfolio.simulate(events,prices,sessions,strategy="DISCOVERY_GATES",
            cohort=cohort,max_positions=cap,allocation=1./cap,round_trip_cost_bps=cost)
        if not len(fills):
            raise ValueError("EMPTY_STRESS_COHORT")
        # Restore signal family by exact event identity, not by realized outcome.
        fkey=f[KEY+["family"]].copy()
        if fkey.duplicated(KEY).any():
            raise ValueError("AMBIGUOUS_DISCOVERY_EVENT")
        fills=fills.copy()
        for k in KEY[1:]:
            fills[k]=pd.to_datetime(fills[k])
        fills=fills.merge(fkey,on=KEY,validate="one_to_one",how="left")
        if fills.family.isna().any():
            raise ValueError("MISSING_FILL_FAMILY")
        return curve,fills,summarize(curve,fills)

    curve,fills,base=execute(frame)
    def omit(mask, cap=5, cost=20):
        _,_,r=execute(frame.loc[~mask],cap,cost)
        return {"removed_candidates":int(mask.sum()),**r}

    by_symbol=contribution(fills,"symbol")
    by_family=contribution(fills,"family")
    if abs(sum(x["pnl"] for x in by_symbol.values())-base["pnl"])>=1e-6:
        raise ValueError("ATTRIBUTION_CONSERVATION_MISMATCH")
    top=max(by_symbol,key=lambda s:by_symbol[s]["pnl"])
    ep_out={}
    for start,end,n in episodes:
        m=frame.family.eq("BEAR_LOGISTIC")&frame.signal_date.between(start,end)
        q=fills.loc[fills.family.eq("BEAR_LOGISTIC")&fills.signal_date.between(start,end)]
        ep_out[f"{start.date()}_{end.date()}"]={
            "sessions":n,"candidates":int(m.sum()),"fills":len(q),"pnl":float(q.net_pnl.sum()),
            "omission_replay":omit(m)}
    start,end,_=max(episodes,key=lambda x:x[2])
    longest=frame.family.eq("BEAR_LOGISTIC")&frame.signal_date.between(start,end)
    semi=frame.symbol.isin(SEMI)
    stress=[]
    for cap in (3,5):
        for cost in (20,40):
            for name,mask in [
                ("BASE",pd.Series(False,index=frame.index)),
                ("NO_LONGEST_BEAR",longest),("NO_SEMI",semi),
                ("NO_SEMI_LONGEST_BEAR",semi|longest),
                ("NO_BEAR",frame.family.eq("BEAR_LOGISTIC")),
                ("SEMI_ONLY",~semi),
            ]:
                stress.append({"name":name,"cap":cap,"cost_bp":cost,**omit(mask,cap,cost)})
    return {"baseline":base,"pnl_by_symbol":by_symbol,"pnl_by_family":by_family,
            **positive_concentration(by_symbol),
            "top_positive_symbol":top,
            "leave_one_symbol_out":{s:omit(frame.symbol.eq(s)) for s in sorted(frame.symbol.unique())},
            "leave_one_signal_year_out":{str(y):omit(frame.signal_date.dt.year.eq(y)) for y in (2024,2025,2026)},
            "leave_one_family_out":{f:omit(frame.family.eq(f)) for f in sorted(frame.family.unique())},
            "bear_episode_contributions_and_replays":ep_out,
            "omit_top_symbol_and_longest_bear":omit(frame.symbol.eq(top)|longest),
            "sector_and_episode_stress":stress}


def run(raw,result,train):
    import portfolio
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for name,blob in raw.items():
            dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(blob)
        market=root/"market"
        prices={s:train.load_bars(train.market_file(market,s))[["open","close"]]
                for s in CORE+["^VIX","GLD"]}
        frame,event_map=candidates(result,prices,portfolio)
        chosen=frame.loc[masks(frame)["DISCOVERY_GATES"]]
        sessions=portfolio.validate_sessions(prices)
        if len(sessions)!=727 or str(sessions[-1].date())!=ASOF:
            raise ValueError("FROZEN_SESSION_COVERAGE")
        episodes=bear_episodes(portfolio.market_state(prices),sessions)
        actual=[(str(s.date()),str(e.date()),n) for s,e,n in episodes]
        if actual!=EXPECTED_EPISODES:
            raise ValueError("FROZEN_EPISODE_MISMATCH")
        reports={}
        for cohort,excluded,expected in [
            ("ALL_20",set(),.45347741702817435),
            ("EXCLUDE_HIGH_RISK",HIGH_RISK,.4407499250710578),
        ]:
            reports[cohort]=cohort_report(chosen.loc[~chosen.symbol.isin(excluded)],event_map,
                                         prices,sessions,episodes,portfolio,cohort)
            if abs(reports[cohort]["baseline"]["total_return"]-expected)>1e-8:
                raise ValueError("CONCENTRATION_BASELINE_MISMATCH")
    return {"schema":"kalman-concentration-replay-v1","asof":ASOF,
            "input_sha256":{k:v[2] for k,v in ARCHIVES.items()},
            "research_only":True,"approved_live":False,"production_writes":False,
            "new_holdout":False,"source_finality_certified":False,
            "portfolio_resimulated":True,"episodes":actual,"cohorts":reports,
            "limitations":[
                "Fixed, previously inspected discovery gates and candidate streams.",
                "Each omission re-runs cash sizing and fills; attributed PnL is not equal to the omission effect.",
                "Positive symbol PnL concentration uses positive symbol-level net PnL as its denominator.",
                "Sector group is four fixed semiconductor names, not a comprehensive sector universe.",
                "Year and episode omissions exclude signal dates, including cross-boundary exits.",
                "Few executed bear episodes, no independent holdout, no parameter selection or live promotion.",
            ]}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("data","results","original-source","out"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args()
    report=run(load_archive(a.data,"data"),load_archive(a.results,"results"),load_original(a.original_source))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print("CONCENTRATION_REPLAY_RESEARCH_ONLY",len(report["cohorts"]),len(report["episodes"]))
