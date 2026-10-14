#!/usr/bin/env python3
"""Upbit KRW-ETH 1-minute historical collection. Read-only, stdlib only."""
import argparse, datetime as dt, json, sqlite3, time, urllib.request, urllib.parse, urllib.error
from zoneinfo import ZoneInfo
UTC=dt.timezone.utc
def parse(s):
    v=dt.datetime.fromisoformat(s)
    return (v if v.tzinfo else v.replace(tzinfo=ZoneInfo("Asia/Seoul"))).astimezone(UTC)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",default="krw_eth_1m.sqlite3")
    p.add_argument("--start",default="2024-01-01T00:00:00+09:00")
    p.add_argument("--end",default="2026-10-14T19:00:00+09:00")
    p.add_argument("--pages",type=int,default=0)
    a=p.parse_args(); start,end=parse(a.start),parse(a.end)
    if start>=end: p.error("start must precede end")
    cn=sqlite3.connect(a.db)
    cn.execute("PRAGMA journal_mode=WAL")
    cn.execute("CREATE TABLE IF NOT EXISTS candles (ts_utc TEXT PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, volume_eth REAL, value_krw REAL)")
    cn.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, val TEXT)")
    key="cursor:"+start.isoformat()+":"+end.isoformat()
    row=cn.execute("SELECT val FROM metadata WHERE key=?",(key,)).fetchone()
    cursor=parse(row[0]) if row else end
    pages=0
    while cursor>start:
        url="https://api.upbit.com/v1/candles/minutes/1?"+urllib.parse.urlencode({"market":"KRW-ETH","count":200,"to":cursor.strftime("%Y-%m-%dT%H:%M:%SZ")})
        bars=None
        for attempt in range(8):
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"research-upbit-collector/1.0"}),timeout=30) as resp: bars=json.load(resp)
                break
            except (urllib.error.URLError,TimeoutError,ValueError) as e:
                if attempt==7: raise
                wait=max(2 if isinstance(e,urllib.error.HTTPError) and e.code==429 else .5,min(60,2**attempt))
                print("RETRY",str(e),"sleep",wait,flush=True);time.sleep(wait)
        if not isinstance(bars,list) or not bars: raise RuntimeError("No bars; checkpoint retained")
        rows=[]
        for b in bars:
            t=dt.datetime.fromisoformat(b["candle_date_time_utc"]).replace(tzinfo=UTC)
            if start<=t<end:
                rows.append((t.isoformat(),b["opening_price"],b["high_price"],b["low_price"],b["trade_price"],b["candle_acc_trade_volume"],b["candle_acc_trade_price"]))
        oldest=min(dt.datetime.fromisoformat(b["candle_date_time_utc"]).replace(tzinfo=UTC) for b in bars)
        if oldest>=cursor: raise RuntimeError("Non-decreasing pagination")
        with cn:
            cn.executemany("INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?)",rows)
            cn.execute("INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) DO UPDATE SET val=excluded.val",(key,oldest.isoformat()))
        pages+=1;cursor=oldest
        if pages%50==0 or cursor<=start:
            n=cn.execute("SELECT COUNT(*) FROM candles WHERE ts_utc>=? AND ts_utc<?",(start.isoformat(),end.isoformat())).fetchone()[0]
            print(json.dumps({"pages":pages,"candles":n,"cursor":cursor.isoformat(),"complete":cursor<=start}),flush=True)
        if a.pages and pages>=a.pages: break
        time.sleep(.16)
    print("COLLECTION_COMPLETE" if cursor<=start else "CHECKPOINT_SAVED")
if __name__=="__main__": main()
