#!/usr/bin/env python3
"""Read-only four-arm regime attribution worker for a single year/spacing."""
import json,sys,sqlite3,datetime as dt
from pathlib import Path
P=json.load(sys.stdin)
db=Path(P["db"]).expanduser().resolve()
if not db.is_file():raise SystemExit("DB_NOT_FOUND")
con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
con.execute("PRAGMA query_only=ON")
kst=dt.timezone(dt.timedelta(hours=9))
closing={}
end=dt.datetime(P["year"]+1,1,1,tzinfo=kst).astimezone(dt.timezone.utc).isoformat()
start=(dt.datetime(P["year"],1,1,tzinfo=kst)-dt.timedelta(days=90)).astimezone(dt.timezone.utc).isoformat()
for ts,close in con.execute("SELECT ts_utc,close FROM candles WHERE ts_utc>=? AND ts_utc<? ORDER BY ts_utc",(start,end)):
    closing[dt.datetime.fromisoformat(ts).astimezone(kst).date()]=float(close)
days=sorted(closing)
regimes={}
for i,day in enumerate(days):
    if i<60:regimes[day]="WARMUP"
    else:
        vals=[closing[d] for d in days[i-60:i]]
        regimes[day]="UP" if sum(vals[-20:])/20>sum(vals)/60 else "DOWN"
ns={"__name__":"attribution_module","__file__":"<memory>"}
exec(compile(P["module"],"<attribution-module>","exec"),ns)
policy=P["policy"]
if policy not in ns["POLICIES"]:raise SystemExit("INVALID_POLICY")
results={policy:ns["simulate"](P["source"],con,P["year"],P["spacing"],P["levels"],P["capital"],P["fee"],regimes,kst,policy)}
con.close()
print(json.dumps({"year":P["year"],"spacing":P["spacing"],"levels":P["levels"],"results":results,"read_only":True,"limitation":"Exploratory OHLC-only attribution; not orderbook fill verification"}))
