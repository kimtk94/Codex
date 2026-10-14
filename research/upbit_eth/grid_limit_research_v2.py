#!/usr/bin/env python3
"""Research-only resting limit grid v2. OHLC cannot reveal intrabar sequence. Python stdlib."""
import argparse,sqlite3,math,csv,json
from pathlib import Path
def simulate(db,spacing,levels,capital,fee,year):
    y1=f"{year}-01-01T00:00:00+09:00"
    y2=f"{year+1}-01-01T00:00:00+09:00"
    from datetime import datetime,timezone
    to_utc=lambda x:datetime.fromisoformat(x).astimezone(timezone.utc).isoformat()
    begin,end=to_utc(y1),to_utc(y2)
    cn=sqlite3.connect("file:"+str(Path(db).resolve())+"?mode=ro",uri=True)
    it=iter(cn.execute("SELECT ts_utc,open,high,low,close FROM candles WHERE ts_utc>=? AND ts_utc<? ORDER BY ts_utc",(begin,end)))
    first=next(it,None)
    if first is None:return {}
    anchor=float(first[4]);cash=capital/2;eth=capital/2/anchor
    # A finite static grid with one unit of inventory per buy/sell fill.
    levels_each_side=levels//2
    unit=capital/levels
    buy_prices=[anchor*(1+spacing)**(-k) for k in range(1,levels_each_side+1)]
    sell_prices=[anchor*(1+spacing)**k for k in range(1,levels_each_side+1)]
    # Pending order levels: buys initially below anchor; sells initially above.
    buys=set(range(1,levels_each_side+1))
    sells=set(range(1,levels_each_side+1))
    # Each filled buy places exactly one sell target one spacing above it; vice versa.
    # price-keyed order records, qty per trade; capped one fill per level per candle.
    active_buy={round(x,8):unit for x in buy_prices}
    active_sell={round(x,8):unit/anchor for x in sell_prices}
    fills=0; blocked=0;turnover=0;fees=0;peak=capital;mdd=0;gaps=0;prev_time=None
    for ts,o,h,l,c in it:
        from datetime import datetime
        t=datetime.fromisoformat(ts)
        if prev_time and (t-prev_time).total_seconds()>60:
            gaps+=1
            # Prevent stale resting orders from being assumed filled in unobserved time:
            # no execution inside gap; this is conservative but incomplete.
        prev_time=t
        # Freeze orders at candle start. If both directions touched, skip entire
        # candle because the OHLC path is unknowable. No same-bar round trips.
        touched_b=[px for px in active_buy if l<=px]
        touched_s=[px for px in active_sell if h>=px]
        if touched_b and touched_s:
            blocked+=1
        elif touched_b:
            for px in sorted(touched_b,reverse=True):
                gross=active_buy.get(px)
                if gross is None:continue
                if cash+1e-8<gross*(1+fee):continue
                qty=gross/px
                cash-=gross*(1+fee);eth+=qty;fees+=gross*fee;turnover+=gross;fills+=1
                del active_buy[px]
                next_sell=round(px*(1+spacing),8)
                active_sell[next_sell]=active_sell.get(next_sell,0)+qty
        elif touched_s:
            for px in sorted(touched_s):
                qty=active_sell.get(px)
                if qty is None:continue
                if eth+1e-12<qty:continue
                proceeds=qty*px;eth-=qty;cash+=proceeds*(1-fee);fees+=proceeds*fee;turnover+=proceeds;fills+=1
                del active_sell[px]
                next_buy=round(px/(1+spacing),8)
                active_buy[next_buy]=active_buy.get(next_buy,0)+proceeds/(1+fee)
        equity=cash+eth*c;peak=max(peak,equity);mdd=min(mdd,equity/peak-1)
        last_close=c
    end_value=cash+eth*last_close
    return dict(year=year,spacing_pct=spacing*100,levels=levels,return_pct=round(100*(end_value/capital-1),4),
      mdd_pct=round(mdd*100,4),fills=fills,turnover_krw=round(turnover,2),
      fee_krw=round(fees,2),skipped_ambiguous_bars=blocked,gap_events=gaps,
      ending_cash=round(cash,2),ending_eth=round(eth,8),benchmark_bh_pct=round((last_close/anchor-1)*100,4))
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",default="krw_eth_1m.sqlite3")
    p.add_argument("--out",default="results_v2_limit")
    p.add_argument("--capital",type=float,default=1000000)
    p.add_argument("--fee",type=float,default=.0005)
    a=p.parse_args();out=Path(a.out);out.mkdir(exist_ok=True,parents=True)
    records=[]
    for year in (2024,2025,2026):
        for spacing in (.0014,.0025,.004,.006,.01,.015):
            for levels in (20,50,100):
                row=simulate(a.db,spacing,levels,a.capital,a.fee,year)
                records.append(row)
                print(json.dumps(row,ensure_ascii=False),flush=True)
    if records:
        with (out/"grid_limit_results.csv").open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    print("EXPLORATORY ONLY: no book depth, price-time queue or trade-level ordering; gaps unresolved.")
if __name__=="__main__":main()
