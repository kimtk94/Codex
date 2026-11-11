"""Read-only Alpaca historical bar entitlement probe.

Requires ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY as ephemeral CI secrets.
Never logs credentials or row-level price data. No orders or account requests.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SAMPLES=[("2020-03","2020-03-02T14:30:00Z","2020-03-03T21:00:00Z"),("2023-03","2023-03-01T14:30:00Z","2023-03-02T21:00:00Z"),("2026-09","2026-09-01T13:30:00Z","2026-09-02T20:00:00Z")]
def main():
    result={"schema_version":1,"provider":"alpaca","mode":"read_only","samples":{}}
    key=os.environ.get("ALPACA_API_KEY_ID")
    secret=os.environ.get("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        result["status"]="BLOCKED_MISSING_CREDENTIALS"
    else:
        result["status"]="PROBED"
        for feed in ("iex","sip"):
            result["samples"][feed]={}
            for label,start,end in SAMPLES:
                params=urlencode({"symbols":"QQQ,QLD","timeframe":"15Min","start":start,"end":end,"limit":100,"feed":feed,"adjustment":"raw"})
                req=Request("https://data.alpaca.markets/v2/stocks/bars?"+params,
                    headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,"Accept":"application/json"})
                try:
                    with urlopen(req,timeout=20) as resp:
                        payload=json.load(resp)
                    records=payload.get("bars") or {}
                    result["samples"][feed][label]={"status":"AVAILABLE" if any(records.values()) else "EMPTY",
                        "counts":{k:len(v) for k,v in records.items()},"pagination":bool(payload.get("next_page_token"))}
                except HTTPError as exc:
                    result["samples"][feed][label]={"status":"HTTP_ERROR","http_code":exc.code}
                except (URLError,TimeoutError,ValueError) as exc:
                    result["samples"][feed][label]={"status":"REQUEST_ERROR","type":type(exc).__name__}
    out=Path("artifacts/market-tool-lab/alpaca-capability.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
if __name__=="__main__":
    main()
