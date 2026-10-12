"""Upbit public historical candles: paginated, append-safe, read-only research.
No API keys or trading endpoints. UTC timestamps, strict dedupe and audit.
"""
import argparse,csv,json,time,urllib.parse,urllib.request
from pathlib import Path
from datetime import datetime,timezone

FIELDS=["t","o","h","l","c","v"]
def utc(text):
    dt=datetime.fromisoformat(text.replace("Z","+00:00"))
    if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
def fetch(market,unit,to,count=200,retries=4):
    args=urllib.parse.urlencode({"market":market,"to":to,"count":count})
    url=f"https://api.upbit.com/v1/candles/minutes/{unit}?{args}"
    for attempt in range(retries):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"KalmanGridResearch/2.8"})
            with urllib.request.urlopen(req,timeout=25) as response:return json.load(response)
        except Exception:
            if attempt+1==retries:raise
            time.sleep(1.5*(attempt+1))
def collect(market,unit,start,end,out,max_pages=100,pause=.20):
    if market not in ("KRW-BTC","KRW-ETH") or unit not in (1,60):
        raise ValueError("unsupported market or unit")
    lower,upper=utc(start),utc(end)
    if lower>=upper:raise ValueError("invalid range")
    path=Path(out);path.parent.mkdir(parents=True,exist_ok=True)
    rows={}
    if path.exists():
        with path.open(newline="") as f:
            for row in csv.DictReader(f):rows[row["t"]]=row
    cursor=upper
    pages=0;reached_start=False;error=None
    for _ in range(max_pages):
        try: data=fetch(market,unit,cursor.strftime("%Y-%m-%dT%H:%M:%SZ"))
        except Exception as exc:
            error=repr(exc);break
        if not data:break
        oldest=min(utc(x["candle_date_time_utc"]) for x in data)
        for x in data:
            t=utc(x["candle_date_time_utc"])
            if lower<=t<upper:
                rows[t.isoformat()]={"t":t.isoformat(),"o":x["opening_price"],"h":x["high_price"],"l":x["low_price"],"c":x["trade_price"],"v":x["candle_acc_trade_volume"]}
        pages+=1
        if oldest<=lower: reached_start=True;break
        if oldest>=cursor:raise RuntimeError("nonadvancing pagination")
        cursor=oldest
        time.sleep(pause)
    ordered=[rows[t] for t in sorted(rows)]
    if any(float(r["h"])<max(float(r["o"]),float(r["c"]),float(r["l"])) or float(r["l"])>min(float(r["o"]),float(r["c"]),float(r["h"])) for r in ordered):
        raise ValueError("invalid OHLC")
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(ordered)
    meta={"market":market,"unit_minutes":unit,"requested_start":start,"requested_end":end,
          "pages_this_run":pages,"rows":len(rows),"first":ordered[0]["t"] if ordered else None,
          "last":ordered[-1]["t"] if ordered else None,"reached_start":reached_start,
          "complete":reached_start and error is None,"error":error,"cursor_next":cursor.isoformat(),
          "source":"Upbit public KRW candles","read_only":True}
    path.with_suffix(".json").write_text(json.dumps(meta,indent=2))
    return meta
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--markets",default="KRW-BTC,KRW-ETH")
    p.add_argument("--unit",type=int,default=60)
    p.add_argument("--start",required=True);p.add_argument("--end",required=True)
    p.add_argument("--out-dir",required=True)
    p.add_argument("--max-pages",type=int,default=100)
    a=p.parse_args()
    for m in a.markets.split(","):
        path=Path(a.out_dir)/f"{m}_{a.unit}m_history.csv"
        print(json.dumps(collect(m,a.unit,a.start,a.end,path,a.max_pages),ensure_ascii=False),flush=True)
if __name__=="__main__":main()
