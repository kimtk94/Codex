"""VectorBT synthetic smoke test; no market fetches, no trades, no Kalman LIVE edits."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import vectorbt as vbt

idx=pd.date_range("2026-01-05",periods=160,freq="B",tz="UTC")
close=pd.Series(100*np.exp(np.cumsum(np.sin(np.arange(160)/9)*0.002+0.0003)),index=idx)
fast=vbt.MA.run(close,10)
slow=vbt.MA.run(close,25)
entries=fast.ma_crossed_above(slow)
exits=fast.ma_crossed_below(slow)
pf=vbt.Portfolio.from_signals(close,entries,exits,init_cash=100000,fees=0.001,slippage=0.0005,freq="1D")
result={"engine":"vectorbt","data":"SYNTHETIC_ONLY","rows":len(close),"entries":int(entries.sum()),
        "orders":int(len(pf.orders.records)),"total_return":float(pf.total_return()),
        "max_drawdown":float(pf.max_drawdown()),"version":vbt.__version__,
        "warning":"Synthetic MA demonstration, NOT Kalman Triple Barrier replication or investment performance."}
assert np.isfinite(result["total_return"]) and np.isfinite(result["max_drawdown"])
out=Path("artifacts/market-tool-lab/vectorbt_smoke.json")
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result))
