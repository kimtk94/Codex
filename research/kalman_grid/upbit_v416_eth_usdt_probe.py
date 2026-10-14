"""V4.16 public GET-only cross-market spot liquidity probe.
Lists active markets before asking for ticker/orderbook.
No credentials, orders, persistence or FX conversion assumptions.
"""
import json,sys
from upbit_v47_public_connectivity import read

def main():
 pairs=read("/v1/market/all",{"is_details":"false"})
 allowed={v["market"] for v in pairs if isinstance(v,dict)}
 targets=[x for x in ("KRW-ETH","USDT-ETH","KRW-USDT") if x in allowed]
 report={"mode":"PUBLIC_GET_ONLY","supported_pairs":{s:s in allowed for s in ("KRW-ETH","USDT-ETH","KRW-USDT")},"results":[]}
 if not {"KRW-ETH","USDT-ETH"}.issubset(allowed):
  report["status"]="PAIR_NOT_LISTED";print(json.dumps(report,indent=2,ensure_ascii=False));return 2
 string=",".join(targets)
 tick={x["market"]:x for x in read("/v1/ticker",{"markets":string})}
 book={x["market"]:x for x in read("/v1/orderbook",{"markets":string,"count":5})}
 inst={x["market"]:x for x in read("/v1/orderbook/instruments",{"markets":string})}
 for m in targets:
  b=book[m]["orderbook_units"][0]
  mid=(float(b["ask_price"])+float(b["bid_price"]))/2
  report["results"].append({"market":m,"last":tick[m]["trade_price"],"bid":b["bid_price"],"ask":b["ask_price"],
   "spread_pct_mid":(float(b["ask_price"])-float(b["bid_price"]))/mid*100,
   "top_bid_size":b.get("bid_size"),"top_ask_size":b.get("ask_size"),
   "tick_size":inst[m].get("tick_size"),"acc_trade_price_24h":tick[m].get("acc_trade_price_24h"),
   "quote_currency":m.split("-")[0]})
 report["status"]="PASS"
 report["limitations"]="Not a profitability comparison: cross-market commissions and KRW-USDT conversion costs not included; 24h volume denominated in differing quote currencies."
 print(json.dumps(report,indent=2,ensure_ascii=False));return 0
if __name__=="__main__":sys.exit(main())
