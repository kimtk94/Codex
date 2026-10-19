#!/usr/bin/env python3
"""GitHub-runner-only Upbit KRW-ETH minute candle collector; no SSH/credentials.
Backwards cursor is exclusive; database is created only in local CI workspace.
"""
import argparse, datetime as dt, json, sqlite3, time, urllib.parse, urllib.request
from pathlib import Path
UTC=dt.timezone.utc
def iso(v):
    return v.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
def collect(path,start,end,max_calls=10000,delay=.16):
    con=sqlite3.connect(str(path))
    con.execute("CREATE TABLE IF NOT EXISTS candles(ts_utc TEXT PRIMARY KEY, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, val TEXT)")
    cursor=end
    total=0; calls=0; empty=0
    while cursor>start:
        if calls>=max_calls: raise RuntimeError("MAX_CALLS_REACHED")
        query=urllib.parse.urlencode({"market":"KRW-ETH","to":iso(cursor),"count":200})
        url="https://api.upbit.com/v1/candles/minutes/1?"+query
        payload=None
        for attempt in range(7):
            try:
                req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"kalman-ci-readonly/1.0"})
                with urllib.request.urlopen(req,timeout=40) as resp:payload=json.load(resp)
                break
            except Exception as e:
                if attempt==6:raise
                time.sleep(min(35,2**attempt))
        calls+=1
        if not isinstance(payload,list) or not payload:raise RuntimeError("UPBIT_EMPTY_OR_BAD_RESPONSE")
        oldest=None; batches=[]
        for item in payload:
            stamp=dt.datetime.fromisoformat(item["candle_date_time_utc"]).replace(tzinfo=UTC)
            if oldest is None or stamp<oldest:oldest=stamp
            if start<=stamp<end:
                high,low,close=(float(item[k]) for k in ("high_price","low_price","trade_price"))
                if not (0<low<=close<=high):raise ValueError("INVALID_OHLC "+str(item))
                batches.append((stamp.isoformat(),high,low,close))
        if oldest is None or oldest>=cursor:raise RuntimeError("CURSOR_STALLED")
        con.executemany("INSERT OR REPLACE INTO candles VALUES (?,?,?,?)",batches)
        con.commit()
        total+=len(batches)
        cursor=oldest
        if calls%100==0:print(json.dumps({"calls":calls,"rows":total,"cursor":iso(cursor)}),flush=True)
        time.sleep(delay)
    count,low,high=con.execute("SELECT COUNT(*),MIN(ts_utc),MAX(ts_utc) FROM candles").fetchone()
    if count<2:raise RuntimeError("NOT_ENOUGH_CANDLES")
    con.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)",("source","Upbit public 1m KRW-ETH"))
    con.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)",("requested_start",iso(start)))
    con.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)",("requested_end",iso(end)))
    con.commit()
    integrity=con.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity!="ok":raise RuntimeError("SQLITE_INTEGRITY_FAIL "+integrity)
    gaps=con.execute("SELECT COUNT(*) FROM (SELECT (julianday(ts_utc)-julianday(LAG(ts_utc) OVER (ORDER BY ts_utc)))*1440 AS delta FROM candles) WHERE delta>5.01").fetchone()[0]
    con.close()
    return {"source":"Upbit public API","rows":count,"min_ts":low,"max_ts":high,"calls":calls,"gt5min_gaps":gaps,"integrity":integrity}
def main():
    p=argparse.ArgumentParser();p.add_argument("--db",required=True);p.add_argument("--start",required=True);p.add_argument("--end",required=True);p.add_argument("--max-calls",type=int,default=10000)
    a=p.parse_args()
    start=dt.datetime.fromisoformat(a.start.replace("Z","+00:00")).astimezone(UTC)
    end=dt.datetime.fromisoformat(a.end.replace("Z","+00:00")).astimezone(UTC)
    if start>=end:raise SystemExit("INVALID_TIME_RANGE")
    print("COLLECTOR_RESULT="+json.dumps(collect(Path(a.db),start,end,a.max_calls)),flush=True)
if __name__=="__main__":main()
