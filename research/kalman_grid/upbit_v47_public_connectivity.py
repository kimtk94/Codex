"""PAPER ONLY Upbit KRW market connectivity probe. GET public data only.
No credentials, private endpoints, broker orders or persistent services.
"""
import json,sys,urllib.request,urllib.parse,urllib.error
from datetime import datetime,timezone

HOST="https://api.upbit.com"
MARKETS="KRW-BTC,KRW-ETH"
def read(endpoint,params):
    url=HOST+endpoint+"?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"KalmanGridReadOnly/1.0"},method="GET")
    with urllib.request.urlopen(req,timeout=12) as response:
        return json.load(response)
def main():
    result={"mode":"PUBLIC_GET_ONLY","timestamp_utc":datetime.now(timezone.utc).isoformat(),"markets":MARKETS,"tests":{}}
    endpoints=(("ticker","/v1/ticker",{"markets":MARKETS}),("orderbook","/v1/orderbook",{"markets":MARKETS,"count":5}),("tick_policy","/v1/orderbook/instruments",{"markets":MARKETS}))
    for name,path,params in endpoints:
        try:
            data=read(path,params)
            if not isinstance(data,list) or len(data)!=2:raise ValueError("unexpected markets payload")
            output=[]
            for item in data:
                if item.get("market") not in MARKETS.split(","):raise ValueError("unexpected market")
                if name=="ticker":values={"market":item["market"],"trade_price":item.get("trade_price"),"timestamp_ms":item.get("timestamp")}
                elif name=="orderbook":
                    top=(item.get("orderbook_units") or [{}])[0]
                    values={"market":item["market"],"bid":top.get("bid_price"),"ask":top.get("ask_price"),"bid_size":top.get("bid_size"),"ask_size":top.get("ask_size"),"timestamp_ms":item.get("timestamp")}
                else:values={"market":item["market"],"tick_size":item.get("tick_size"),"supported_levels":item.get("supported_levels")}
                output.append(values)
            result["tests"][name]={"status":"PASS","data":output}
        except Exception as exc:
            result["tests"][name]={"status":"FAIL","error":str(exc)[:220]}
    result["status"]="PASS" if all(x["status"]=="PASS" for x in result["tests"].values()) else "PARTIAL_OR_FAIL"
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["status"]=="PASS" else 2
if __name__=="__main__":sys.exit(main())
