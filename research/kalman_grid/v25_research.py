"""PAPER ONLY: close-snapshot grid comparison with safe recentring.
Not a fill-realistic backtest. It deliberately does not connect to a broker.
"""
import argparse, csv, json
from pathlib import Path
from kalman_grid_v23 import Grid, D

class RollingGrid(Grid):
    def recenter(self, new_anchor):
        for oid in list(self.buys.values()):
            self.ledger.cancel(oid)
        self.buys.clear()
        self.anchor=D(new_anchor)
        # Existing sell order prices and the lots they cover are preserved.
        self._fund()
        self.ledger.audit()

def evaluate(rows, *, anchor_every=0, spacing='0.14', levels=100, cash='30000', notional='10000', fee='0.04'):
    it=iter(rows); first=next(it)
    g=RollingGrid(first[1],spacing=spacing,levels=levels,cash=cash,notional=notional,fee=fee,exposure_cap=cash)
    count=1; shifts=0; last=D(first[1])
    for ts, price in it:
        # At a rebalance time, cancel old BUY orders but preserve existing lots and SELL orders.
        if anchor_every and count % anchor_every==0:
            g.recenter(price);shifts+=1
        g.update(price,ts);last=D(price);count+=1
    s=g.summary(last)
    return {'bars':count,'return_pct':float(s['return_pct']),'mdd_pct':float(s['mdd_pct']),
            'fills':s['fills'],'fees':float(s['fees']),'shifts':shifts,
            'open_lots':len(g.ledger.lots),'cash':float(s['cash']),
            'asset':float(s['asset']),'locked_cash':float(s['locked']),
            'equity':float(s['equity']),'realized_pnl':float(s['realized_pnl']),
            'unrealized_pnl':float(s['unrealized_pnl'])}

def main():
    p=argparse.ArgumentParser();p.add_argument('--data-dir',required=True)
    p.add_argument('--out-dir',required=True);p.add_argument('--symbols',default='QQQ,QLD')
    p.add_argument('--intervals',default='0,140,700');p.add_argument('--spacings',default='0.14,0.2,0.3,0.5,1.0')
    a=p.parse_args();import pandas as pd
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    results=[]
    for symbol in a.symbols.split(','):
        df=pd.read_parquet(Path(a.data_dir)/f'{symbol}_1h_2017plus.parquet')
        df=df.sort_values('t')
        if df.t.duplicated().any() or df[['c','t']].isna().any().any() or (df.c<=0).any():raise ValueError('bad input')
        rows=list(zip(df.t.astype(str),df.c.astype(str)))
        for interval in map(int,a.intervals.split(',')):
            for spacing in a.spacings.split(','):
                r=evaluate(rows,anchor_every=interval,spacing=spacing)
                r.update(symbol=symbol,interval_bars=interval,spacing_pct=spacing,start=rows[0][0],end=rows[-1][0])
                results.append(r)
    with (out/'sweep.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
    (out/'limitations.json').write_text(json.dumps({'execution':'PAPER_ONLY_CLOSE_OBSERVATION','intrabar':'UNKNOWN', 'slippage':'NOT_MODELED', 'fx':'NOT_MODELED', 'note':'Recenter cancels pending buys only. It never sells or discards existing lots.'},indent=2))
    print(json.dumps({'scenarios':len(results),'result_file':str(out/'sweep.csv')}))
if __name__=='__main__':main()
