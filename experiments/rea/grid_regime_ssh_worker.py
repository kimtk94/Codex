#!/usr/bin/env python3
"""Research-only causal regime filter: server DB is never modified.
Policy: DOWN/WARMUP cancels buys; sells persist. UP reseeds only when state changes.
Compare against the exact original simulator under the same data/fees.
"""
import json,sys,sqlite3,datetime as dt
from pathlib import Path
from collections import deque
P=json.load(sys.stdin)
db=Path(P["db"]).expanduser().resolve()
con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
con.execute("PRAGMA query_only=ON")
kst=dt.timezone(dt.timedelta(hours=9))
# Prepare previous-completed-KST-day signals, using all available history.
close_by_day={}
for ts,cl in con.execute("SELECT ts_utc,close FROM candles WHERE ts_utc<? ORDER BY ts_utc",(str(dt.datetime(P["year"]+1,1,1,tzinfo=kst).astimezone(dt.timezone.utc).isoformat()),)):
    day=dt.datetime.fromisoformat(ts).astimezone(kst).date()
    close_by_day[day]=float(cl)
regimes={}
hist=[]
for day in sorted(close_by_day):
    if len(hist)<60: regimes[day]="WARMUP"
    else: regimes[day]="UP" if sum(hist[-20:])/20>sum(hist[-60:])/60 else "DOWN"
    hist.append(close_by_day[day])
src=P["source"]
base_ns={"__name__":"grid_base","__file__":"<memory>"}
exec(compile(src,"<base>","exec"),base_ns)
base=base_ns["sim"](con,P["year"],P["spacing"],P["levels"],P["capital"],P["fee"])
# Exact source substitutions are fingerprint-checked; refuse unexpected edits.
patches=[
 (" def seed(center):\n", " def seed(center):\n"),
 (" seed(anchor);prev=dt.datetime.fromisoformat(first[0]);last=anchor",
  " seed(anchor);prev=dt.datetime.fromisoformat(first[0]);last=anchor;last_regime=None"),
 ("  prev=t\n  bs=[key for key in orders",
  """  prev=t
  current_regime=regime_by_day.get(t.astimezone(kst).date(),'WARMUP')
  if current_regime!=last_regime:
   if current_regime=='UP':
    cancel();seed(close)
   else:
    for key in list(orders):
     if key[0]=='B':
      v=orders.pop(key);krw+=v*(1+fee);hold_krw-=v*(1+fee)
   last_regime=current_regime
  bs=[key for key in orders"""),
 ("   for side,px,amount in pending:add(side,px,amount)",
  "   for side,px,amount in pending:\n    if side!='B' or current_regime=='UP':add(side,px,amount)")
]
for old,new in patches[1:]:
    if src.count(old)!=1:raise RuntimeError("SOURCE_PATCH_MISMATCH:"+old[:40])
    src=src.replace(old,new)
# Gap branch is unchanged: gate after gap on next candle, disclosed limitation.
ns={"__name__":"grid_regime","__file__":"<memory>","regime_by_day":regimes,"kst":kst}
exec(compile(src,"<regime>","exec"),ns)
filtered=ns["sim"](con,P["year"],P["spacing"],P["levels"],P["capital"],P["fee"])
con.close()
counts={x:list(regimes.values()).count(x) for x in ("UP","DOWN","WARMUP")}
print(json.dumps({"year":P["year"],"spacing":P["spacing"],"levels":P["levels"],"baseline":base,"filtered":filtered,"regime_days":counts,"read_only":True,"limitations":["Gap reseed occurs before regime gate; following bar processes cancellation","UP re-entry cancels and reseeds all orders, not only buys","OHLC fills are not order-book verified"]}))
