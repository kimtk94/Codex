"""Research-only Upbit KRW hourly benchmark. No live orders."""
import argparse,csv,json
from pathlib import Path
from v25_research import evaluate
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input-dir",required=True);p.add_argument("--output-dir",required=True)
    a=p.parse_args();root=Path(a.input_dir);out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    results=[]
    for market in ("KRW-BTC","KRW-ETH"):
        file=root/(market+"_60m_history.csv")
        with file.open(newline="") as f: data=list(csv.DictReader(f))
        assert len(data)>1000 and len({x["t"] for x in data})==len(data)
        prices=[(x["t"],x["c"]) for x in data]
        for spacing in ("0.14","0.20","0.30","0.50","1.00"):
            for interval in (0,140,700):
                r=evaluate(prices,spacing=spacing,anchor_every=interval,levels=100,cash="30000",notional="10000",fee="0.05")
                r.update(market=market,spacing_pct=spacing,rolling_bars=interval,source_bars=len(prices),start=prices[0][0],end=prices[-1][0],fee_pct="0.05")
                results.append(r)
    path=out/"sweep.csv"
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
    summary={"results":str(path),"scenarios":len(results),"source":"UPBIT_PUBLIC_KRW_HOURLY","no_orders":True,"limits":["close_only","no_slippage","no_tick_rounding","no_1m","no_fee_tier_verification"]}
    (out/"manifest.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary))
if __name__=="__main__":main()
