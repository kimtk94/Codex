"""Replay fixed exploratory regime gates on the frozen candidate ledger.

All results use the original cash simulator and actual archived open/close.
No new signals, tuning, trading, writes to Drive, or independent holdout.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
from outcome_profile import ARCHIVES, ASOF, KEY, load_archive, load_original, csv, normalize_keys

HIGH_RISK={"QLD","COIN","MSTR","IONQ"}
CORE="SPY QQQ QLD IWM AAPL MSFT AMZN GOOGL META NVDA AMD AVGO MU TSLA PLTR IONQ COIN MSTR JPM XOM".split()
NAMES=("BULL_LOGISTIC","BULL_TREND","BEAR_LOGISTIC","BULL_PLUS_BEAR",
       "REGIME_SWITCH_CASH","REGIME_SWITCH_BEAR","REGIME_SWITCH_TREND_SIDEWAYS","DISCOVERY_GATES",
       "REGIME_SWITCH_AVOID_HIGH_DOWN","REGIME_SWITCH_AVOID_ALL_HIGH","CASH_ONLY")
OLD={"BULL_LOGISTIC":("LOGISTIC","portfolio"),"BULL_TREND":("TREND_RULE","portfolio"),
     "BEAR_LOGISTIC":("BEAR_LOGISTIC_ONLY","regime"),"BULL_PLUS_BEAR":("BULL_PLUS_BEAR_LOGISTIC","regime")}


def context(prices):
    spy=prices["SPY"].close
    m=spy.pct_change(20,fill_method=None).shift(1)
    regime=pd.Series(np.select([m>.02,m<-.02],["UP","DOWN"],default="SIDEWAYS"),index=m.index)
    regime=regime.where(m.notna())
    return pd.DataFrame({"mom_regime":regime,
        "spy5":spy.pct_change(5,fill_method=None).shift(1),
        "spy_realized_vol20_lag":spy.pct_change(fill_method=None).rolling(20,min_periods=20).std().shift(1)*np.sqrt(252),
        "gld5":prices["GLD"].close.pct_change(5,fill_method=None).shift(1),
        "vix":prices["^VIX"].close.shift(1)})


def masks(frame):
    l=frame.family.eq("BULL_LOGISTIC")
    t=frame.family.eq("BULL_TREND")
    b=frame.family.eq("BEAR_LOGISTIC")
    up=frame.mom_regime.eq("UP")
    down=frame.mom_regime.eq("DOWN")
    side=frame.mom_regime.eq("SIDEWAYS")
    vol=frame.get("spy_realized_vol20_lag",pd.Series(np.nan,index=frame.index))
    observed=vol.notna()
    switch=(t&up)|(l&down)|b
    # Missing lagged inputs never qualify for the discovery gates.
    a=l&frame.ret5.lt(0)&frame.spy5.ge(0)
    c=b&frame.vix.ge(20)&frame.gld5.ge(0)
    return {"BULL_LOGISTIC":l,"BULL_TREND":t,"BEAR_LOGISTIC":b,"BULL_PLUS_BEAR":l|b,
        "REGIME_SWITCH_CASH":(t&up)|(l&down),
        "REGIME_SWITCH_BEAR":(t&up)|(l&down)|b,
        "REGIME_SWITCH_TREND_SIDEWAYS":(t&(up|side))|(l&down)|b,
        "DISCOVERY_GATES":a|c,
        "REGIME_SWITCH_AVOID_HIGH_DOWN":switch&observed&~(down&vol.ge(.2)),
        "REGIME_SWITCH_AVOID_ALL_HIGH":switch&observed&vol.lt(.2),
        "CASH_ONLY":pd.Series(False,index=frame.index)}


def candidates(result,prices,portfolio):
    bull=csv(result,"research/oos_trades.csv")
    bull["family"]=bull.strategy.map({"LOGISTIC":"BULL_LOGISTIC","TREND_RULE":"BULL_TREND"})
    bear=csv(result,"research/regime_challenger/bear_oos_trades.csv")
    bear["family"]=bear.candidate_family
    frame=normalize_keys(pd.concat([bull,bear],ignore_index=True))
    if frame.family.value_counts().to_dict()!={"BULL_LOGISTIC":439,"BULL_TREND":1061,
        "BEAR_LOGISTIC":89,"BEAR_RULE":152} or frame.duplicated(["family",*KEY]).any():
        raise ValueError("FROZEN_CANDIDATE_COUNT_MISMATCH")
    ctx=context(prices)
    frame=frame.merge(ctx,left_on="signal_date",right_index=True,how="left",validate="many_to_one")
    frame["ret5"]=np.nan
    for s,g in frame.groupby("symbol"):
        p=prices[s]
        r=p.close.loc[g.exit_date].to_numpy()/p.open.loc[g.entry_date].to_numpy()-1
        if not np.allclose(r,g.gross_return,rtol=0,atol=2e-6) or not np.allclose(r-.002,g.net_return,rtol=0,atol=2e-6):
            raise ValueError("FROZEN_OHLC_LABEL_MISMATCH")
        frame.loc[g.index,"ret5"]=p.close.pct_change(5,fill_method=None).loc[g.signal_date].to_numpy()
    if frame[["ret5","mom_regime","spy_realized_vol20_lag"]].isna().any().any():
        raise ValueError("MISSING_CANDIDATE_CONTEXT")
    original_state=portfolio.market_state(prices)
    event_map={}
    for family,g in frame.groupby("family"):
        rows=portfolio.prepared_events(g,prices,original_state,
            strategy=str(g.strategy.iloc[0]),excluded=set())
        for row in rows:
            k=(family,*(row[c] for c in KEY))
            if k in event_map:
                raise ValueError("DUPLICATE_EVENT")
            event_map[k]=row
    if len(event_map)!=1741:
        raise ValueError("ORIGINAL_EVENT_COVERAGE_MISMATCH")
    return frame,event_map


def old_tables(result):
    out={}
    for name,eq,ex in (
        ("portfolio","research/portfolio_daily_equity.csv","research/portfolio_executions.csv"),
        ("regime","research/regime_challenger/regime_daily_equity.csv",
         "research/regime_challenger/regime_executions.csv")):
        c=csv(result,eq); c["date"]=pd.to_datetime(c.date)
        e=normalize_keys(csv(result,ex))
        out[name]=(c,e)
    return out


def audit_original(curve,fills,scenario,old):
    c,e=old
    ref=c.loc[c.scenario.eq(scenario)].set_index("date")
    if len(ref)!=len(curve) or not ref.index.equals(curve.index):
        raise ValueError("BASELINE_CALENDAR_MISMATCH")
    eq=float((ref.equity-curve.equity).abs().max())
    actual=normalize_keys(fills)
    prior=e.loc[e.scenario.eq(scenario)]
    j=actual.merge(prior,on=KEY,how="outer",validate="one_to_one",indicator=True)
    if not j._merge.eq("both").all():
        raise ValueError("BASELINE_FILL_KEY_MISMATCH")
    pnl=float((j.net_pnl_x-j.net_pnl_y).abs().max())
    if eq>=1e-4 or pnl>=1e-4:
        raise ValueError("BASELINE_REPLAY_MISMATCH")
    return {"scenario":scenario,"sessions":len(curve),"fills":len(fills),
            "max_equity_error":eq,"max_pnl_error":pnl}


def replay(prices,result,portfolio):
    frame,event_map=candidates(result,prices,portfolio)
    sessions=portfolio.validate_sessions(prices)
    if len(sessions)!=727 or str(sessions[-1].date())!=ASOF:
        raise ValueError("FROZEN_SESSION_COVERAGE")
    checks=old_tables(result)
    audit=[];scenarios=[]
    for cohort,excluded in (("ALL_20",set()),("EXCLUDE_HIGH_RISK",HIGH_RISK)):
        for name,mask in masks(frame).items():
            f=frame.loc[mask&~frame.symbol.isin(excluded)]
            events=[event_map[(r.family,*(getattr(r,c) for c in KEY))]
                    for r in f.itertuples(index=False)]
            for cap in (3,5):
                for cost in (20,40):
                    curve,fills,skips=portfolio.simulate(events,prices,sessions,
                        strategy=name,cohort=cohort,max_positions=cap,
                        allocation=1./cap,round_trip_cost_bps=cost)
                    if (name in OLD and not len(fills)) or (curve.cash<-1e-6).any() or curve.active_positions.gt(cap).any():
                        raise ValueError("REPLAY_CASH_OR_CAPACITY_VIOLATION")
                    m=portfolio.performance(curve)
                    scenarios.append({"name":name,"cohort":cohort,"cap":cap,"cost_bp":cost,
                        "candidates":len(events),"fills":len(fills),"skipped":skips,
                        "win_rate":float(fills.realized_return.gt(0).mean()) if len(fills) else None,
                        "mean_trade":float(fills.realized_return.mean()) if len(fills) else None,
                        "severe":int(fills.realized_return.le(-.05).sum()) if len(fills) else 0,**m})
                    if name in OLD and (cap==5 or OLD[name][1]=="portfolio"):
                        prefix,table=OLD[name]
                        scenario=f"{prefix}__{cohort}__POS{cap}__COST{cost}BP"
                        audit.append(audit_original(curve,fills,scenario,checks[table]))
    if len(scenarios)!=88 or len(audit)!=24 or sum(x["fills"] for x in audit)!=8108:
        raise ValueError("FROZEN_REPLAY_COVERAGE_MISMATCH")
    return {"schema":"kalman-frozen-regime-cash-replay-v1",
        "asof":ASOF,"input_sha256":{k:v[2] for k,v in ARCHIVES.items()},
        "research_only":True,"production_writes":False,"approved_live":False,
        "new_holdout":False,"source_finality_certified":False,"new_signals_generated":False,
        "portfolio_resimulated":True,"candidate_count":len(frame),"sessions":len(sessions),
        "baseline_audit":audit,"scenarios":scenarios,
        "benchmarks":{s:portfolio.buy_hold(prices,sessions,s) for s in ("SPY","QQQ")},
        "limitations":[
            "Previously inspected data and discovery gates; no independent evidence or selection.",
            "Frozen nonoverlapping candidate streams, not re-generated model signals; filtered events may leave unobserved opportunities.",
            "Actual archived adjusted OHLC, not independently source-certified or PIT-certified.",
            "Fixed universe, including unresolved historical IONQ lineage in ALL_20.",
            "Original next-open/exit-close friction, equal capital fractions, no leverage; no extra slippage, taxes, or cash interest.",
            "Market momentum categories are lagged SPY 20d return >2%, <-2%, otherwise sideways, separate from original Bull/Bear gate.",
            "Discovery gates use signal close stock ret5<0 and lagged SPY ret5>=0; Bear uses lagged VIX>=20 and lagged GLD ret5>=0.",
            "New entry-only cash gates use lagged annualized 20-day SPY realized volatility >=20%; existing positions retain their exits. Cash-only assumes zero interest.",
            "No threshold search, model promotion, live change, or future return used to rank candidates.",
        ]}


def run(raw,result,train):
    import portfolio
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for name,blob in raw.items():
            dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(blob)
        market=root/"market"
        prices={s:train.load_bars(train.market_file(market,s))[["open","close"]]
                for s in CORE+["^VIX","GLD"]}
        return replay(prices,result,portfolio)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("data","results","original-source","out"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args()
    report=run(load_archive(a.data,"data"),load_archive(a.results,"results"),load_original(a.original_source))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print("FROZEN_REGIME_CASH_REPLAY_RESEARCH_ONLY",len(report["scenarios"]),len(report["baseline_audit"]))
