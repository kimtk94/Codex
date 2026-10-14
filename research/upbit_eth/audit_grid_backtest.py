#!/usr/bin/env python3
"""Historical KRW-ETH grid research. Standard library, offline, no orders."""
import argparse, csv, datetime as dt, json, math, sqlite3
from pathlib import Path
UTC=dt.timezone.utc
START=dt.datetime.fromisoformat("2024-01-01T00:00:00+09:00").astimezone(UTC).isoformat()
END=dt.datetime.fromisoformat("2026-10-14T19:00:00+09:00").astimezone(UTC).isoformat()
def source(cn,start,end):
    return cn.execute("SELECT ts_utc,open,high,low,close,volume_eth,value_krw FROM candles WHERE ts_utc>=? AND ts_utc<? ORDER BY ts_utc",(start,end))
def audit(cn):
    previous=None;n=0;missing=0;invalid=0;first=None;last=None;duplicates=0
    for x in source(cn,START,END):
        ts,o,h,l,c,v,val=x
        if first is None:first=ts
        last=ts;n+=1
        if not (0<l<=min(o,c)<=max(o,c)<=h and v>=0 and val>=0): invalid+=1
        if previous is not None:
            gap=int((dt.datetime.fromisoformat(ts)-dt.datetime.fromisoformat(previous)).total_seconds()//60)-1
            missing+=max(0,gap)
            if gap<0:duplicates+=1
        previous=ts
    expected=int((dt.datetime.fromisoformat(END)-dt.datetime.fromisoformat(START)).total_seconds()/60)
    return dict(rows=n,first_utc=first,last_utc=last,expected_calendar_minutes=expected,
        missing_calendar_minutes=expected-n,internal_gaps=missing,invalid_ohlcv=invalid,
        duplicates=duplicates,coverage_pct=round(100*n/expected,5))
def backtest(cn,start,end,spacing,levels,capital,fee,slip):
    bars=iter(source(cn,start,end))
    first=next(bars,None)
    if first is None:return None
    anchor=float(first[4]);cash=capital*.5;eth=(capital*.5)/(anchor*(1+fee+slip))
    equity0=cash+eth*anchor;peak=equity0;worst=0;trades=buys=sells=0;turnover=0
    prior=first;lastidx=0;last_equity=equity0;last_ts=first[0]
    for row in bars:
        open_px=float(row[1]); close=float(row[4]);prevclose=float(prior[4])
        idx=math.floor(math.log(prevclose/anchor)/math.log1p(spacing))
        delta=idx-lastidx
        if delta:
            order=capital/levels
            for _ in range(min(abs(delta),levels)):
                if delta<0:
                    if cash<order*.999:break
                    qty=order/(open_px*(1+slip)*(1+fee))
                    cash-=order;eth+=qty;buys+=1;turnover+=order
                else:
                    qty=min(eth,order/(open_px*(1-slip)))
                    if qty<order/(open_px*(1-slip))*.999:break
                    proceeds=qty*open_px*(1-slip)
                    eth-=qty;cash+=proceeds*(1-fee);sells+=1;turnover+=proceeds
                trades+=1
        lastidx=idx
        last_equity=cash+eth*close
        peak=max(peak,last_equity);worst=min(worst,last_equity/peak-1)
        prior=row;last_ts=row[0]
    days=(dt.datetime.fromisoformat(last_ts)-dt.datetime.fromisoformat(first[0])).total_seconds()/86400
    return dict(return_pct=round((last_equity/equity0-1)*100,5),
      mdd_pct=round(worst*100,5),
      cagr_pct=round(((last_equity/equity0)**(365.25/days)-1)*100,5) if days>0 else None,
      benchmark_buy_hold_pct=round((float(prior[4])/anchor-1)*100,5),
      trades=trades,buys=buys,sells=sells,turnover_krw=round(turnover,1),ending_equity_krw=round(last_equity,1))
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",default="krw_eth_1m.sqlite3")
    p.add_argument("--out",default="results")
    p.add_argument("--capital",type=float,default=1000000)
    p.add_argument("--fee",type=float,default=.0005)
    p.add_argument("--slippage",type=float,default=.0002)
    p.add_argument("--audit-only",action="store_true")
    p.add_argument("--allow-gaps",action="store_true",help="Exploratory results only; does not reconstruct missing trades")
    a=p.parse_args()
    cn=sqlite3.connect("file:"+str(Path(a.db).resolve())+"?mode=ro",uri=True)
    cn.execute("PRAGMA query_only=ON")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    qa=audit(cn);(out/"audit.json").write_text(json.dumps(qa,indent=2))
    print("AUDIT",json.dumps(qa),flush=True)
    if a.audit_only:return
    if qa["invalid_ohlcv"] or qa["duplicates"]:raise SystemExit("OHLCV/duplicate failure")
    if qa["first_utc"] is None or qa["first_utc"]>START or qa["last_utc"] is None or qa["last_utc"]< (dt.datetime.fromisoformat(END)-dt.timedelta(minutes=1)).isoformat():
        raise SystemExit("Boundary coverage failure: check requested start/end and database")
    if qa["missing_calendar_minutes"] and not a.allow_gaps:
        raise SystemExit("Missing minute slots: investigate whether legitimate no-trade gaps. For EXPLORATORY run add --allow-gaps")
    years=[("2024",START,"2025-01-01T00:00:00+09:00"),("2025","2025-01-01T00:00:00+09:00","2026-01-01T00:00:00+09:00"),("2026","2026-01-01T00:00:00+09:00","2026-10-14T19:00:00+09:00")]
    ranges=[("all",START,END)]+[(y,dt.datetime.fromisoformat(s).astimezone(UTC).isoformat(),dt.datetime.fromisoformat(e).astimezone(UTC).isoformat()) for y,s,e in years]
    results=[]
    for spacing in (.0014,.0025,.004,.006):
        for levels in (20,50,100):
            r=dict(grid_spacing_pct=100*spacing,levels=levels)
            for key,begin,finish in ranges:
                metric=backtest(cn,begin,finish,spacing,levels,a.capital,a.fee,a.slippage)
                if metric:
                    for k,v in metric.items():r[f"{key}_{k}"]=v
            results.append(r)
            print("TEST",len(results),"/12",r["grid_spacing_pct"],levels,r.get("all_return_pct"),flush=True)
    results.sort(key=lambda x:x.get("2024_return_pct",-1e9),reverse=True)
    with (out/"grid_sweep.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
    (out/"selected_2024_only.json").write_text(json.dumps(results[0],indent=2))
    print("COMPLETE; ranked by 2024 training performance; 2025/2026 independent reset-inventory tests",flush=True)
if __name__=="__main__":main()
