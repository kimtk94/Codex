#!/usr/bin/env python3
"""Read-only diagnostic for legacy backtest grid state, fills, and fee sensitivity."""
import argparse,sqlite3,math,json,datetime as dt
p=argparse.ArgumentParser();p.add_argument("--db",default="krw_eth_1m.sqlite3");p.add_argument("--capital",type=float,default=1000000);a=p.parse_args()
con=sqlite3.connect("file:"+__import__("pathlib").Path(a.db).resolve().as_posix()+"?mode=ro",uri=True)
bounds=("2023-12-31T15:00:00+00:00","2026-10-14T10:00:00+00:00")
def run(spacing,levels,fee,slip):
    it=iter(con.execute("SELECT ts_utc,open,close FROM candles WHERE ts_utc>=? AND ts_utc<? ORDER BY ts_utc",bounds))
    first=next(it);anchor=first[2];cash=a.capital*.5;eth=a.capital*.5/(anchor*(1+fee+slip))
    equity0=cash+eth*anchor;lastidx=0;prev=first
    counts=dict(requested_levels=0,filled_buy=0,filled_sell=0,unfilled_buy=0,unfilled_sell=0,zero_delta=0,large_jump=0)
    fees=0;slippage_cost=0;high_eth=eth;lowest_cash=cash;turnover=0;max_abs_idx=0
    for ts,op,cl in it:
        idx=math.floor(math.log(prev[2]/anchor)/math.log1p(spacing));delta=idx-lastidx
        if abs(delta)>levels:counts["large_jump"]+=1
        max_abs_idx=max(max_abs_idx,abs(idx))
        if delta==0:counts["zero_delta"]+=1
        counts["requested_levels"]+=min(abs(delta),levels)
        order=a.capital/levels
        for _ in range(min(abs(delta),levels)):
            if delta<0:
                if cash<order*.999:
                    counts["unfilled_buy"]+=1;break
                qty=order/(op*(1+slip)*(1+fee));cash-=order;eth+=qty;counts["filled_buy"]+=1
                fees+=order*fee/(1+fee);slippage_cost+=order*slip/(1+slip);turnover+=order
            elif delta>0:
                qty=min(eth,order/(op*(1-slip)))
                if qty<order/(op*(1-slip))*.999:
                    counts["unfilled_sell"]+=1;break
                proceeds=qty*op*(1-slip);eth-=qty;cash+=proceeds*(1-fee)
                counts["filled_sell"]+=1;fees+=proceeds*fee;slippage_cost+=qty*op*slip;turnover+=proceeds
        lastidx=idx # legacy behavior
        high_eth=max(high_eth,eth);lowest_cash=min(lowest_cash,cash);prev=(ts,op,cl)
    final=cash+eth*prev[2]
    return dict(spacing_pct=spacing*100,levels=levels,fee=fee,slippage=slip,net_return_pct=round(100*(final/equity0-1),4),
        ending_cash=round(cash,1),ending_eth=round(eth,8),ending_equity=round(final,1),turnover=round(turnover,1),
        modeled_fees=round(fees,1),modeled_slippage=round(slippage_cost,1),max_abs_grid_index=max_abs_idx,**counts)
print("WARNING: diagnostic mirrors the LEGACY simulator, not accurate limit-order fills.")
for spacing,levels in [(0.0014,20),(0.004,20),(0.006,100)]:
 for fee,slip in [(0,0),(.0005,.0002)]:
    print(json.dumps(run(spacing,levels,fee,slip),ensure_ascii=False),flush=True)
