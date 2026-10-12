"""PAPER ONLY: fee-equivalent adverse execution cost stress; not actual fill slippage."""
import argparse,csv,json
from decimal import Decimal
from pathlib import Path
from upbit_paper_grid_v35 import evaluate_upbit
COSTS=('0','0.02','0.05','0.10')
GAPS=('0.14','0.50','1.00')
MODES=(0,700)
MARKETS=('KRW-BTC','KRW-ETH')
def run(input_dir,out_dir):
 root=Path(input_dir);out=Path(out_dir);out.mkdir(parents=True,exist_ok=True);results=[]
 for market in MARKETS:
  with (root/(market+'_1m_history.csv')).open(newline='') as f:data=list(csv.DictReader(f))
  stamps=[r['t'] for r in data]
  if len(stamps)<40000 or stamps!=sorted(stamps) or len(set(stamps))!=len(stamps):raise ValueError('input uniqueness/count: '+market)
  if not (stamps[0].startswith('2026-09-01') and stamps[-1].startswith('2026-09-30')):raise ValueError('wrong date: '+market)
  obs=[(r['t'],r['c']) for r in data]
  for gap in GAPS:
   for mode in MODES:
    for extra in COSTS:
     fee=str(Decimal('0.05')+Decimal(extra))
     result=evaluate_upbit(obs,spacing=gap,anchor_every=mode,fee=fee)
     result.update(market=market,spacing_pct=gap,recenter_observations=mode,base_fee_pct='0.05',extra_cost_pct_each_side=extra,accounting_cost_pct_each_side=fee,interpretation='ADVERSE_COST_PROXY_NOT_FILL_SLIPPAGE')
     results.append(result)
 dest=out/'v38_cost_stress.csv'
 with dest.open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(results[0]));writer.writeheader();writer.writerows(results)
 meta={'scenarios':len(results),'paper_only':True,'output':str(dest),'extra_costs_pct':COSTS,'cost_model':'Extra expense treated as fee-equivalent at every hypothetical fill. Not real price slippage, order-book execution, queue position, or no-fill model.'}
 (out/'manifest.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input-dir',required=True);p.add_argument('--out-dir',required=True)
 a=p.parse_args();run(a.input_dir,a.out_dir)
