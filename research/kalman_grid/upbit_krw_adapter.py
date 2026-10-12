"""Read-only Upbit KRW candle data adapter for Grid research."""
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path

def fetch_hourly(market, count=200):
    if market not in ("KRW-BTC", "KRW-ETH"):
        raise ValueError("Unexpected market")
    args=urllib.parse.urlencode({"market":market,"count":count})
    url="https://api.upbit.com/v1/candles/minutes/60?"+args
    request=urllib.request.Request(url,headers={"User-Agent":"Kalman-Grid-Research"})
    with urllib.request.urlopen(request,timeout=20) as response:
        raw=json.load(response)
    return sorted([
        {"t":x["candle_date_time_utc"]+"Z","o":x["opening_price"],
         "h":x["high_price"],"l":x["low_price"],"c":x["trade_price"],
         "v":x["candle_acc_trade_volume"]}
        for x in raw],key=lambda x:x["t"])

def export(market,out_dir):
    rows=fetch_hourly(market)
    dest=Path(out_dir)/(market+"_1h.csv")
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=("t","o","h","l","c","v"))
        w.writeheader()
        w.writerows(rows)
    return str(dest),len(rows)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--out-dir",required=True)
    a=p.parse_args()
    for m in ("KRW-BTC","KRW-ETH"):
        print(m,export(m,a.out_dir))
